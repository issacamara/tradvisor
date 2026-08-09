from curl_cffi import requests
import yaml
import pandas as pd
from helper import save_dataframe_as_csv, get_symbols_from_richbourse, parse_french_date
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re


RATINGS_URL = "https://www.richbourse.com/common/notation-financiere/index"


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
    table = soup.find('table', {"class": lambda x: x and 'table-striped' in x and 'table-bordered' in x})
    
    if not table:
        return []
    
    tbody = table.find('tbody')
    if not tbody:
        return []
    
    for row in tbody.find_all('tr'):
        cells = row.find_all('td')
        
        if len(cells) < 4:
            continue
        
        try:
            date_text = cells[1].get_text(strip=True)
            rating_year = parse_french_date(date_text)
            
            if not rating_year:
                continue
            
            rating_short_term = cells[2].get_text(strip=True) if len(cells) > 2 else None
            rating_long_term = cells[3].get_text(strip=True) if len(cells) > 3 else None
            
            if rating_short_term or rating_long_term:
                ratings.append({
                    'symbol': symbol,
                    'rating_year': rating_year,
                    'rating_short_term': rating_short_term if rating_short_term else None,
                    'rating_long_term': rating_long_term if rating_long_term else None,
                })
        
        except Exception as e:
            continue
    
    return ratings


def scrape_ratings_init(url):
    """Scrape financial ratings - INITIALIZATION (all available years).
    
    This script is for first-time setup. It collects all available ratings
    for all symbols.
    """
    # Get all symbols from RichBourse
    print("Initialization: fetching all symbols from RichBourse...")
    symbols = get_symbols_from_richbourse(RATINGS_URL)
    
    print(f"Processing {len(symbols)} symbols...")
    
    all_data = []
    
    for symbol in symbols:
        print(f"Processing {symbol}...")
        
        ratings = get_ratings_for_symbol(symbol)
        
        if not ratings:
            print(f"  No ratings found for {symbol}")
            continue
        
        for rating in ratings:
            print(f"  Found: {rating['rating_year']} - Short: {rating['rating_short_term']}, Long: {rating['rating_long_term']}")
            
            all_data.append({
                'symbol': symbol,
                'rating_year': rating['rating_year'],
                'rating_short_term': rating['rating_short_term'],
                'rating_long_term': rating['rating_long_term'],
            })
    
    if not all_data:
        print("No ratings data found.")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    return df


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    df = scrape_ratings_init(config['url'].get('ratings', 'https://www.richbourse.com/common/notation-financiere/index'))
    
    if df.empty:
        return "No new data to collect.\n"
    
    print("\n=== COLLECTED DATA ===")
    print(df.to_json(orient='records', indent=2))
    print("======================\n")
    
    return save_dataframe_as_csv(df, 'RATINGS', config)


if __name__ == "__main__":
    print(entry_point())
