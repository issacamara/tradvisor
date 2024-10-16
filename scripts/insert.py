import os
import glob
import yaml
import pandas as pd
from google.cloud import bigquery
import duckdb
from datetime import datetime
# Load configuration from YAML file
with open('../config.yml', 'r') as file:
    config = yaml.safe_load(file)

# Determine the environment
environment = config['environment']

# Define a function to load CSV files based on today's date
def load_csv_files(directory):

    today_date = datetime.today().strftime('%Y-%m-%d')
    csv_files = glob.glob(os.path.join(f"../{directory}", f"*{today_date}*.csv"))
    return csv_files

# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete

# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):
    con = duckdb.connect(f"../{db_path}")
    con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df")  # Create table if not exists
    con.execute(f"INSERT INTO {table} SELECT * FROM df")

# Define a function to process each CSV file
def process_csv_files(csv_files, config):
    for file in csv_files:
        df = pd.read_csv(file, sep='|')
        if "bonds" in file.lower():
            table_key = 'bonds'
        elif "shares" in file.lower():
            table_key = 'shares'
        elif "dividends" in file.lower():
            table_key = 'dividends'
        elif "indices" in file.lower():
            table_key = 'indices'
        else:
            continue

        if environment == "GCP":
            table = config['bigquery']['tables'][table_key]
            insert_into_bigquery(df, config['bigquery']['project_id'], config['bigquery']['dataset'], table)
        elif environment == "on-premise":
            table = config['duckdb']['tables'][table_key]
            insert_into_duckdb(df, config['duckdb']['database'], table)

# Load CSV files
csv_files = load_csv_files(config['csv_directory'])

# Process each CSV file
process_csv_files(csv_files, config)

print("Data insertion completed.")