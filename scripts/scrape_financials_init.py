from curl_cffi import requests
import yaml
import pandas as pd
from helper import save_dataframe_as_csv, upsert_into_bigquery, get_symbols_from_richbourse, table_exists
from google.auth import default
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re
import json
import io
import gc
import unicodedata


FINANCIALS_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"


def normalize_text(text):
    """Normalize string by removing accents and converting to lowercase."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    ).lower()


def is_valid_financial_title(title):
    """Check if title contains 'Etats Financiers' (accent and case insensitive)."""
    normalized_title = normalize_text(title)
    return 'etat' in normalized_title and 'financier' in normalized_title


def extract_year_from_title(title):
    """Extract fiscal year from announcement title."""
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


def get_announcements_for_symbol(symbol, max_year):
    """Fetch announcements for a specific symbol across multiple pages up to max_year."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
    }
    
    session = requests.Session()
    announcements = []
    page = 1
    seen_urls = set()

    while True:
        url = f"https://www.richbourse.com/common/actualite-categorie/index/etats-financiers?symbole={symbol}&page={page}"
        
        try:
            response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
            if response.status_code != 200:
                break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            rows = soup.find_all('div', class_=lambda x: x and ('ligne_paire' in x or 'ligne_impaire' in x))
            
            if not rows:
                break
            
            page_extracted_years = []
            new_items_on_page = 0
            
            for row in rows:
                date_div = row.find('div', class_=lambda x: x and ('col-xs-4' in x or 'col-md-3' in x))
                link_elem = row.find('a', href=True)
                
                if not date_div or not link_elem:
                    continue
                
                date_text = date_div.get_text(strip=True)
                title = link_elem.get_text(strip=True)
                href = link_elem.get('href', '')
                
                # Build absolute PDF URL
                if href.startswith('/'):
                    pdf_url = f"https://www.richbourse.com{href}"
                elif href.startswith('http'):
                    pdf_url = href
                else:
                    pdf_url = f"https://www.richbourse.com/common/actualite-categorie/index/{href}"
                
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)
                new_items_on_page += 1
                
                # Filter title: MUST contain "Etats Financiers"
                if not is_valid_financial_title(title):
                    continue

                # Skip trimestre/semestre
                if should_reject_announcement(title):
                    continue
                
                # Extract fiscal year
                fiscal_year = extract_year_from_title(title)
                if not fiscal_year:
                    continue
                
                page_extracted_years.append(fiscal_year)

                # Skip if outside 5-year limit
                if fiscal_year < max_year:
                    continue

                # Parse date (format: DD/MM/YYYY)
                announcement_date = None
                try:
                    parts = date_text.split('/')
                    if len(parts) == 3:
                        day, month, year = parts
                        announcement_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except Exception:
                    pass
                
                if not announcement_date:
                    continue
                
                announcements.append({
                    'symbol': symbol,
                    'title': title,
                    'fiscal_year': fiscal_year,
                    'announcement_date': announcement_date,
                    'url': pdf_url
                })
            
            # Stop paginating if no new items found or if page looped back
            if new_items_on_page == 0:
                break

            # Stop paginating if all fiscal years extracted on this page are older than 5 years
            if page_extracted_years and max(page_extracted_years) < max_year:
                break
            
            page += 1

        except Exception as e:
            print(f"    Error fetching page {page} for symbol {symbol}: {e}")
            break
            
    return announcements


def get_existing_symbols_and_years():
    """Query BigQuery to get existing (symbol, fiscal_year) pairs with announcement_date."""
    from google.cloud import bigquery
    
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
        return {}


