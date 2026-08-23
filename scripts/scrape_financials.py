from curl_cffi import requests
import yaml
import pandas as pd
from helper import save_dataframe_as_csv, upsert_into_bigquery, get_symbols_from_richbourse, table_exists
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re
import json
import io
from google.auth import default


FINANCIALS_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"


def get_existing_symbols_and_years():
    """Query BigQuery to get existing (symbol, fiscal_year) pairs with announcement_date.
    
    Returns a dict mapping (symbol, fiscal_year) tuples to announcement_date.
    Used for smart PDF download - skips if we already have data from this announcement.
    """
    from google.cloud import bigquery
    from google.auth import default
    
    credentials, project_id = default()
    client = bigquery.Client(credentials=credentials, project=project_id)
    query = f"""
        SELECT symbol, fiscal_year, announcement_date
        FROM `{project_id}.stocks.financials`
    """
    
    try:
        results = client.query(query).result()
        return {(row.symbol, row.fiscal_year): {
            'announcement_date': str(row.announcement_date) if row.announcement_date else None
        } for row in results}
    except Exception:
        # Table might not exist or be empty
        return {}


def extract_year_from_title(title):
    """Extract fiscal year from announcement title."""
    # Look for patterns like "Exercice 2024", "2024", "Exercice 2023-2024"
    patterns = [
        r'Exercice\s*(\d{4})',
        r'(\d{4})',
        r'(\d{4})-(\d{2,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            year_str = match.group(1)
            try:
                return int(year_str)
            except ValueError:
                continue
    
    return None


def should_reject_announcement(title):
    """Check if announcement should be rejected (trimestre/semestre)."""
    title_lower = title.lower()
    reject_keywords = ['trimestre', 'trimestriel', 'semestre', 'semestriel', 'quarterly']
    return any(keyword in title_lower for keyword in reject_keywords)


def get_announcements_for_symbol(symbol):
    """Fetch announcements for a specific symbol."""
    url = f"https://www.richbourse.com/common/actualite-categorie/index/etats-financiers?symbole={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
    
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    announcements = []
    # Find all announcement rows
    rows = soup.find_all('div', class_=lambda x: x and ('ligne_paire' in x or 'ligne_impaire' in x))
    
    for row in rows:
        date_div = row.find('div', class_=lambda x: x and ('col-xs-4' in x or 'col-md-3' in x))
        link_elem = row.find('a', href=True)
        
        if not date_div or not link_elem:
            continue
        
        date_text = date_div.get_text(strip=True)
        title = link_elem.get_text(strip=True)
        href = link_elem.get('href', '')
        
        # Parse date (format: DD/MM/YYYY)
        try:
            parts = date_text.split('/')
            if len(parts) == 3:
                day, month, year = parts
                announcement_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                continue
        except:
            continue
        
        # Skip trimestre/semestre
        if should_reject_announcement(title):
            continue
        
        # Extract fiscal year
        fiscal_year = extract_year_from_title(title)
        if not fiscal_year:
            continue
        
        # Build PDF URL - ensure it's absolute
        if href.startswith('/'):
            pdf_url = f"https://www.richbourse.com{href}"
        elif href.startswith('http'):
            pdf_url = href
        else:
            # Relative URL - prepend base URL
            pdf_url = f"https://www.richbourse.com/common/actualite-categorie/index/{href}"
        
        announcements.append({
            'symbol': symbol,
            'title': title,
            'announcement_date': announcement_date,
            'fiscal_year': fiscal_year,
            'url': pdf_url
        })
    
    return announcements


def is_data_incomplete(data):
    """Check if extracted data is incomplete (any missing value).
    
    Returns True if at least one financial field is null/missing.
    """
    if data is None:
        return True
    
    financial_fields = ['revenue', 'net_income', 'total_debt', 'cash_and_cash_equivalents', 'total_equity']
    
    # Return True if any field is missing
    return any(data.get(field) is None for field in financial_fields)


def extract_pdf_url_from_details_page(details_url, session, headers):
    """Fetch the details HTML page and extract the actual PDF URL.
    
    RichBourse changed their URL format from:
    - Old: /common/actualite/afficher-fichier/... (direct PDF)
    - New: /common/actualite/details/... (HTML page with PDF link)
    
    This function handles the new format by extracting the PDF link from the HTML.
    """
    try:
        # Update headers to request HTML
        html_headers = headers.copy()
        html_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        
        response = session.get(details_url, headers=html_headers, timeout=30, impersonate="chrome", allow_redirects=True)
        
        if response.status_code != 200:
            print(f"    Failed to fetch details page: HTTP {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for PDF links - common patterns:
        # 1. Links with .pdf extension
        # 2. Links containing 'fichier' or 'download'
        
        pdf_link = None
        
        # First, try to find direct PDF links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if '.pdf' in href.lower() or 'fichier' in href.lower() or 'download' in href.lower():
                pdf_link = href
                break
        
        # If not found, try to find links in content containers
        if not pdf_link:
            for container in soup.find_all(['div', 'section', 'article'], class_=lambda x: x and ('content' in x.lower() or 'file' in x.lower() or 'document' in x.lower())):
                for a_tag in container.find_all('a', href=True):
                    href = a_tag.get('href', '')
                    if '.pdf' in href.lower() or 'fichier' in href.lower():
                        pdf_link = href
                        break
                if pdf_link:
                    break
        
        # Last resort: look for any link that might be a PDF
        if not pdf_link:
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                if 'afficher-fichier' in href or 'download' in href or 'fichier' in href:
                    pdf_link = href
                    break
        
        if not pdf_link:
            print(f"    Could not find PDF link in details page")
            return None
        
        # Convert to absolute URL if needed
        if pdf_link.startswith('/'):
            pdf_url = f"https://www.richbourse.com{pdf_link}"
        elif pdf_link.startswith('http'):
            pdf_url = pdf_link
        else:
            pdf_url = f"https://www.richbourse.com/common/actualite/{pdf_link}"
        
        print(f"    Extracted PDF URL: {pdf_url[:80]}...")
        return pdf_url
        
    except Exception as e:
        print(f"    Error extracting PDF URL from details page: {e}")
        return None


def extract_text_from_pdf(pdf_content):
    """Extract text from PDF using pdfplumber (falls back to pypdf).
    
    Args:
        pdf_content: The PDF file content as bytes
    
    Returns:
        Extracted text as string, or None if extraction fails
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return text if text.strip() else None
    except Exception as e:
        print(f"    pdfplumber failed: {e}")
    
    # Fallback to pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text if text.strip() else None
    except Exception as e:
        print(f"    pypdf failed: {e}")
    
    return None


def extract_financials_from_pdf(pdf_content, openrouter_api_key, max_retries=2):
    """Extract financial data from PDF using OpenRouter API with retry on better models.
    
    First extracts text from PDF to avoid hitting image limits (50 max).
    
    Args:
        pdf_content: The PDF file content as bytes
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries with better models (default: 2)
    
    Returns:
        Dictionary with extracted financial data or None if all attempts fail
    """
    # First, try to extract text from PDF to avoid image limit issues
    print("    Extracting text from PDF...")
    pdf_text = extract_text_from_pdf(pdf_content)
    
    use_text_mode = pdf_text and len(pdf_text) > 100  # Use text if we got meaningful content
    
    if use_text_mode:
        print(f"    Using text extraction ({len(pdf_text)} chars)")
    else:
        print("    Text extraction failed or too short, falling back to PDF file (may hit image limit)")
    
    prompt = """You are a financial data extraction expert. Extract structured financial data from a BRVM annual financial statement PDF.

For each document, extract the following fields:

fiscal_year: The fiscal year of the report (e.g., 2024). Use the most recent year covered by the statement, not the publication date.

revenue: Total revenue or "chiffre d'affaires" (produits d'exploitation / chiffre d'affaires net). For banks, use "produit net bancaire" (PNB) if chiffre d'affaires is not presented. In local currency (XOF/FCFA), expressed in full units.

net_income: Net income or "résultat net" (résultat net de l'exercice). Use the net result attributable to the company (résultat net part du groupe if consolidated accounts are shown alongside company-only accounts, otherwise résultat net). In local currency, expressed in full units.

total_debt: Definition depends on company type:
  - For NON-FINANCIAL companies (industrial, commercial, services, utilities): use total financial/interest-bearing debt — "dettes financières", "emprunts et dettes financières", or total dettes (excluding trade payables/fournisseurs and other non-financial liabilities when itemized separately). If only "total passif" is available with no breakdown, use total passif minus capitaux propres.
  - For BANKS and financial institutions: "total_debt" does not follow the standard corporate definition. Instead, use the sum of interest-bearing liabilities to third parties, typically composed of: "dettes envers les établissements de crédit" (interbank borrowings), "dettes envers la clientèle" (customer deposits), and "emprunts obligataires et dettes rattachées" (bonds and related debt), if separately reported. If these line items are not individually broken out, use "total dettes" or "total passif" (excluding "capitaux propres" and "provisions techniques" for insurers) as a fallback. Do not include "capitaux propres", "provisions pour risques et charges", or off-balance-sheet commitments in this figure.
  - For INSURANCE companies: use total technical and financial liabilities excluding equity — primarily "provisions techniques" plus any interest-bearing debt, if the breakdown is available; otherwise use total passif minus capitaux propres.
  In local currency, expressed in full units.

cash_and_cash_equivalents: Cash and cash equivalents — "trésorerie", "trésorerie et équivalents de trésorerie", or "disponibilités". For banks, this may appear as "caisse, banques centrales" or "trésorerie active" — use that if the standard line is absent. In local currency, expressed in full units.

total_equity: Total equity — "capitaux propres" or "capitaux propres part du groupe" (total, including reserves, capital, and retained earnings — "report à nouveau"). In local currency, expressed in full units.

symbol: The first 4 or 5 letters of the document name (before the "_" character).

CRITICAL — DETECT COMPANY TYPE FIRST:
Before extracting total_debt, determine whether the document is a bank/financial institution, an insurance company, or a non-financial (corporate) company, based on the statement structure, sector references, or company name (e.g., BOA, SGBCI, NSIA, SONIBANK are banks/insurers; industrial or commercial names like SONATEL, NESTLE, SOLIBRA are non-financial). Apply the matching total_debt definition above.

CRITICAL — UNIT NORMALIZATION:
Financial statements often present figures in thousands, millions, or billions of XOF, with the unit noted near the table header or in a footnote (e.g., "en milliers de FCFA", "en millions de FCFA", "montants exprimés en milliers d'unités monétaires"). You MUST detect this unit and convert every extracted monetary value into full base units (i.e., the actual FCFA amount) before returning it. Examples:
- If the statement says "en milliers de FCFA" and shows 12 345, the actual value is 12345000.
- If the statement says "en millions de FCFA" and shows 12, the actual value is 12000000.
- If the statement says "en milliards de FCFA" and shows 1.2, the actual value is 1200000000.
- If no unit is specified, assume the figures are already in full units (do not scale).
Apply the detected scale factor consistently to ALL five monetary fields (revenue, net_income, total_debt, cash_and_cash_equivalents, total_equity) — do not mix scales within the same document. Double-check that the final numbers are plausible in magnitude for a BRVM-listed company (typically hundreds of millions to hundreds of billions of FCFA).

Instructions for each document:
- The documents are from companies listed on the BRVM (Bourse Régionale des Valeurs Mobilières), West Africa, and prepared under SYSCOHADA révisé / BCEAO-PCB norms.
- The documents may be in French — look for: "chiffre d'affaires", "résultat net", "trésorerie", "capitaux propres", "dettes", "passifs", along with the unit disclosure (milliers/millions/milliards).
- Extract the most recent fiscal year's data (usually the first/leftmost column in the balance sheet and income statement).
- If a field is not found, use null — do not guess or estimate.
- Do not include any explanation or text outside the output.

Output format: 
{
  "fiscal_year": <integer or null>,
  "revenue": <number or null>,
  "net_income": <number or null>,
  "total_debt": <number or null>,
  "cash_and_cash_equivalents": <number or null>,
  "total_equity": <number or null>
}
"""
    
    # Model tiers - from free to paid (better models first for retry)
    # Each entry: (model_id, is_free, display_name)
    model_tiers = [
        # Tier 1: Free model (tried first)
        (["google/gemma-4-31b-it:free"], True, "Gemma 4 31B (free)"),
        # Tier 2: Paid model (fallback)
        (["openai/gpt-4o-mini"], False, "GPT-4o Mini"),
    ]
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tradvisor.app",
        "X-Title": "TRADVISOR BRVM"
    }
    
    best_result = None
    
    for tier_idx, (models, is_free, model_name) in enumerate(model_tiers):
        # Skip paid models if we've reached max_retries with free models
        if tier_idx > max_retries and not is_free:
            print(f"    Max retries reached, skipping paid models")
            break
        
        print(f"    Trying model: {model_name}")
        
        if use_text_mode:
            # Send text instead of PDF to avoid image limit
            content = [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"\n\n--- PDF TEXT CONTENT ---\n\n{pdf_text}"}
            ]
        else:
            # Fall back to PDF file (may hit image limit)
            import base64
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "filename": "document.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_base64}"
                    }
                }
            ]
        
        payload = {
            "models": models,
            "provider": {
                "allow_fallbacks": False
            },
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result['choices'][0]['message']['content']
                
                # Parse JSON response
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = text[json_start:json_end]
                    data = json.loads(json_str)
                    
                    # Store this result
                    best_result = data
                    
                    # Check if data is complete enough
                    if not is_data_incomplete(data):
                        print(f"    ✓ Successfully extracted with {model_name}")
                        return data
                    else:
                        print(f"    ✗ Incomplete data from {model_name}, trying better model...")
                        # Continue to try better model
                        continue
            else:
                print(f"    OpenRouter API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"    Error with {model_name}: {e}")
            continue
    
    # Return best result we got, even if incomplete
    if best_result:
        print(f"    Returning best result (may be incomplete)")
    else:
        print(f"    All models failed to extract data")
    
    return best_result


def scrape_financials(url, openrouter_api_key=None):
    """Scrape annual financial statements - MONTHLY RUN.
    
    This script is for regular monthly runs. It collects current and previous
    year financials for symbols that don't already have them.
    
    Processes each symbol individually and upserts to BigQuery immediately
    to avoid memory issues with large datasets.
    """
    import gc
    
    current_year = datetime.now().year
    previous_year = current_year - 1
    
    # Get existing data from BigQuery
    existing_data = get_existing_symbols_and_years()
    table_exists_flag = table_exists('financials')
    
    # If table doesn't exist or is empty, auto-initialize with all historical data
    if not table_exists_flag or not existing_data:
        print("No existing data found. Auto-initializing with all available historical data...")
        # Lazy import to avoid circular import issues
        from scrape_financials_init import scrape_financials_init
        # Get URL from config (need to load it here since we're outside entry_point)
        import yaml
        with open('config.yml', 'r') as file:
            config = yaml.safe_load(file)
        url = config['url'].get('financials', 'https://www.richbourse.com/common/actualite-categorie/index/etats-financiers')
        return scrape_financials_init(url, openrouter_api_key)
    
    print(f"Found {len(existing_data)} existing (symbol, fiscal_year) pairs in database.")
    
    # Get all available symbols from RichBourse
    all_symbols = get_symbols_from_richbourse(FINANCIALS_URL)
    print(f"Found {len(all_symbols)} total symbols on RichBourse.")
    
    total_processed = 0
    
    for symbol in all_symbols:
        print(f"Processing {symbol}...")
        
        announcements = get_announcements_for_symbol(symbol)
        
        if not announcements:
            print(f"  No announcements found for {symbol}")
            continue
        
        # Deduplicate: keep only the most recent announcement per (symbol, fiscal_year)
        announcements_by_year = {}
        for ann in announcements:
            fiscal_year = ann['fiscal_year']
            
            # Only collect current or previous year
            if fiscal_year not in [current_year, previous_year]:
                continue
            
            key = (symbol, fiscal_year)
            ann_date = ann.get('announcement_date', '')
            
            # Keep most recent announcement
            if key not in announcements_by_year or ann_date > announcements_by_year[key].get('announcement_date', ''):
                announcements_by_year[key] = ann
        
        symbol_data = []
        
        for key, ann in announcements_by_year.items():
            fiscal_year = ann['fiscal_year']
            existing_financials = existing_data.get(key)
            
            # SMART PDF DOWNLOAD: Skip if we already have data from this exact announcement date
            # This avoids re-downloading PDFs unnecessarily when there are multiple announcements
            # for the same fiscal year (we always keep the most recent one)
            if existing_financials and existing_financials.get('announcement_date') == ann['announcement_date']:
                print(f"  FY {fiscal_year} - already up to date, skipping")
                continue
            
            # Download PDF
            try:
                session = requests.Session()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/pdf,*/*",
                    "Referer": "https://www.richbourse.com/",
                }
                
                # Handle new URL format: /details/ URLs return HTML with PDF link
                pdf_url = ann['url']
                if '/details/' in pdf_url:
                    print(f"    Detected /details/ URL, extracting actual PDF URL...")
                    pdf_url = extract_pdf_url_from_details_page(pdf_url, session, headers)
                    if not pdf_url:
                        raise Exception("Failed to extract PDF URL from details page")
                
                # Follow redirects and get the actual PDF
                pdf_response = session.get(pdf_url, headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
                
                if pdf_response.status_code != 200:
                    raise Exception(f"Failed to download PDF: HTTP {pdf_response.status_code}")
                
                # Check if API key is available
                if not openrouter_api_key:
                    raise Exception("OPENROUTER_API_KEY environment variable not set")
                
                # Extract financial data from PDF
                pdf_content = pdf_response.content
                financial_data = extract_financials_from_pdf(pdf_content, openrouter_api_key)
                
                # CRITICAL: Delete PDF content from memory immediately after processing
                del pdf_content
                
                if not financial_data:
                    raise Exception("Failed to extract financial data from PDF - all AI models failed")
                
                # New or updated data - upsert
                # Smart download ensures we only get here if announcement_date is different
                print(f"  FY {fiscal_year} - upserting (newer announcement)")
                # Convert announcement_date string to date object for BigQuery
                # Keep announcement_date as string in YYYY-MM-DD format - BigQuery will parse it as DATE
                symbol_data.append({
                    'symbol': symbol,
                    'fiscal_year': fiscal_year,
                    'revenue': financial_data.get('revenue'),
                    'net_income': financial_data.get('net_income'),
                    'total_debt': financial_data.get('total_debt'),
                    'cash_and_cash_equivalents': financial_data.get('cash_and_cash_equivalents'),
                    'total_equity': financial_data.get('total_equity'),
                    'announcement_date': ann['announcement_date'],  # String format "YYYY-MM-DD"
                    'document_link': ann['url'],
                    'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
                print(f"    Extracted: revenue={financial_data.get('revenue')}, net_income={financial_data.get('net_income')}")
                
                # Free financial data memory
                del financial_data
                
                # Close session to free memory
                session.close()
                
            except Exception as e:
                print(f"    FATAL ERROR: {e}")
                raise
        
        # Upsert this symbol's data to BigQuery immediately
        if symbol_data:
            df_symbol = pd.DataFrame(symbol_data)
            try:
                credentials, project_id = default()
                upsert_into_bigquery(df_symbol, project_id, 'stocks', 'financials', ['symbol', 'fiscal_year'])
                print(f"  Upserted {len(df_symbol)} records to BigQuery.")
                total_processed += len(df_symbol)
            except Exception as e:
                print(f"  BigQuery upsert failed: {e}")
            
            # Free memory
            del df_symbol
            del symbol_data
        
        # Force garbage collection after each symbol
        gc.collect()
    
    print(f"\nMonthly run complete. Total records upserted: {total_processed}")
    return pd.DataFrame()


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    # Get OpenRouter API key from environment
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    
    # Scrape and upsert to BigQuery (memory-efficient, processes each symbol individually)
    scrape_financials(
        config['url'].get('financials', 'https://www.richbourse.com/common/actualite-categorie/index/etats-financiers'),
        openrouter_api_key
    )
    
    return "Monthly run complete.\n"


# Local testing (only run when executed directly)
if __name__ == "__main__":
    print(entry_point())
