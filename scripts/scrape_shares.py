import requests
import yaml
import pandas as pd
import re
import functions_framework
from bs4 import BeautifulSoup
import os
from helper import save_dataframe_as_csv
from datetime import datetime
from google.auth import default


def scrape(url):
    params = {
        "hl": "en"  # language
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }
    page = requests.get(url=url, params=params, headers=headers, timeout=30, verify=False)
    soup = BeautifulSoup(page.content, 'html.parser')
    # Find the table in the HTML (assuming there's only one table)
    table = soup.find('table', {"class": "tablesorter tbl100_6 tbl1"})
    # Extract the headers from the table
    # Extract the header
    headers = ['SYMBOL', 'NAME', 'OPEN', 'HIGH', 'LOW', 'VOLUME', 'CLOSE']

    # Extract the rows from the table
    rows = []
    for tr in table.find('tbody').find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        del cells[-1]  # remove VARIATION column
        del cells[-2]  # remove VOLUME_(FCFA)
        symbol = cells[0].find('a', href=True)['href'].split("_")[1].split(".")[0]
        row = [symbol] + [cells[0].text.strip().replace('\xa0', ' ')] + [
            re.sub(r'[^0-9]', '', cell.text.strip()) for cell in cells[1:]]
        rows.append(row)

    return headers, rows


def scrape_brvm_shares(url):
    headers, rows = scrape(url)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)

    df['OPEN'] = df['OPEN'].str.replace(',', '.').astype(float)
    df['HIGH'] = df['HIGH'].str.replace(',', '.').astype(float)
    df['LOW'] = df['LOW'].str.replace(',', '.').astype(float)
    df['CLOSE'] = df['CLOSE'].str.replace(',', '.').astype(float)
    df['VOLUME'] = df['VOLUME'].str.replace(',', '.').astype(float)
    df['DATE'] = datetime.now().strftime('%Y-%m-%d')
    # Display the DataFrame
    return df

@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    df = scrape_brvm_shares(config['url']['shares'])
    return save_dataframe_as_csv(df, 'SHARES', config)

env = 'gcp'
if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
    pass
else:
    print(entry_point())