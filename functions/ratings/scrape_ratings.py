from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import functions_framework
import pandas as pd
import yaml
from bs4 import BeautifulSoup
from curl_cffi import requests
from helper import get_symbols_from_richbourse, save_dataframe_as_csv


RATINGS_URL = "https://www.richbourse.com/common/notation-financiere/index"
RATING_COLUMNS = (
    "symbol",
    "agency",
    "scale",
    "subject",
    "rating_period",
    "rating_year",
    "effective_date",
    "effective_date_status",
    "rating_short_term",
    "rating_long_term",
    "collected_at",
    "source_revision_id",
)


def _source_revision_id(record):
    identity = {
        key: record.get(key)
        for key in (
            "symbol",
            "agency",
            "rating_period",
            "rating_short_term",
            "rating_long_term",
        )
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalized_rating(record, collected_at):
    period = str(record.get("rating_period") or "").strip()
    year_text = period[-4:] if len(period) >= 4 else ""
    year = int(year_text) if year_text.isdigit() else None
    normalized = {
        "symbol": record.get("symbol"),
        "agency": record.get("agency") or None,
        "scale": record.get("scale") or None,
        "subject": record.get("subject") or None,
        "rating_period": period or None,
        "rating_year": year,
        # Month/year source labels are not precise enough to establish an effective day.
        "effective_date": record.get("effective_date") or None,
        "effective_date_status": "verified" if record.get("effective_date") else "unknown",
        "rating_short_term": record.get("rating_short_term") or None,
        "rating_long_term": record.get("rating_long_term") or None,
        "collected_at": collected_at,
    }
    normalized["source_revision_id"] = _source_revision_id(normalized)
    return normalized


def get_ratings_for_symbol(symbol, *, collected_at=None):
    """Return source-labeled rating observations without ordinal interpretation."""
    url = f"{RATINGS_URL}?symbole={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.7,en;q=0.6",
        "Referer": RATINGS_URL,
    }
    response = requests.Session().get(
        url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True
    )
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find(
        "table",
        {"class": lambda value: value and "table-striped" in value and "table-bordered" in value},
    )
    body = table.find("tbody") if table else None
    if body is None:
        return []

    observed_at = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    observations = []
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        agency = cells[0].get_text(" ", strip=True) or None
        period = cells[1].get_text(" ", strip=True) or None
        short_label = cells[2].get_text(" ", strip=True) or None
        long_label = cells[3].get_text(" ", strip=True) or None
        if not (short_label or long_label):
            continue
        observations.append(
            _normalized_rating(
                {
                    "symbol": symbol,
                    "agency": agency,
                    "scale": None,
                    "subject": None,
                    "rating_period": period,
                    "effective_date": None,
                    "rating_short_term": short_label,
                    "rating_long_term": long_label,
                },
                observed_at,
            )
        )
    return observations


def scrape_ratings(url=RATINGS_URL, *, collected_at=None):
    """Collect the source's rating history; replay is deduplicated by revision."""
    observed_at = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    observations = []
    for symbol in get_symbols_from_richbourse(url):
        observations.extend(get_ratings_for_symbol(symbol, collected_at=observed_at))
    return pd.DataFrame(observations, columns=RATING_COLUMNS)


@functions_framework.http
def entry_point(request=None):
    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)
    frame = scrape_ratings(config["url"].get("ratings", RATINGS_URL))
    if frame.empty:
        return "No ratings data to collect.\n"
    return save_dataframe_as_csv(frame, "ratings", config)


if __name__ == "__main__":
    print(entry_point())
