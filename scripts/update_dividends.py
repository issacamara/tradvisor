import os, io
import glob
import yaml
import pandas as pd
from google.cloud import bigquery, storage

import duckdb
from helper import move_csv_files, move_csv_files_gcp
from google.auth import default


# Define a function to load CSV files based on today's date
def load_files(config):

    if config['environment'] == 'gcp':
        bucket = storage.Client().bucket(config['gcp']['gcs']['bucket'])
        return bucket.list_blobs(prefix='DIVIDENDS')

    else:
        return glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '', config['csv_directory']), "DIVIDENDS*.csv"))


# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete


# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):

    with duckdb.connect(os.path.join(os.path.dirname(__file__), '..', db_path)) as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df")  # Create table if not exists
        con.execute(f"INSERT INTO {table} SELECT * FROM df")

# Define a function to process each CSV file
def process_csv_files(files, conf):
    if conf['environment'] == "gcp":
        for f in files:
            content = f.download_as_text()
            df = pd.read_csv(io.StringIO(content), sep='|')
            _, project_id = default()
            insert_into_bigquery(df, project_id, conf['gcp']['bigquery']['dataset'], 'DIVIDENDS')

    else:
        for f in files:
            df = pd.read_csv(f, sep='|')
            insert_into_duckdb(df, conf['duckdb']['database'], 'DIVIDENDS')

def entry_point(request=None):
    # Load configuration from YAML file
    with open("config.yml", 'r') as file:
        config = yaml.safe_load(file)

    # Determine the environment

    asset = "DIVIDENDS"

    # Load CSV files
    csv_files = load_files(config)

    # Process each CSV file
    process_csv_files(csv_files, config)
    if config['environment'] == 'gcp':
        move_csv_files_gcp(config["gcp"]['gcs']['bucket'],config["gcp"]['gcs']['archive'],asset)
    else:
        move_csv_files(config["csv_directory"],config["archive"],asset)

    return "Data insertion successfully completed !\n"

# print(entry_point())

