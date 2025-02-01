import yaml
import pandas as pd
from helper import save_dataframe_as_csv
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import functions_framework

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
    table = soup.find('table', {"class": "table table-hover table-striped sticky-enabled"})
    # Extract the headers from the table
    # Extract the header
    headers = ["SYMBOL","NAME","PRICE","INTEREST_RATE","ISSUE_DATE","MATURITY_DATE"]
    # header_row = table.find('thead').find_all('th')
    # for th in header_row:
    #     headers.append(th.get_text().strip().replace(' ', "_").upper())
    # Extract the rows from the table
    rows = []
    for tr in table.find('tbody').find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        t_row = [cell.text.strip() for cell in cells]
        try:
            tmp_list = str(t_row[1]).split(" ")
            name = ' '.join(tmp_list[:-2])
            interest_rate = float(tmp_list[-2].replace(',', '.').strip('%'))/100
            maturity_date = "31/12/"+tmp_list[-1].split("-")[1]
            price = t_row[4]
            symbol = t_row[0]
            issue_date = t_row[2]
            row = [symbol]+[name]+[price]+[interest_rate]+[issue_date]+[maturity_date]
            rows.append(row)
        except:
            print("Issue with row:", t_row)
            continue
    return headers, rows


def scrape_brvm_bonds(url):
    headers, rows = scrape(url)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)
    # df['NAME'] = df['NAME'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    df['MATURITY_DATE'] = pd.to_datetime(df['MATURITY_DATE'])
    df['ISSUE_DATE'] = pd.to_datetime(df['ISSUE_DATE'])
    df['PRICE'] = df['PRICE'].str.replace(' ', '').astype(float)
    # df['INTEREST'] = df['INTEREST'].str.replace(' ', '').str.replace(',','.').astype(float)
    df['DATE'] = datetime.now().strftime('%Y-%m-%d')

    # Display the DataFrame
    return df

@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    df = scrape_brvm_bonds(config['url']['bonds'])
    return save_dataframe_as_csv(df, 'BONDS', config)

# print(entry_point())