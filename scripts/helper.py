import os
import shutil
import pandas as pd
import glob
import requests
from bs4 import BeautifulSoup

from datetime import datetime

from google.cloud import storage
def save_dataframe_as_csv(df, fin_asset, gcs_bucket_name=None):
    """
    Save a Pandas DataFrame as a CSV file either locally or to Google Cloud Storage (GCS).

    Parameters:
    - df (pd.DataFrame): The DataFrame to save.
    - filename (str): The name of the file to save as.
    - gcs_bucket_name (str, optional): The name of the GCS bucket. If provided, the file will be saved to GCS.
      If None, the file will be saved locally.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f'{fin_asset}-{today}.csv'
    if gcs_bucket_name:
        # Save the file to a temporary location
        temp_filename = f'/tmp/{filename}'
        df.to_csv(temp_filename, index=False)

        # Upload the file to GCS
        client = storage.Client()
        bucket = client.bucket(gcs_bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_filename(temp_filename)

        # Optionally, remove the local temp file after upload
        os.remove(temp_filename)

        print(f"File saved to GCS bucket '{gcs_bucket_name}' as '{filename}'.")
    else:
        # Save the file locally
        file = os.path.join(os.path.dirname(__file__), '..','data', filename)
        df.to_csv(file, index=False, sep="|")
        print(f"File saved locally as '{filename}'.")

def scrape(url):
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
    return headers, rows

def move_csv_files(source_dir, destination_dir, pattern):
    # List all files in the source directory
    files = [f for f in os.path.join(os.path.dirname(__file__), '..', source_dir) if f.startswith(pattern)]
    csv_files = glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '..', source_dir), f"{pattern}*.csv"))

    # Loop through the files and move the CSV files to the destination directory
    for file in csv_files:
        file_name = file.split("/")[-1]
        source_file = os.path.join(os.path.dirname(__file__), '..', source_dir, file_name)
        destination_file = os.path.join(os.path.dirname(__file__), '..', destination_dir, file_name)
        # source_file = os.path.join(f"../{source_dir}", file)
        # destination_file = os.path.join(f"../{destination_dir}", file)
        shutil.move(source_file, destination_file)
        print(f'Moved: {file_name}')
