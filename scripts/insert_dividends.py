import os
import io
import functions_framework
import yaml
from google.cloud import storage
from google.cloud import bigquery
from google.auth import default
import pandas as pd

from helper import load_files, upsert_into_bigquery, get_project_number


@functions_framework.http
def entry_point(request=None):
    # Load configuration from YAML file
    with open("config.yml", 'r') as file:
        config = yaml.safe_load(file)

    asset = "dividends"  # lowercase table name
    process_dividends(config, asset)

    return "Data upsert successfully completed !\n"


def cleanup_old_dividends(project_id, dataset, table, years_to_keep=5):
    """Delete dividend records older than the specified number of years for each symbol.
    
    Keeps only the most recent 5 years of data for each symbol.
    """
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    
    # Delete old records - keep only last 5 years of data per symbol
    # Example: If today is 2025-01-01, keep data from 2021 onwards (2021,2022,2023,2024,2025)
    # Formula: current_year - (years_to_keep - 1) = 2025 - 4 = 2021
    delete_query = f"""
    DELETE FROM `{table_id}`
    WHERE fiscal_year < EXTRACT(YEAR FROM CURRENT_DATE()) - {years_to_keep - 1}
    """
    
    query_job = client.query(delete_query)
    query_job.result()
    
    print(f"Cleaned up dividend records older than {years_to_keep} years")


def process_dividends(conf, asset):
    """Process dividend CSV files and upsert into BigQuery."""
    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):  # GCP cloud function environment
        credentials, project_id = default()
        project_number = get_project_number(project_id)
        bucket_url1 = f"data-{project_number}"
        bucket_url2 = f"archive-{project_number}"
        bucket = storage.Client().bucket(bucket_url1)
        
        # Process each file in the bucket
        blobs = list(bucket.list_blobs(prefix=asset))
        for blob in blobs:
            if blob.name.endswith('.csv'):
                content = blob.download_as_text()
                df = pd.read_csv(io.StringIO(content), sep='|')
                rows_count = len(df)  # Get row count before upsert
                # Upsert with symbol and fiscal_year as primary keys
                upsert_into_bigquery(df, project_id, 'stocks', asset, ['symbol', 'fiscal_year'])
                print(f"Upserted {rows_count} rows into {asset} table")
                # Move to archive
                from helper import move_csv_file_gcp
                move_csv_file_gcp(bucket_url1, bucket_url2, blob.name)

        # Cleanup old records - keep only last 5 years
        cleanup_old_dividends(project_id, 'stocks', asset, years_to_keep=5)
    else:
        # Local development
        from helper import move_csv_file
        import glob
        files = glob.glob(os.path.join(os.path.dirname(__file__), '..', conf['csv_directory'], f"{asset}*.csv"))
        for f in files:
            df = pd.read_csv(f, sep='|')
            # For local, use DuckDB (no upsert needed for local)
            from helper import insert_into_duckdb
            insert_into_duckdb(df, conf['duckdb']['database'], asset)
            move_csv_file(conf["csv_directory"], conf["archive"], f)


if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
    pass
else:
    print(entry_point())

