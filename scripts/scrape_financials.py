import yaml
from datetime import datetime
import functions_framework
from google.auth import default
from google.cloud import storage

from helper import get_symbols_from_richbourse, get_project_number
from scrape_financials_init import get_announcements_for_symbol, download_and_save_pdf_to_gcs, FINANCIALS_URL

def scrape_financials(url):
    previous_fiscal_year = datetime.now().year - 1
    credentials, project_id = default()
    project_number = get_project_number(project_id)
    storage_client = storage.Client()
    bucket = storage_client.bucket(f"data-{project_number}")

    symbols = get_symbols_from_richbourse(url)
    for symbol in symbols:
        announcements = get_announcements_for_symbol(symbol, min_year=previous_fiscal_year, single_year_only=True)
        for ann in announcements:
            download_and_save_pdf_to_gcs(ann, bucket)

@functions_framework.http
def entry_point(request=None):
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    url = config['url'].get('financials', FINANCIALS_URL)
    scrape_financials(url)
    return f"Scraped PDFs for previous fiscal year into GCS.\n"

if __name__ == "__main__":
    print(entry_point())