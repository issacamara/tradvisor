import io
import os
import re
import unicodedata
import yaml
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
from google.auth import default
from google.cloud import storage, bigquery
import functions_framework

from helper import get_symbols_from_richbourse, get_project_number

FINANCIALS_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn').lower()

def is_valid_financial_title(title):
    normalized = normalize_text(title)
    return 'etat' in normalized and 'financier' in normalized

def extract_year_from_title(title):
    patterns = [r'Exercice\s*(\d{4})', r'(\d{4})', r'(\d{4})-(\d{2,4})']
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None

def should_reject_announcement(title):
    reject_keywords = ['trimestre', 'trimestriel', 'semestre', 'semestriel', 'quarterly']
    return any(k in title.lower() for k in reject_keywords)

def get_existing_symbols_and_years():
    """Query BigQuery to get existing (symbol, fiscal_year) pairs with announcement_date."""
    credentials, project_id = default()
    client = bigquery.Client(credentials=credentials, project=project_id)
    query = f"""
        SELECT symbol, fiscal_year, CAST(announcement_date AS STRING) AS announcement_date
        FROM `{project_id}.stocks.financials`
    """
    try:
        results = client.query(query).result()
        return {
            (row.symbol, int(row.fiscal_year)): row.announcement_date
            for row in results
        }
    except Exception as e:
        print(f"Error querying BigQuery: {e}")
        return {}

def extract_pdf_url_from_details_page(details_url, session, headers):
    try:
        html_headers = headers.copy()
        html_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        res = session.get(details_url, headers=html_headers, timeout=30, impersonate="chrome", allow_redirects=True)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        pdf_link = None
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if '.pdf' in href.lower() or 'fichier' in href.lower() or 'download' in href.lower():
                pdf_link = href
                break
        
        if not pdf_link:
            return None
        
        if pdf_link.startswith('/'):
            return f"https://www.richbourse.com{pdf_link}"
        elif pdf_link.startswith('http'):
            return pdf_link
        return f"https://www.richbourse.com/common/actualite/{pdf_link}"
    except Exception as e:
        print(f"Error extracting PDF URL: {e}")
        return None

def get_announcements_for_symbol(symbol, min_year, single_year_only=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": FINANCIALS_URL
    }
    session = requests.Session()
    announcements = []
    page = 1
    seen_urls = set()

    while True:
        url = f"{FINANCIALS_URL}/{symbol}?page={page}"
        try:
            res = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
            if res.status_code != 200:
                break
            soup = BeautifulSoup(res.content, 'html.parser')
            rows = soup.find_all('div', class_=lambda x: x and ('ligne_paire' in x or 'ligne_impaire' in x))
            if not rows:
                break
            
            page_extracted_years = []
            new_items = 0
            
            for row in rows:
                date_div = row.find('div', class_=lambda x: x and ('col-xs-4' in x or 'col-md-3' in x))
                link_elem = row.find('a', href=True)
                if not date_div or not link_elem:
                    continue
                
                date_text = date_div.get_text(strip=True)
                title = link_elem.get_text(strip=True)
                href = link_elem.get('href', '')
                
                pdf_url = f"https://www.richbourse.com{href}" if href.startswith('/') else href
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)
                new_items += 1
                
                if not is_valid_financial_title(title) or should_reject_announcement(title):
                    continue
                
                fiscal_year = extract_year_from_title(title)
                if not fiscal_year:
                    continue
                page_extracted_years.append(fiscal_year)

                if single_year_only and fiscal_year != min_year:
                    continue
                elif not single_year_only and fiscal_year < min_year:
                    continue

                parts = date_text.split('/')
                ann_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}" if len(parts) == 3 else None
                if not ann_date:
                    continue

                announcements.append({
                    'symbol': symbol,
                    'title': title,
                    'fiscal_year': fiscal_year,
                    'announcement_date': ann_date,
                    'url': pdf_url
                })

            if new_items == 0 or (page_extracted_years and max(page_extracted_years) < min_year):
                break
            page += 1
        except Exception as e:
            print(f"Error fetching page {page} for {symbol}: {e}")
            break
            
    return announcements

def download_and_save_pdf_to_gcs(ann, bucket, existing_bq_data):
    symbol = ann['symbol']
    fiscal_year = int(ann['fiscal_year'])
    ann_date = str(ann['announcement_date'])
    key = (symbol, fiscal_year)

    existing_date = existing_bq_data.get(key)

    # If key exists in BQ and the web announcement date is NOT strictly greater, skip download
    if existing_date and ann_date <= existing_date:
        print(f"  [SKIPPED BQ] {symbol} FY{fiscal_year}: BQ date ({existing_date}) >= Scraping date ({ann_date})")
        return

    blob_name = f"financials_pdf/{symbol}_{fiscal_year}_{ann_date}.pdf"
    blob = bucket.blob(blob_name)
    if blob.exists():
        print(f"  [SKIPPED GCS] {blob_name} already exists in bucket.")
        return

    print(f"  [DOWNLOADING] {symbol} FY{fiscal_year} (Web date: {ann_date} > BQ date: {existing_date})")
    
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*"}
    pdf_url = ann['url']
    if '/details/' in pdf_url:
        pdf_url = extract_pdf_url_from_details_page(pdf_url, session, headers)
        if not pdf_url:
            return

    res = session.get(pdf_url, headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
    if res.status_code == 200:
        blob.metadata = {
            'symbol': symbol,
            'fiscal_year': str(fiscal_year),
            'announcement_date': ann_date,
            'document_link': ann['url']
        }
        blob.upload_from_string(res.content, content_type='application/pdf')
        print(f"  ✓ Saved to GCS: {blob_name}")
def scrape_financials_init(url):
    min_year = datetime.now().year - 5
    credentials, project_id = default()
    project_number = get_project_number(project_id)
    storage_client = storage.Client()
    bucket = storage_client.bucket(f"data-{project_number}")

    print("Checking existing records in BigQuery...")
    existing_bq_data = get_existing_symbols_and_years()

    symbols = get_symbols_from_richbourse(url)
    for symbol in symbols:
        announcements = get_announcements_for_symbol(symbol, min_year)
        for ann in announcements:
            download_and_save_pdf_to_gcs(ann, bucket, existing_bq_data)

@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    url = config['url'].get('financials', FINANCIALS_URL)
    scrape_financials_init(url)
    return "Financials initialization completed.\n"

if __name__ == "__main__":
    print(entry_point())