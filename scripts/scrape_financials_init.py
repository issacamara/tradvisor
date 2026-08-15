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


FINANCIALS_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"


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
    rows = soup.find_all('div', class_=lambda x: x and ('ligne_paire' in x or 'ligne_impaire' in x))
    
    for row in rows:
        date_div = row.find('div', class_=lambda x: x and ('col-xs-4' in x or 'col-md-3' in x))
        link_elem = row.find('a', href=True)
        
        if not date_div or not link_elem:
            continue
        
        date_text = date_div.get_text(strip=True)
        title = link_elem.get_text(strip=True)
        href = link_elem.get('href', '')
        
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
            pdf_url = f"https://www.richbourse.com/common/actualite-categorie/index/{href}"
        
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
        # Cover / index / front matter
        selected_pages.update(range(min(5, total_pages)))

        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").lower()
            if any(kw in text for kw in keywords):
                selected_pages.add(idx)

        # Fallback to initial pages if text parsing was impossible or found no matches
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
- Detect the reporting unit from headings, captions, footnotes, or the surrounding text.
- Apply the detected multiplier consistently to revenue, net_income, total_debt, cash_and_cash_equivalents, and total_equity.
- Do not convert between currencies.
- Return monetary values as integers only with no formatting.

Return only this JSON object:

{
  "fiscal_year": <integer or null>,
  "revenue": <integer or null>,
  "net_income": <integer or null>,
  "total_debt": <integer or null>,
  "cash_and_cash_equivalents": <integer or null>,
  "total_equity": <integer or null>
}"""

    model_tiers = [
        (["google/gemma-4-31b-it:free"], True, "Gemma 4 31B (free)"),
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
    
    # 1. Standard Path: Text Extraction (Parses entire PDF regardless of total page count)
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

    # 3. Last-resort Fallback: Sequential 40-Page Chunking for fully scanned image PDFs
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
        announcements = get_announcements_for_symbol(symbol)
        
        if not announcements:
            print(f"  No announcements found for {symbol}")
            continue
        
        announcements_by_year = {}
        for ann in announcements:
            fiscal_year = ann['fiscal_year']
            key = (symbol, fiscal_year)
            ann_date = ann.get('announcement_date', '')
            
            if fiscal_year < max_year:
                continue
            
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
                pdf_response = session.get(ann['url'], headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
                
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