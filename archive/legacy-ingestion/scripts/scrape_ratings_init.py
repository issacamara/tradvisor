from __future__ import annotations

import functions_framework
import yaml
from helper import save_dataframe_as_csv

from scrape_ratings import RATINGS_URL, scrape_ratings


def scrape_ratings_init(url=RATINGS_URL, *, collected_at=None):
    """Initial load uses the same complete, revision-stable history contract."""
    return scrape_ratings(url, collected_at=collected_at)


@functions_framework.http
def entry_point(request=None):
    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)
    frame = scrape_ratings_init(config["url"].get("ratings", RATINGS_URL))
    if frame.empty:
        return "No ratings data to collect.\n"
    return save_dataframe_as_csv(frame, "ratings", config)


if __name__ == "__main__":
    print(entry_point())
