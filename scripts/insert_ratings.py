import os
import functions_framework
import yaml
from helper import process_files, load_files
from google.cloud import bigquery
from google.auth import default


def cleanup_old_ratings():
    """Keep only the latest 2 years of ratings for each symbol."""
    credentials, project_id = default()
    client = bigquery.Client(credentials=credentials, project=project_id)
    
    # Get current year
    from datetime import datetime
    current_year = datetime.now().year
    min_year = current_year - 1  # Keep current year and previous year
    
    # Delete records older than min_year
    query = f"""
        DELETE FROM `{project_id}.stocks.ratings`
        WHERE rating_year < {min_year}
    """
    
    try:
        query_job = client.query(query)
        query_job.result()
        print(f"Cleaned up ratings older than {min_year}")
    except Exception as e:
        print(f"Cleanup error (may be empty table): {e}")


@functions_framework.http
def entry_point(request=None):
    # Load configuration from YAML file
    with open("config.yml", 'r') as file:
        config = yaml.safe_load(file)

    # Cleanup old ratings (keep only latest 2 years)
    cleanup_old_ratings()

    asset = "ratings"
    csv_files = load_files(config, asset)
    process_files(config, csv_files, asset)

    return "Data insertion successfully completed !\n"

if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
    pass
else:
    print(entry_point())
