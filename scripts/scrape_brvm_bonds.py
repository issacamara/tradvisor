import yaml
import pandas as pd
from google.cloud import storage
from helper import save_dataframe_as_csv

from helper import scrape


def scrape_brvm_bonds(url):
    headers, rows = scrape(url)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)
    df['NAME'] = df['NAME'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    df['MATURITY_DATE'] = pd.to_datetime(df['MATURITY_DATE'])
    df['ISSUE_DATE'] = pd.to_datetime(df['ISSUE_DATE'])
    df['DAILY_PRICE'] = df['DAILY_PRICE'].str.replace(' ', '').astype(float)
    df['INTEREST'] = df['INTEREST'].str.replace(' ', '').str.replace(',','.').astype(float)

    # Display the DataFrame
    return df


with open("../config.yml", 'r') as file:
    config = yaml.safe_load(file)
df = scrape_brvm_bonds(config['url']['bonds'])
save_dataframe_as_csv(df, 'BONDS')