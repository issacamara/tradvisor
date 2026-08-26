from curl_cffi import requests
import yaml
import pandas as pd
from google.auth import default
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re
import gc
import unicodedata
from google.cloud import storage


# BRVM URLs
BRVM_LISTING_URL = "https://www.brvm.org/fr/rapports-societes-cotees"
FINANCIALS_REPORT_TYPE = 57  # field_type_rapport_tid=57 for "Etats Financiers"


def load_symbol_mapping(csv_path):
    """Load symbol mapping from CSV file.
    
    CSV format: slug,symbol
    Example: air-liquide-ci,AIRL
    
    Parameters:
    - csv_path: Path to CSV file. If None, looks for 'mapping.csv' in scripts dir
    
    Returns:
    - Dictionary mapping slug to symbol
    """

    mapping = {}
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, sep=';', encoding='latin1')
        if 'emetteur' in df.columns and 'symbol' in df.columns:
            mapping = dict(zip(df['emetteur'], df['symbol']))
        print(f"Loaded {len(mapping)} symbol mappings from {csv_path}")
    else:
        print(f"Warning: Symbol mapping file not found at {csv_path}")
    
    return mapping


def normalize_text(text):
    """Normalize string by removing accents and converting to lowercase."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    ).lower()


def extract_year_from_title(title):
    """Extract fiscal year from announcement title.
    
    Handles formats like:
    - "Etats financiers - Exercice 2025"
    - "Etats financiers ejercicio 2019"
    - "Exercice 2024"
    """
    patterns = [
        r'Exercice\s*(\d{4})',
        r'exercice\s*(\d{4})',
        r'(\d{4})',
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


def get_companies_from_brvm():
    """Fetch all companies from BRVM listing page.
    
    Returns:
    - List of tuples: (slug, company_name)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    session = requests.Session()
    companies = []
    page = 0
    
    while True:
        url = BRVM_LISTING_URL if page == 0 else f"{BRVM_LISTING_URL}?page={page}"
        
        try:
            response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
            if response.status_code != 200:
                break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the companies table
            table = soup.find('table', class_=lambda x: x and 'views-table' in x)
            if not table:
                break
            
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
            if not rows:
                break
            
            new_items = 0
            for row in rows:
                # Find the link to company detail page
                link_elem = row.find('a', href=True)
                if not link_elem:
                    continue
                
                href = link_elem.get('href', '')
                # Extract slug from URL like /fr/rapports-societe-cotes/air-liquide-ci
                match = re.search(r'/fr/rapports-societe-cotes/([^/?]+)', href)
                if not match:
                    continue
                
                slug = match.group(1)
                company_name = link_elem.get_text(strip=True)
                
                companies.append((slug, company_name))
                new_items += 1
            
            if new_items == 0:
                break
            
            page += 1
            
        except Exception as e:
            print(f"    Error fetching companies page {page}: {e}")
            break
    
    return companies


