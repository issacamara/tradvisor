import requests
import yaml
import pandas as pd
from google.cloud import storage
from helper import save_dataframe_as_csv

from bs4 import BeautifulSoup
from helper import scrape


def scrape_brvm_capitalisations(url):
    params = {
        "hl": "en"  # language
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }

    page = requests.get(url=url, params=params, headers=headers,
                        timeout=30)
    soup = BeautifulSoup(page.content, 'html.parser')
    # Find the table in the HTML (assuming there's only one table)
    table = soup.find('table', {"class": "table table-hover table-striped sticky-enabled"})
    # Extract the headers from the table
    # Extract the header
    headers = []
    header_row = table.find('thead').find_all('th')
    for th in header_row:
        headers.append(th.get_text().strip().replace(' ', "_").upper())


    # Extract the rows from the table
    rows = []
    for tr in table.find('tbody').find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        row = [cell.text.strip() for cell in cells]
        rows.append(row)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)
    df['NAME'] = df['NAME'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    df['NUMBER_OF_SHARES'] = df['NUMBER_OF_SHARES'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['DAILY_PRICE'] = df['DAILY_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['FLOATING_CAPITALIZATION'] = df['FLOATING_CAPITALIZATION'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['GLOBAL_CAPITALIZATION'] = df['GLOBAL_CAPITALIZATION'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['GLOBAL_CAPITALIZATION_(%)'] = df['GLOBAL_CAPITALIZATION_(%)'].str.replace(' ', '').str.replace(',', '.').astype(float)

    # Display the DataFrame
    return df

with open("../config.yml", 'r') as file:
    config = yaml.safe_load(file)
df = scrape_brvm_capitalisations(config['url']['capitalisations'])
save_dataframe_as_csv(df, 'CAPITALISATIONS')