from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts" / "scrape_ratings.py"

bs4 = types.ModuleType("bs4")
bs4.BeautifulSoup = object
sys.modules["bs4"] = bs4
curl_cffi = types.ModuleType("curl_cffi")
curl_cffi.requests = types.SimpleNamespace(Session=object)
sys.modules["curl_cffi"] = curl_cffi
framework = types.ModuleType("functions_framework")
framework.http = lambda function: function
sys.modules["functions_framework"] = framework
sys.modules["yaml"] = types.ModuleType("yaml")
helper = types.ModuleType("helper")
helper.get_symbols_from_richbourse = lambda url: []
helper.save_dataframe_as_csv = lambda dataframe, asset, config: dataframe
sys.modules["helper"] = helper

spec = importlib.util.spec_from_file_location("scrape_ratings", SCRIPT)
assert spec is not None and spec.loader is not None
ratings = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ratings
spec.loader.exec_module(ratings)


def test_rating_keeps_source_context_and_does_not_infer_effective_day() -> None:
    result = ratings._normalized_rating(
        {
            "symbol": "ABC",
            "agency": "Agency A",
            "scale": "local",
            "subject": "issuer",
            "rating_period": "FY 2024",
            "effective_date": None,
            "rating_short_term": "A-2",
            "rating_long_term": "A",
        },
        "2025-01-02T08:00:00+00:00",
    )

    assert result["symbol"] == "ABC"
    assert result["agency"] == "Agency A"
    assert result["scale"] == "local"
    assert result["subject"] == "issuer"
    assert result["rating_year"] == 2024
    assert result["effective_date"] is None
    assert result["effective_date_status"] == "unknown"
    assert result["rating_short_term"] == "A-2"
    assert result["rating_long_term"] == "A"


def test_revision_identity_is_stable_across_replay_collection_times() -> None:
    record = {
        "symbol": "ABC",
        "agency": "Agency A",
        "scale": "global",
        "subject": "issuer",
        "rating_period": "2024",
        "effective_date": "2024-12-01",
        "rating_short_term": None,
        "rating_long_term": "BBB",
    }
    first = ratings._normalized_rating(record, "2025-01-01T00:00:00+00:00")
    replay = ratings._normalized_rating(record, "2025-01-03T00:00:00+00:00")

    assert first["source_revision_id"] == replay["source_revision_id"]
    assert first["collected_at"] != replay["collected_at"]
