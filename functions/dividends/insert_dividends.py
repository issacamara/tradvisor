import io
import functions_framework
import pandas as pd

from helper import get_project_number, upsert_and_archive


@functions_framework.http
def entry_point(request=None):
    asset = "dividends"  # lowercase table name
    from ingestion_configuration import IngestionConfiguration

    configuration = IngestionConfiguration.from_environment()
    process_dividends(configuration, asset)

    return "Data upsert successfully completed !\n"


def cleanup_old_dividends(project_id, dataset, table, years_to_keep=5):
    """Delete dividend records older than the specified number of years for each symbol.
    
    Keeps only the most recent 5 years of data for each symbol.
    """
    from google.cloud import bigquery

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


def process_dividends(configuration, asset):
    """Process dividend CSV files and upsert into BigQuery."""
    from google.auth import default
    from google.cloud import storage

    credentials, project_id = default()
    if configuration is not None:
        configuration.validate_application_default_project(project_id)
        source_bucket = configuration.data_bucket
        archive_bucket = configuration.archive_bucket
        dataset = configuration.dataset
        table = configuration.table_for(asset).rsplit(".", 1)[1]
    else:
        if not project_id:
            raise RuntimeError("cloud ingestion requires an application-default project")
        project_number = get_project_number(project_id)
        source_bucket = f"data-{project_number}"
        archive_bucket = f"archive-{project_number}"
        dataset = "stocks"
        table = asset
    blobs = storage.Client(credentials=credentials, project=project_id).bucket(
        source_bucket
    ).list_blobs(prefix=asset)
    for blob in blobs:
        if blob.name.endswith(".csv"):
            df = pd.read_csv(io.StringIO(blob.download_as_text()), sep="|")

            def archive_csv(blob_name=blob.name):
                from helper import move_csv_file_gcp

                move_csv_file_gcp(source_bucket, archive_bucket, blob_name)

            upsert_and_archive(
                df, project_id, dataset, table, ["payment_id"], archive_csv
            )
            print(f"Upserted {len(df)} rows into {asset} table")


if __name__ == "__main__":
    print(entry_point())
