import requests
import yaml
import pandas as pd
from google.cloud import storage
from helper import save_dataframe_as_csv, scrape

from bs4 import BeautifulSoup


def scrape_brvm_share(url):
    headers, rows = scrape(url)
    params = {
        "hl": "en"  # language
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }
    data = []
    for i in range(1,3):
        page = requests.get(url=f"{url}?page={i}", params=params, headers=headers,
                            timeout=30)
        soup = BeautifulSoup(page.content, 'html.parser')
        # Find the table in the HTML (assuming there's only one table)
        table = soup.find('table', {"class": "table table-striped table-bordered"})
        # Extract the headers from the table
        # Extract the header
        table_headers = []
        header_row = table.find('thead').find_all('th')
        for th in header_row:
            table_headers.append(th.get_text().strip().replace(' ', "_").upper())


        # Extract the rows from the table
        rows = []
        for tr in table.find('tbody').find_all('tr'):
            index = tr.find('a', href=True)['href'].split("/")[-1]

            cells = tr.find_all(['td', 'th'])
            row = [cell.text.strip() for cell in cells]
            row[0] = index
            rows.append(row)

        # Convert to a DataFrame
        table_headers[0] = "SYMBOL"
        df = pd.DataFrame(rows, columns=table_headers)
    # df['NAME'] = df['NAME'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    # df['PREVIOUS_PRICE'] = df['PREVIOUS_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    # df['OPENING_PRICE'] = df['OPENING_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    # df['CLOSING_PRICE'] = df['CLOSING_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
        data.append(df)

    # Display the DataFrame
    df = pd.concat(data, axis=0)
    df['DIVIDENDE'] = df['DIVIDENDE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['DATE_PAIEMENT'] = pd.to_datetime(df['DATE_PAIEMENT'], errors='coerce')
    return df.drop(df.columns[[1, 3, 4]], axis=1)

with open("../config.yml", 'r') as file:
    config = yaml.safe_load(file)
df = scrape_brvm_share(config['url']['dividends'])
save_dataframe_as_csv(df, 'DIVIDENDS')