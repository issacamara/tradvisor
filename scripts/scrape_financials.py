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


def extract_financials_from_pdf(pdf_content, openrouter_api_key, max_retries=2):
    """Extract financial data from PDF using OpenRouter API with retry on better models.
    
    Args:
        pdf_content: The PDF file content as bytes
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries with better models (default: 2)
    
    Returns:
        Dictionary with extracted financial data or None if all attempts fail
    """
    import base64
    
    # Convert PDF to base64
    pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
    
    prompt = """You are a financial statement extraction engine specialized in BRVM and OHADA-style annual reports, often written in French.

Your task is to extract the most recent fiscal year's financial data from the provided PDF or parsed document text and return ONLY a valid JSON object with this exact schema:

{
  "fiscal_year": null,
  "revenue": null,
  "net_income": null,
  "total_debt": null,
  "cash_and_cash_equivalents": null,
  "total_equity": null
}

Definitions:

- fiscal_year: the most recent year shown in the statement heading or reporting date, such as "Exercice 2023", "Exercice clos le 31 décembre 2023", or "au 31.12.2023".
- revenue: total revenue, usually labeled "chiffre d'affaires", "ventes", or "produits des activités ordinaires". Prefer "chiffre d'affaires" over "chiffre d'affaires & autres produits" unless the latter is clearly the document's defined top-line revenue.
- net_income: final profit or loss for the year, usually labeled "résultat net", "bénéfice net", "perte nette", or "résultat net de l'exercice".
- total_debt: use ONLY interest-bearing financial debt, not total liabilities. Include clearly financial items such as "emprunts", "emprunts à LT", "dettes financières", "autres dettes financières", bonds, bank borrowings, lease liabilities, overdrafts, and "emprunts et dettes financières". Exclude provisions, trade payables, tax and social liabilities, customer advances, and other operating liabilities. If several explicit interest-bearing debt items are shown and no total is provided, sum them only when the reconstruction is unambiguous.
- cash_and_cash_equivalents: cash or near-cash liquidity, usually labeled "trésorerie actif", "disponibilités", "trésorerie et équivalents de trésorerie", or equivalent. Prefer the balance-sheet cash asset figure. Do not use net cash or "trésorerie nette" when a gross cash figure is available.
- total_equity: total shareholders' equity, usually labeled "capitaux propres". Prefer an explicit total. If not explicitly shown, sum visible equity components such as capital, share premium, revaluation surplus, reserves, retained earnings / report à nouveau, and current-year net income only when the reconstruction is unambiguous.

Unit normalization requirement:

- Return every monetary value in the smallest base currency unit represented by the currency, normally the full currency unit.
- Detect the reporting unit from headings, captions, footnotes, or the surrounding text. Examples include:
  - "en milliers de FCFA", "en milliers de francs CFA", "KFCFA", or "FCFA '000": values are in thousands, so multiply each extracted monetary value by 1000.
  - "en millions de FCFA", "en millions de F CFA", "M FCFA", or "FCFA millions": values are in millions, so multiply each extracted monetary value by 1000000.
  - "en milliards de FCFA", "milliards de F CFA", or "B FCFA": values are in billions, so multiply each extracted monetary value by 1000000000.
  - "en milliers d'euros": multiply by 1000.
  - "en millions d'euros": multiply by 1000000.
  - "en milliards d'euros": multiply by 1000000000.
  - If no scale is stated, treat the value as already expressed in full currency units.
- Apply the detected multiplier consistently to revenue, net_income, total_debt, cash_and_cash_equivalents, and total_equity.
- Do not convert between currencies. Preserve the source currency; only remove the reporting scale.
- Do not apply the unit multiplier to fiscal_year.
- If a value contains a French thousands separator, interpret it correctly before applying the scale. For example, "13.423" in a table stated as "millions de FCFA" means 13,423 million FCFA, which must be returned as 13423000000.
- French decimal commas may represent decimal fractions. Do not treat a decimal fraction as a thousands separator unless the document layout clearly indicates otherwise.
- Parentheses around a number indicate a negative amount. Preserve the negative sign where the requested field itself is negative, such as a net loss. Do not use parentheses or other non-numeric formatting in the JSON.
- Round only when the source presents a monetary value as a whole number in the stated reporting unit. Do not invent precision that is not present.

Extraction rules:

1. Use the most recent fiscal year only.
2. Prefer explicit subtotal or total lines over manual reconstruction.
3. Never guess.
4. If a field is not explicitly present and cannot be reconstructed unambiguously from visible components, return null.
5. Return monetary values as integers only, with no currency symbol, no spaces, no commas, no decimal points, and no unit suffix.
6. Return values normalized to full base currency units according to the detected reporting scale.
7. Preserve the source currency denomination; do not convert, revalue, or normalize currencies.
8. If multiple candidate values exist for a field, choose the one that best matches the definition above.
9. Do not use total liabilities as total_debt.
10. Do not infer missing values from ratios, commentary, percentages, cash-flow movements, or narrative text.
11. Ignore prior years unless the latest year is missing.
12. If the document is scanned or OCR is noisy, extract only values identifiable with high confidence.
13. Use the balance sheet for cash, equity, and debt whenever those figures are available.
14. For total_debt, include only interest-bearing financial debt existing at the reporting date. Do not use debt repayments or financing cash flows as the debt balance.
15. If a statement provides both "chiffre d'affaires" and "chiffre d'affaires & autres produits", use "chiffre d'affaires" for revenue unless the document explicitly defines the combined subtotal as revenue.
16. Validate reconstructed totals where possible, but do not substitute a mathematically derived value if an explicit value exists.
17. Do not include explanatory text, Markdown, comments, citations, or additional JSON fields in the output.

French label hints:

- revenue: "chiffre d'affaires", "ventes", "produits des activités ordinaires", "revenus"
- net_income: "résultat net", "bénéfice net", "perte nette", "résultat net de l'exercice", "bénéfice/perte de l'exercice"
- cash_and_cash_equivalents: "trésorerie actif", "disponibilités", "trésorerie et équivalents de trésorerie", "valeurs à encaisser"
- total_equity: "capitaux propres", "capital", "prime", "réserves", "report à nouveau", "écart de réévaluation", "résultat net"
- total_debt: "emprunt", "emprunts à LT", "dettes financières", "autres dettes financières", "emprunts et dettes financières", "concours bancaires", "découverts bancaires", "passifs de location"

Examples of unit normalization:

- If the statement says "(en millions de FCFA)" and revenue is "578 922", return 578922000000.
- If the statement says "(en milliers de FCFA)" and net income is "8 709", return 8709000.
- If the statement says "(en milliards de FCFA)" and total equity is "45,699", return 45699000000000.
- If the statement has no stated scale and revenue is "578922000000", return 578922000000.
- If the statement says "(en millions de FCFA)" and debt is composed of "Emprunts à LT: 1 052" and "Dettes financières: 2 435", return 3487000000 for total_debt.
- If the statement says "(en millions de FCFA)" and cash is "Trésorerie - Actif: 4 825", return 4825000000.

Return only this JSON object:

{
  "fiscal_year": <integer or null>,
  "revenue": <integer or null>,
  "net_income": <integer or null>,
  "total_debt": <integer or null>,
  "cash_and_cash_equivalents": <integer or null>,
  "total_equity": <integer or null>
}"""
    
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
        
        payload = {
            "models": models,
            "provider": {
                "allow_fallbacks": False
            },
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "file",
                            "file": {
                                "filename": "document.pdf",
                                "file_data": f"data:application/pdf;base64,{pdf_base64}"
                            }
                        }
                    ]
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
                # Follow redirects and get the actual PDF
                pdf_response = session.get(ann['url'], headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
                
                if pdf_response.status_code != 200:
                    raise Exception(f"Failed to download PDF: HTTP {pdf_response.status_code}")
                
                # Check if API key is available
                if not openrouter_api_key:
                    raise Exception("OPENROUTER_API_KEY environment variable not set")
                
                financial_data = extract_financials_from_pdf(pdf_response.content, openrouter_api_key)

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
                
                # Free PDF memory
                del pdf_response
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
