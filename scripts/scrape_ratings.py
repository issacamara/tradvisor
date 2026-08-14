from curl_cffi import requests
import yaml
import pandas as pd
from helper import save_dataframe_as_csv, get_symbols_from_richbourse, table_exists, parse_french_date
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re
from google.auth import default


RATINGS_URL = "https://www.richbourse.com/common/notation-financiere/index"


def get_existing_symbols_and_years():
    """Query BigQuery to get existing (symbol, year) pairs with their ratings.
    
    Returns a dict mapping (symbol, year) tuples to their rating values.
    """
    from google.cloud import bigquery
    from google.auth import default
    
    credentials, project_id = default()
    client = bigquery.Client(credentials=credentials, project=project_id)
    query = f"""
        SELECT symbol, rating_year, rating_short_term, rating_long_term
        FROM `{project_id}.stocks.ratings`
    """
    
    try:
        results = client.query(query).result()
        return {(row.symbol, row.rating_year): {
            'rating_short_term': row.rating_short_term,
            'rating_long_term': row.rating_long_term
        } for row in results}
    except Exception:
        # Table might not exist or be empty
        return {}


def get_ratings_for_symbol(symbol):
    """Fetch ratings for a specific symbol."""
    url = f"https://www.richbourse.com/common/notation-financiere/index?symbole={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.richbourse.com/common/notation-financiere/index"
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
    
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    ratings = []
    
    # Find the ratings table - look for the one with "Dernières notations financières"
    table = soup.find('table', {"class": lambda x: x and 'table-striped' in x and 'table-bordered' in x})
    
    if not table:
        return []
    
    tbody = table.find('tbody')
    if not tbody:
        return []
    
    # Process each row
    for row in tbody.find_all('tr'):
        cells = row.find_all('td')
        
        if len(cells) < 4:
            continue
        
        try:
            # Column 1: Agence de notation (not needed)
            # Column 2: Date (e.g., "Juillet 2025")
            date_text = cells[1].get_text(strip=True)
            rating_date = parse_french_date(date_text)
            
            if not rating_date:
                continue
            
            # Column 3: Court terme (e.g., "A1 perspective Stable")
            rating_short_term = cells[2].get_text(strip=True) if len(cells) > 2 else None
            
            # Column 4: Long terme (e.g., "AA- perspective Stable")
            rating_long_term = cells[3].get_text(strip=True) if len(cells) > 3 else None
            
            if rating_short_term or rating_long_term:
                ratings.append({
                    'symbol': symbol,
                    'rating_year': rating_date,
                    'rating_short_term': rating_short_term if rating_short_term else None,
                    'rating_long_term': rating_long_term if rating_long_term else None,
                })
        
        except Exception as e:
            continue
    
    return ratings


def scrape_ratings(url):
    """Scrape financial ratings - MONTHLY RUN (previous year only).
    
    This script is for regular monthly runs. It collects only the previous
    year's ratings for symbols that don't already have it.
    """
    current_year = datetime.now().year
    previous_year = current_year - 1  # Only collect previous year
    
    # Get existing data from BigQuery
    existing_data = get_existing_symbols_and_years()
    table_exists_flag = table_exists('ratings')
    
    # If table doesn't exist or is empty, auto-initialize with all historical data
    if not table_exists_flag or not existing_data:
        print("No existing data found. Auto-initializing with all available historical data...")
        # Lazy import to avoid circular import issues
        from scrape_ratings_init import scrape_ratings_init
        # Get URL from config (need to load it here since we're outside entry_point)
        import yaml
        with open('config.yml', 'r') as file:
            config = yaml.safe_load(file)
        url = config['url'].get('ratings', 'https://www.richbourse.com/common/notation-financiere/index')
        return scrape_ratings_init(url)
    
    print(f"Found {len(existing_data)} existing (symbol, year) pairs in database.")
    
    all_data = []
    updated_data = []
    
    # Get all available symbols from RichBourse
    all_symbols = get_symbols_from_richbourse(RATINGS_URL)
    print(f"Found {len(all_symbols)} total symbols on RichBourse.")
    
    for symbol in all_symbols:
        print(f"Processing {symbol}...")
        
        ratings = get_ratings_for_symbol(symbol)
        
        if not ratings:
            print(f"  No ratings found for {symbol}")
            continue
        
        for rating in ratings:
            rating_year = rating['rating_year']
            
            # Only collect current or previous year
            if rating_year not in [current_year, previous_year]:
                continue
            
            key = (symbol, rating_year)
            existing_rating = existing_data.get(key)
            
            # Check if we need to insert or update
            if existing_rating is None:
                # New data - insert
                print(f"  Found NEW: {rating_year} - Short: {rating['rating_short_term']}, Long: {rating['rating_long_term']}")
                all_data.append({
                    'symbol': symbol,
                    'rating_year': rating_year,
                    'rating_short_term': rating['rating_short_term'],
                    'rating_long_term': rating['rating_long_term'],
                })
            else:
                # Check if values changed - update if different
                needs_update = False
                if rating['rating_short_term'] != existing_rating['rating_short_term']:
                    needs_update = True
                    print(f"  Short term changed for {rating_year}: {existing_rating['rating_short_term']} -> {rating['rating_short_term']}")
                if rating['rating_long_term'] != existing_rating['rating_long_term']:
                    needs_update = True
                    print(f"  Long term changed for {rating_year}: {existing_rating['rating_long_term']} -> {rating['rating_long_term']}")
                
                if needs_update:
                    updated_data.append({
                        'symbol': symbol,
                        'rating_year': rating_year,
                        'rating_short_term': rating['rating_short_term'],
                        'rating_long_term': rating['rating_long_term'],
                    })
                else:
                    print(f"  {rating_year} unchanged (idempotent)")
    
    # Combine new and updated data
    all_data.extend(updated_data)
    
    if not all_data:
        print("No new or updated ratings data found.")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    print(f"\nCollected {len(df)} records ({len(all_data) - len(updated_data)} new, {len(updated_data)} updated)")
    return df


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    df = scrape_ratings(config['url'].get('ratings', 'https://www.richbourse.com/common/notation-financiere/index'))
    
    if df.empty:
        return "No new data to collect.\n"
    
    # Print JSON to stdout for verification
    print("\n=== COLLECTED DATA ===")
    print(df.to_json(orient='records', indent=2))
    print("======================\n")
    
    # Save to CSV (for archival)
    result = save_dataframe_as_csv(df, 'ratings', config)
    
    return result


# Local testing (only run when executed directly)
if __name__ == "__main__":
    print(entry_point())