def get_financial_reports_for_company(slug, max_year):
    """Fetch financial reports (Etats Financiers) for a specific company.
    
    Parameters:
    - slug: Company URL slug (e.g., 'air-liquide-ci')
    - max_year: Minimum year to collect (e.g., 2020 for last 5 years)
    
    Returns:
    - List of dicts with: title, fiscal_year, pdf_url
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    session = requests.Session()
    reports = []
    page = 0
    
    while True:
        # Filter by field_type_rapport_tid=57 (Etats Financiers)
        base_url = f"https://www.brvm.org/fr/rapports-societe-cotes/{slug}"
        if page == 0:
            url = f"{base_url}?field_type_rapport_tid={FINANCIALS_REPORT_TYPE}"
        else:
            url = f"{base_url}?field_type_rapport_tid={FINANCIALS_REPORT_TYPE}&page={page}"
        
        try:
            response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
            if response.status_code != 200:
                break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the reports table
            table = soup.find('table', class_=lambda x: x and 'views-table' in x)
            if not table:
                break
            
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
            if not rows:
                break
            
            new_items = 0
            page_years = []
            
            for row in rows:
                # Title is in the first column
                title_cell = row.find('td', class_='views-field-nothing')
                # PDF link is in the second column
                link_cell = row.find('td', class_='views-field-field-fichier')
                
                if not title_cell or not link_cell:
                    continue
                
                title = title_cell.get_text(strip=True)
                link_elem = link_cell.find('a', href=True)
                
                if not link_elem:
                    continue
                
                # Extract fiscal year from title
                fiscal_year = extract_year_from_title(title)
                if not fiscal_year:
                    continue
                
                page_years.append(fiscal_year)
                
                # Skip if outside 5-year limit
                if fiscal_year < max_year:
                    continue
                
                pdf_href = link_elem.get('href', '')
                # Build absolute URL if needed
                if pdf_href.startswith('/'):
                    pdf_url = f"https://www.brvm.org{pdf_href}"
                elif pdf_href.startswith('http'):
                    pdf_url = pdf_href
                else:
                    pdf_url = f"https://www.brvm.org/{pdf_href}"
                
                # Only include PDF files
                if not pdf_url.lower().endswith('.pdf'):
                    continue
                
                reports.append({
                    'title': title,
                    'fiscal_year': fiscal_year,
                    'pdf_url': pdf_url
                })
                new_items += 1
            
            if new_items == 0:
                break
            
            # Stop if all years on this page are older than max_year
            if page_years and max(page_years) < max_year:
                break
            
            page += 1

        except Exception as e:
            print(f"    Error fetching reports for {slug} page {page}: {e}")
            break
    
    return reports


def get_bucket_name():
    """Get the Cloud Storage bucket name for storing PDFs."""
    credentials, project_id = default()
    client = storage.Client(credentials=credentials, project=project_id)
    
    # Look for data bucket
    buckets = list(client.list_buckets())
    for bucket in buckets:
        if bucket.name.startswith(f"data-"):
            return bucket.name
    
    # Fallback to first bucket
    if buckets:
        return buckets[0].name
    
    raise Exception("No suitable storage bucket found")


def download_pdf_to_storage(symbol, fiscal_year, pdf_url, bucket_name):
    """Download PDF from URL and upload to Cloud Storage.
    
    Returns:
    - True if successful, False otherwise
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
            "Referer": "https://www.brvm.org/",
        }
        
        pdf_response = session.get(pdf_url, headers=headers, timeout=60, impersonate="chrome", allow_redirects=True)
        
        if pdf_response.status_code != 200:
            print(f"      Failed to download PDF: HTTP {pdf_response.status_code}")
            return False
        
        pdf_content = pdf_response.content
        
        # Upload to Cloud Storage
        # Format: financials/{symbol}/{fiscal_year}/{timestamp}.pdf
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        blob_name = f"financials/{symbol}/{fiscal_year}/{timestamp}.pdf"
        
        credentials, project_id = default()
        storage_client = storage.Client(credentials=credentials, project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(pdf_content, content_type='application/pdf')
        
        print(f"      Uploaded to gs://{bucket_name}/{blob_name}")
        return True
        
    except Exception as e:
        print(f"      Error downloading/uploading PDF: {e}")
        return False


def scrape_financials_init(url=None):
    """Scrape annual financial statements from BRVM - INITIALIZATION (last 5 years).
    
    Downloads PDF files to Cloud Storage for later processing by insert_financials function.
    """
    current_year = datetime.now().year
    max_year = current_year - 5  # Last 5 years
    
    print(f"Collecting financial PDFs from BRVM (last 5 years: {max_year}-{current_year})...")
    
    # Load symbol mapping (same directory as config.yml)
    mapping_csv_path = os.path.join(os.path.dirname(__file__), 'mapping.csv')
    symbol_mapping = load_symbol_mapping(mapping_csv_path)
    
    print("Fetching all companies from BRVM...")
    companies = get_companies_from_brvm()
    print(f"Found {len(companies)} companies on BRVM.")
    
    # Get storage bucket name
    bucket_name = get_bucket_name()
    print(f"Using storage bucket: {bucket_name}")
    
    total_downloaded = 0
    total_failed = 0
    
    for slug, company_name in companies:
        # Get symbol from mapping
        symbol = symbol_mapping.get(company_name)

        if not symbol:
            print(f"  Warning: No symbol mapping for slug '{slug}' ({company_name}), skipping...")
            continue
        
        print(f"Processing {symbol} ({company_name})...")
        
        # Get financial reports for this company
        reports = get_financial_reports_for_company(slug, max_year)
        
        if not reports:
            print(f"  No financial reports found for {symbol}")
            continue
        
        # Deduplicate by fiscal_year (keep latest/most complete)
        reports_by_year = {}
        for report in reports:
            fiscal_year = report['fiscal_year']
            if fiscal_year not in reports_by_year:
                reports_by_year[fiscal_year] = report
        
        for fiscal_year, report in reports_by_year.items():
            print(f"  Found: {report['title']} (FY {fiscal_year})")
            
            # Download and upload to storage
            success = download_pdf_to_storage(
                symbol, 
                fiscal_year, 
                report['pdf_url'], 
                bucket_name
            )
            
            if success:
                total_downloaded += 1
            else:
                total_failed += 1
        
        gc.collect()
    
    print(f"\nInitialization complete.")
    print(f"  Total PDFs downloaded: {total_downloaded}")
    print(f"  Total failures: {total_failed}")
    return total_downloaded


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    scrape_financials_init(
        config['url'].get('financials', 'https://www.brvm.org/fr/rapports-societes-cotees')
    )
    
    return "PDF download initialization complete.\n"


if __name__ == "__main__":
    print(entry_point())