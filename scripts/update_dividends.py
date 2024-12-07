import os, io
import glob
import yaml
import pandas as pd
from google.cloud import bigquery
import duckdb
from helper import move_csv_files
from google.cloud import bigquery, storage

# config_file = os.path.join(os.path.dirname(__file__), '..', 'config.yml')

# Load configuration from YAML file
with open('config.yml', 'r') as file:
    config = yaml.safe_load(file)

# Determine the environment
environment = config['environment']
product = "DIVIDENDS"
# Define a function to load CSV files based on today's date
def load_files(directory):
    if environment == 'cloud':
        bucket = storage.Client().bucket(config['gcp']['gcs']['bucket'])
        return bucket.list_blobs(prefix=product)

    else:
        return glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '..', directory), f"{product}*.csv"))

# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete

# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):
    with duckdb.connect(f"../{db_path}") as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df")  # Create table if not exists
        con.execute(f"TRUNCATE TABLE {table}") # deletes all row
        con.execute(f"INSERT INTO {table} SELECT * FROM df")

# Define a function to process each CSV file
def process_csv_files(files, conf):
    if environment == "cloud":
        for f in files:
            content = f.download_as_text()
            df = pd.read_csv(io.StringIO(content), sep='|')
            insert_into_bigquery(df, conf['gcp']['project_id'], conf['gcp']['bigquery']['dataset'], product)

    else:
        for f in files:
            df = pd.read_csv(f, sep='|')
            insert_into_duckdb(df, conf['duckdb']['database'], product)

# Load CSV files
csv_files = load_files(config['csv_directory'])

# Process each CSV file
process_csv_files(csv_files, config)

# move_csv_files(config["csv_directory"],config["archive"],product)

print("Data insertion completed.")