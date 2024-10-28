import sys, os
sys.path.insert(1, "/".join(os.path.realpath(__file__).split("/")[0:-2]))
import glob
import yaml
import pandas as pd
from google.cloud import bigquery
import duckdb
from helper import move_csv_files

config_file = os.path.join(os.path.dirname(__file__), '..', 'config.yml')

# Load configuration from YAML file
with open(config_file, 'r') as file:
    config = yaml.safe_load(file)

# Determine the environment
environment = config['environment']
product = "SHARES"
# Define a function to load CSV files based on today's date
def load_shares_files(directory):

    csv_files = glob.glob(os.path.join(f"../{directory}", f"{product}*.csv"))
    return csv_files

# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete

def calculate_indicators(data):
    symbols = set(data['SYMBOL'])
    return

# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):
    with duckdb.connect(f"../{db_path}") as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df")  # Create table if not exists
        con.execute(f"INSERT INTO {table} SELECT * FROM df")

# Define a function to process each CSV file
def process_csv_files(csv_files, config):
    for file in csv_files:
        df = pd.read_csv(file, sep='|')

        if environment == "GCP":
            insert_into_bigquery(df, config['bigquery']['project_id'], config['bigquery']['dataset'], product)
        elif environment == "on-premise":
            insert_into_duckdb(df, config['duckdb']['database'], product)



# Load CSV files
csv_files = load_shares_files(config['csv_directory'])

# Process each CSV file
process_csv_files(csv_files, config)

move_csv_files(config["csv_directory"],config["archive"],product)

print("Data insertion completed.")