def is_data_incomplete(data):
    """Check if extracted data is incomplete (any missing value)."""
    if data is None:
        return True
    
    financial_fields = ['revenue', 'net_income', 'total_debt', 'cash_and_cash_equivalents', 'total_equity']
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
        # 3. Links in specific classes (if known)
        
        pdf_link = None
        
        # First, try to find direct PDF links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            # Check for PDF extension or common PDF-related keywords
            if '.pdf' in href.lower() or 'fichier' in href.lower() or 'download' in href.lower():
                pdf_link = href
                break
        
        # If not found, try to find links in specific containers
        if not pdf_link:
            # Look for links in common content areas
            for container in soup.find_all(['div', 'section', 'article'], class_=lambda x: x and ('content' in x.lower() or 'file' in x.lower() or 'document' in x.lower())):
                for a_tag in container.find_all('a', href=True):
                    href = a_tag.get('href', '')
                    if '.pdf' in href.lower() or 'fichier' in href.lower():
                        pdf_link = href
                        break
                if pdf_link:
                    break
        
        # If still not found, look for any link that might be a PDF
        if not pdf_link:
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                # Check if it looks like a file URL (contains numbers/IDs)
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
    """Extract full text from PDF across ALL pages using pdfplumber (falls back to pypdf)."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text
    except Exception as e:
        print(f"    pdfplumber failed: {e}")
    
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except Exception as e:
        print(f"    pypdf failed: {e}")
    
    return None


def extract_relevant_pdf_pages(pdf_content, max_pages=40):
    """Scan all pages (including 50+) for keywords and compile a trimmed PDF payload."""
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)

        if total_pages <= max_pages:
            return pdf_content

        keywords = [
            "bilan", "compte de résultat", "états financiers",
            "capitaux propres", "résultat net", "chiffre d'affaires",
            "dettes financières", "trésorerie actif", "passif", "exercice"
        ]

        selected_pages = set()
        selected_pages.update(range(min(5, total_pages)))

        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").lower()
            if any(kw in text for kw in keywords):
                selected_pages.add(idx)

        if len(selected_pages) <= 5:
            print(f"    No keywords matched. Selecting first {max_pages} pages.")
            selected_pages.update(range(min(max_pages, total_pages)))

        sorted_pages = sorted(list(selected_pages))[:max_pages]
        print(f"    Filtered PDF from {total_pages} down to {len(sorted_pages)} targeted pages.")

        writer = PdfWriter()
        for page_idx in sorted_pages:
            writer.add_page(reader.pages[page_idx])

        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    except Exception as e:
        print(f"    Smart slicing failed: {e}")
        return pdf_content


def send_openrouter_payload(content, openrouter_api_key, max_retries=2):
    """Helper to call OpenRouter models with structured fallback strategy."""
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

    model_tiers = [
        (["google/gemma-4-31b-it:free"], True, "Gemma 4 31B (free)"),
        # (["openai/gpt-4o-mini"], False, "GPT-4o Mini"),
        (["deepseek/deepseek-v4-flash-0731"], False, "DeepSeek V4 Flash 0731")
    ]
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tradvisor.app",
        "X-Title": "TRADVISOR BRVM"
    }

    best_result = None

    for tier_idx, (models, is_free, model_name) in enumerate(model_tiers):
        if tier_idx > max_retries and not is_free:
            break
        
        payload = {
            "models": models,
            "provider": {"allow_fallbacks": False},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}] + content
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
                
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(text[json_start:json_end])
                    best_result = data
                    
                    if not is_data_incomplete(data):
                        print(f"    ✓ Successfully extracted with {model_name}")
                        return data
                    else:
                        print(f"    ✗ Incomplete data from {model_name}, trying next model...")
            else:
                print(f"    OpenRouter API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"    Error with {model_name}: {e}")
            continue

    return best_result


def extract_financials_from_pdf(pdf_content, openrouter_api_key):
    """Extract financial data handling full-text extraction, smart slicing, and image chunking."""
    import base64

    print("    Extracting text from PDF...")
    pdf_text = extract_text_from_pdf(pdf_content)
    
    # 1. Standard Path: Text Extraction
    if pdf_text and len(pdf_text) > 100:
        print(f"    Using full document text extraction ({len(pdf_text)} chars)")
        text_content = [{"type": "text", "text": f"\n\n--- PDF TEXT CONTENT ---\n\n{pdf_text}"}]
        result = send_openrouter_payload(text_content, openrouter_api_key)
        if result and not is_data_incomplete(result):
            return result

    # 2. Scanned / Image Fallback: Smart Keyword Slicing
    print("    Text extraction empty or incomplete. Applying Smart Keyword PDF slicing...")
    sliced_pdf_bytes = extract_relevant_pdf_pages(pdf_content, max_pages=40)
    pdf_base64 = base64.b64encode(sliced_pdf_bytes).decode('utf-8')
    
    file_content = [{
        "type": "file",
        "file": {
            "filename": "document.pdf",
            "file_data": f"data:application/pdf;base64,{pdf_base64}"
        }
    }]
    
    result = send_openrouter_payload(file_content, openrouter_api_key)
    if result and not is_data_incomplete(result):
        return result

    # 3. Last-resort Fallback: Sequential Chunking
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)
        
        if total_pages > 40:
            print(f"    Attempting sequential chunk processing across {total_pages} pages...")
            for start in range(0, total_pages, 40):
                end = min(start + 40, total_pages)
                print(f"    Scanning page chunk {start + 1} to {end}...")

                writer = PdfWriter()
                for i in range(start, end):
                    writer.add_page(reader.pages[i])

                chunk_buf = io.BytesIO()
                writer.write(chunk_buf)
                chunk_b64 = base64.b64encode(chunk_buf.getvalue()).decode('utf-8')

                chunk_content = [{
                    "type": "file",
                    "file": {
                        "filename": f"chunk_{start}.pdf",
                        "file_data": f"data:application/pdf;base64,{chunk_b64}"
                    }
                }]
                
                chunk_result = send_openrouter_payload(chunk_content, openrouter_api_key)
                if chunk_result and not is_data_incomplete(chunk_result):
                    return chunk_result
    except Exception as e:
        print(f"    Sequential chunking error: {e}")

    return result


def scrape_financials_init(url, openrouter_api_key=None):
    """Scrape annual financial statements - INITIALIZATION (last 5 years)."""
    current_year = datetime.now().year
    max_year = current_year - 5
    
    print("Checking existing data in BigQuery...")
    existing_data = get_existing_symbols_and_years()
    print(f"Found {len(existing_data)} existing (symbol, fiscal_year) pairs.")
    
    print("Fetching all symbols from RichBourse...")
    symbols = get_symbols_from_richbourse(FINANCIALS_URL)
    print(f"Processing {len(symbols)} symbols...")
    
    total_processed = 0
    
    for symbol in symbols:
        print(f"Processing {symbol}...")
        announcements = get_announcements_for_symbol(symbol, max_year)
        
        if not announcements:
            
            print(f"  No valid announcements found for {symbol}")
            continue
        
        announcements_by_year = {}
        for ann in announcements:
            fiscal_year = ann['fiscal_year']
            key = (symbol, fiscal_year)
            ann_date = ann.get('announcement_date', '')
            
            if key not in announcements_by_year or ann_date > announcements_by_year[key].get('announcement_date', ''):
                announcements_by_year[key] = ann
        
        symbol_data = []
        
        for ann in announcements_by_year.values():
            fiscal_year = ann['fiscal_year']
            key = (symbol, fiscal_year)
            existing = existing_data.get(key)
            
            if existing and existing.get('announcement_date') == ann['announcement_date']:
                print(f"  FY {fiscal_year} - already up to date, skipping")
                continue
            
            print(f"  Found: {ann['title']} (FY {fiscal_year})")
            
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
                
                pdf_response = session.get(pdf_url, headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
                
                if pdf_response.status_code != 200:
                    raise Exception(f"Failed to download PDF: HTTP {pdf_response.status_code}")
                
                if not openrouter_api_key:
                    raise Exception("OPENROUTER_API_KEY environment variable not set")
                
                pdf_content = pdf_response.content
                financial_data = extract_financials_from_pdf(pdf_content, openrouter_api_key)
                
                del pdf_content
                
                if not financial_data:
                    raise Exception("Failed to extract financial data from PDF - all AI models failed")
                
                symbol_data.append({
                    'symbol': symbol,
                    'fiscal_year': fiscal_year,
                    'revenue': financial_data.get('revenue'),
                    'net_income': financial_data.get('net_income'),
                    'total_debt': financial_data.get('total_debt'),
                    'cash_and_cash_equivalents': financial_data.get('cash_and_cash_equivalents'),
                    'total_equity': financial_data.get('total_equity'),
                    'announcement_date': ann['announcement_date'],
                    'document_link': ann['url'],
                    'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
                print(f"    Extracted: revenue={financial_data.get('revenue')}, net_income={financial_data.get('net_income')}")
                
                del financial_data
                session.close()
                
            except Exception as e:
                print(f"    FATAL ERROR: {e}")
                raise
        
        if symbol_data:
            df_symbol = pd.DataFrame(symbol_data)
            try:
                credentials, project_id = default()
                upsert_into_bigquery(df_symbol, project_id, 'stocks', 'financials', ['symbol', 'fiscal_year'])
                print(f"  Upserted {len(df_symbol)} records to BigQuery.")
                total_processed += len(df_symbol)
            except Exception as e:
                print(f"  BigQuery upsert failed: {e}")
            
            del df_symbol
            del symbol_data
        
        gc.collect()
    
    print(f"\nInitialization complete. Total records upserted: {total_processed}")
    return pd.DataFrame()


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    
    scrape_financials_init(
        config['url'].get('financials', 'https://www.richbourse.com/common/actualite-categorie/index/etats-financiers'),
        openrouter_api_key
    )
    
    return "Initialization complete.\n"


if __name__ == "__main__":
    print(entry_point())