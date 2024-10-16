import yaml
import pandas as pd
from util.helper import save_dataframe_as_csv, scrape
from datetime import datetime


def scrape_brvm_share(url):
    headers, rows = scrape(url)

    # Convert to a DataFrame
    df = pd.DataFrame(rows, columns=headers)
    df['NAME'] = df['NAME'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    df['VOLUME'] = df['VOLUME'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['OPENING_PRICE'] = df['OPENING_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['CLOSING_PRICE'] = df['CLOSING_PRICE'].str.replace(' ', '').str.replace(',', '.').astype(float)
    df['DATE'] = datetime.now().strftime('%Y-%m-%d')
    # Display the DataFrame
    return df[["SYMBOL","NAME","VOLUME","OPENING_PRICE","CLOSING_PRICE","DATE"]]

with open("../config.yml", 'r') as file:
    config = yaml.safe_load(file)
df = scrape_brvm_share(config['url']['shares'])
save_dataframe_as_csv(df, 'SHARES')