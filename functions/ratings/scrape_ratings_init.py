from __future__ import annotations

import functions_framework
import yaml
from helper import save_dataframe_as_csv
from ingestion_observability import observed_entrypoint

from scrape_ratings import RATINGS_URL, scrape_ratings


def scrape_ratings_init(url=RATINGS_URL, *, collected_at=None):
    """Initial load uses the same complete, revision-stable history contract."""
    return scrape_ratings(url, collected_at=collected_at)


@functions_framework.http
@observed_entrypoint("ingestion.ratings.initialize")
def entry_point(request=None):
    from ingestion_configuration import IngestionConfiguration, source_endpoints

    configuration = IngestionConfiguration.from_environment()
    with open("config.yml", "r") as file:
        endpoints = source_endpoints(yaml.safe_load(file))
    frame = scrape_ratings_init(endpoints["ratings"])
    if frame.empty:
        return "No ratings data to collect.\n"
    return save_dataframe_as_csv(frame, "ratings", configuration)


if __name__ == "__main__":
    print(entry_point())
