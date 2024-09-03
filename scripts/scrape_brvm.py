import requests
import yaml
import pandas as pd
from google.cloud import storage

from bs4 import BeautifulSoup


def scrape_brvm(url):
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
        headers.append(th.get_text().strip())


    # Extract the rows from the table
    rows = []
    for tr in table.find('tbody').find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        row = [cell.text.strip() for cell in cells]
        for i in range(2,6):
            row[i] = float(row[i].replace(" ", ""))
        rows.append(row)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)

    # Display the DataFrame
    print(df)

with open("../config.yml", 'r') as file:
    config = yaml.safe_load(file)
scrape_brvm(config[0]['url']['shares'])