import os, io
import shutil
from fileinput import filename
import duckdb

from google.cloud import bigquery
import pandas as pd
import glob
import requests
from bs4 import BeautifulSoup
from google.cloud import resourcemanager_v3
from datetime import datetime

from google.cloud import storage
from google.auth import default

def get_project_number(project_id):
    client = resourcemanager_v3.ProjectsClient()
    project = client.get_project(name=f"projects/{project_id}")
    return project.name.split("/")[1]  # Format is "projects/{project_number}"

def save_dataframe_as_csv(df, fin_asset, conf):
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
    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
        # Save the file to a temporary location
        csv_string = df.to_csv(index=False, sep="|")
        credentials, project_id = default()
        project_number = get_project_number(project_id)
        # Upload the file to GCS
        client = storage.Client()
        bucket_url = f"data-{project_number}"
        bucket = client.bucket(bucket_url)
        blob = bucket.blob(filename)
        blob.upload_from_string(csv_string)

        return f"File saved to GCS bucket '{bucket_url}' as '{filename}'.\n"
    else:
        # Save the file locally
        file = os.path.join(os.path.dirname(__file__), '..','data', filename)
        df.to_csv(file, index=False, sep="|")
        return(f"File saved locally as '{filename}'.\n")

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
        print(f'Moved: {file_name}\n')

def move_csv_file(source_dir, destination_dir, file):

    filename = file.split("/")[-1]
    source_file = os.path.join(os.path.dirname(__file__), '..', source_dir, filename)
    destination_file = os.path.join(os.path.dirname(__file__), '..', destination_dir, filename)
    shutil.move(source_file, destination_file)
    print(f'File {filename} moved to {destination_dir}\n')


def move_csv_files_gcp(source_bucket_name, destination_bucket_name, pattern):
    # Initialize the storage client
    storage_client = storage.Client()
    # Get the source and destination buckets
    source_bucket = storage_client.bucket(source_bucket_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)

    # List all blobs (files) in the source bucket
    blobs = [blob for blob in source_bucket.list_blobs() if blob.name.startswith(pattern)]

    for blob in blobs:
        # Get the source blob
        source_blob = source_bucket.blob(blob.name)

        # Copy the blob to the destination bucket
        # destination_blob = destination_bucket.blob(blob.name)
        source_bucket.copy_blob(source_blob, destination_bucket, blob.name)

        # Delete the blob from the source bucket
        source_blob.delete()

        print(f'Moved {blob.name} from {source_bucket_name} to {destination_bucket_name}')

def move_csv_file_gcp(source_bucket_name, destination_bucket_name, filename):
    storage_client = storage.Client()
    source_bucket = storage_client.bucket(source_bucket_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)
    source_blob = source_bucket.blob(filename)
    source_bucket.copy_blob(source_blob, destination_bucket, filename)
    source_blob.delete()
    print(f'Moved {filename} from {source_bucket_name} to {destination_bucket_name}')

# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete

# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):

    with duckdb.connect(os.path.join(os.path.dirname(__file__), '..', db_path)) as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df where FALSE")  # Create table if not exists
        con.execute(f"INSERT INTO {table} SELECT * FROM df")

def process_files(conf, files, asset):
    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):  # GCP cloud function environment
        for f in files:
            content = f.download_as_text()
            df = pd.read_csv(io.StringIO(content), sep='|')
            credentials, project_id = default()
            project_number = get_project_number(project_id)
            bucket_url1 = f"data-{project_number}"
            bucket_url2 = f"archive-{project_number}"
            insert_into_bigquery(df, project_id, 'stocks', asset)
            move_csv_file_gcp(bucket_url1, bucket_url2, f.name)

    else:
        for f in files:
            df = pd.read_csv(f, sep='|')
            insert_into_duckdb(df, conf['duckdb']['database'], asset)
            move_csv_file(conf["csv_directory"], conf["archive"], f)

# Define a function to load CSV files based on today's date
def load_files(config, asset):

    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
        credentials, project_id = default()
        project_number = get_project_number(project_id)
        bucket_uri = f"data-{project_number}"
        bucket = storage.Client().bucket(bucket_uri)
        return bucket.list_blobs(prefix=asset)

    else:
        return glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '', config['csv_directory']), f"{asset}*.csv"))
