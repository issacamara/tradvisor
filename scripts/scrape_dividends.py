from curl_cffi import requests
import yaml
import pandas as pd
from helper import save_dataframe_as_csv
from datetime import datetime
from bs4 import BeautifulSoup
import functions_framework
import os
import re


def scrape_dividends(url):
    """Scrape dividend data from BRVM website.
    
    Returns: SYMBOL, DIVIDEND, PAYMENT_DATE
    """
    params = {"hl": "en"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.richbourse.com/common/dividende"
    }
    
    all_data = []
    
    # Try multiple pages
    for page_num in range(1, 4):
        try:
            if page_num == 1:
                page_url = url
            else:
                page_url = f"{url}?page={page_num - 1}"
            
            session = requests.Session()
            response = session.get(page_url, params=params, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
            
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the table - try multiple approaches
            table = soup.find('table', {"class": "table table-striped table-bordered"})
            if not table:
                table = soup.find('table', {"class": "table table-striped"})
            if not table:
                table = soup.find('table', {"class": "tablesorter"})
            if not table:
                # Find any table with dividend-related headers
                tables = soup.find_all('table')
                for t in tables:
                    headers = t.find_all('th')
                    header_text = [h.get_text().strip().upper() for h in headers]
                    if 'DIVIDENDE' in str(header_text) or 'SOCIÉTÉ' in str(header_text):
                        table = t
                        break
            if not table:
                print(f"No table found on page {page_num}")
                continue
            
            tbody = table.find('tbody')
            if not tbody:
                continue
            
            # Process each row
            for row in tbody.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 6:
                    continue
                
                try:
                    # Column 1: Extract symbol from link (Société)
                    symbol_link = cells[1].find('a', href=True)
                    if symbol_link:
                        symbol = symbol_link['href'].split('/')[-1]
                    else:
                        continue
                    
                    # Column 2: Extract dividend amount (Dividende)
                    dividend_text = cells[2].get_text(strip=True)
                    dividend_text = re.sub(r'[^0-9,]', '', dividend_text)
                    dividend_text = dividend_text.replace(',', '.')
                    dividend = float(dividend_text) if dividend_text else 0
                    
                    # Column 5: Payment date (Date paiement)
                    payment_date = cells[5].get_text(strip=True)
                    if 'inconnue' in payment_date.lower() or not payment_date:
                        payment_date = None
                    else:
                        # Try to parse the date format from the website (likely DD/MM/YYYY)
                        try:
                            parts = payment_date.split('/')
                            if len(parts) == 3:
                                day, month, year = parts
                                payment_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        except:
                            payment_date = None
                    
                    all_data.append({
                        'SYMBOL': symbol,
                        'DIVIDEND': dividend,
                        'PAYMENT_DATE': payment_date
                    })
                    
                except Exception as e:
                    continue
                    
        except Exception as e:
            break
    
    if not all_data:
        raise ValueError("No dividend data found")
    
    df = pd.DataFrame(all_data)
    df['DATE'] = datetime.now().strftime('%Y-%m-%d')
    
    return df


@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    
    df = scrape_dividends(config['url']['dividends'])
    return save_dataframe_as_csv(df, 'DIVIDENDS', config)


# Local testing
env = 'gcp'
if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
    pass
else:
    print(entry_point())