from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scraper = _load_script("share_scraper_for_tests", "scrape_shares.py")
loader = _load_script("share_loader_for_tests", "insert_shares.py")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 234,5600", "1234.5600"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("0,000001", "0.000001"),
    ],
)
def test_localized_decimal_preserves_supported_precision(value: str, expected: str) -> None:
    assert format(scraper.parse_localized_decimal(value), "f") == expected


def test_invalid_or_negative_decimal_is_not_silently_rewritten() -> None:
    with pytest.raises(ValueError):
        scraper.parse_localized_decimal("12,3,4")
    with pytest.raises(ValueError):
        scraper.parse_localized_decimal("-1,25")


def test_scraper_preserves_raw_values_collection_time_and_unknown_session(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "scrape",
        lambda _url: [
            {
                "symbol": "ABC",
                "name": "Example",
                "open": "1 000,25",
                "high": "1 100,50",
                "low": "900,00",
                "volume": "0",
                "close": "1 050,75",
            }
        ],
    )
    first = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 9, 22, 8, tzinfo=timezone.utc)
    )
    retry = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 9, 22, 8, 1, tzinfo=timezone.utc)
    )

    observation = first.iloc[0]
    assert observation["open"] == "1 000,25"
    assert observation["parsed_open"] == "1000.25"
    assert observation["session_date"] == ""
    assert observation["session_date_status"] == "unknown"
    assert observation["trade_status"] == "unknown"
    assert observation["collected_at"] == "2026-09-22T08:00:00Z"
    assert observation["observation_id"] != retry.iloc[0]["observation_id"]


def test_scraper_archival_payload_retains_unparseable_raw_value(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "scrape",
        lambda _url: [
            {
                "symbol": "ABC",
                "name": "Example",
                "open": "1 000,25",
                "high": "not published",
                "low": "900,00",
                "volume": "12",
                "close": "1 050,75",
            }
        ],
    )
    row = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc)
    ).iloc[0]

    assert row["high"] == "not published"
    assert row["numeric_parse_status"] == "invalid"
    assert row["numeric_parse_errors"] == "high"


def test_same_day_scrapes_preserve_each_raw_evidence_file(tmp_path, monkeypatch) -> None:
    scripts = tmp_path / "scripts"
    data = tmp_path / "data"
    scripts.mkdir()
    data.mkdir()
    monkeypatch.setattr(scraper, "__file__", str(scripts / "scrape_shares.py"))
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)
    collected_at = datetime(2026, 9, 22, 8, tzinfo=timezone.utc)

    first_result = scraper._save_raw_observations(
        pd.DataFrame([{"symbol": "ABC", "close": "1 050,75"}]), collected_at
    )
    second_result = scraper._save_raw_observations(
        pd.DataFrame([{"symbol": "ABC", "close": "1 051,00"}]), collected_at
    )
    files = sorted(data.glob("shares-2026-09-22*.csv"))
    contents = {path.read_text() for path in files}

    assert first_result != second_result
    assert len(files) == 2
    assert any("1 050,75" in content for content in contents)
    assert any("1 051,00" in content for content in contents)


def _row(**updates):
    row = {
        "symbol": "ABC",
        "name": "Example",
        "open": "1 000,25",
        "high": "1 100,50",
        "low": "900,00",
        "volume": "12",
        "close": "1 050,75",
        "session_date": "2026-09-21",
        "session_date_status": "verified",
        "trade_status": "traded",
        "collected_at": "2026-09-22T08:00:00Z",
        "observation_id": "observation-1",
    }
    row.update(updates)
    return row


def test_missing_or_runtime_only_dates_never_reach_normalized_load() -> None:
    rows = pd.DataFrame(
        [
            _row(session_date="", session_date_status="unknown"),
            _row(session_date="2026-09-22", session_date_status="unknown"),
            _row(session_date="not-a-date", session_date_status="verified"),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert normalized.empty
    assert evidence["missing_session_evidence"] == 3


def test_zero_volume_unknown_status_is_withheld_even_with_verified_date() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(volume="0", trade_status="unknown")])
    )

    assert normalized.empty
    assert evidence["unknown_trade_status"] == 1


def test_unique_verified_traded_observation_normalizes_exactly() -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([_row()]))

    assert evidence["loadable"] == 1
    assert normalized.loc[0, "date"].isoformat() == "2026-09-21"
    assert str(normalized.loc[0, "open"]) == "1000.25"
    assert normalized.loc[0, "volume"] == 12


def test_duplicate_or_revision_rows_are_withheld_with_explicit_evidence() -> None:
    rows = pd.DataFrame(
        [
            _row(observation_id="revision-a", source_revision_id="source-a"),
            _row(close="1 051,00", observation_id="revision-b", source_revision_id="source-b"),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert normalized.empty
    assert evidence["duplicate_or_revision_unknown"] == 2


def test_invalid_numeric_values_are_withheld_from_normalized_load() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(high="unavailable", numeric_parse_status="invalid")])
    )

    assert normalized.empty
    assert evidence["invalid_numeric_observation"] == 1


def test_unsupported_price_precision_is_not_rounded_into_contract() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(close="1 050,1234567")])
    )

    assert normalized.empty
    assert evidence["invalid_numeric_observation"] == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"close": "0"},
        {"open": "0"},
        {"high": "0"},
        {"low": "0"},
        {"close": "1 200,00"},
        {"high": "850,00"},
        {"low": "1 200,00"},
        {"open": "1 200,00"},
        {"high": "", "low": "900,00"},
        {"high": "1 100,50", "low": "", "open": ""},
    ],
)
def test_nonpositive_or_impossible_ohlc_is_withheld(updates) -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([_row(**updates)]))

    assert normalized.empty
    assert evidence["invalid_numeric_observation"] == 1


def test_close_only_observation_keeps_permitted_missing_candle_fields() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(open="", high="", low="")])
    )

    assert evidence["loadable"] == 1
    assert pd.isna(normalized.loc[0, "open"])
    assert pd.isna(normalized.loc[0, "high"])
    assert pd.isna(normalized.loc[0, "low"])


def test_raw_file_is_archived_when_no_observation_is_loadable(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "unused"
    helper.insert_into_bigquery = lambda *_args: calls.append("bigquery")
    helper.insert_into_duckdb = lambda *_args: calls.append("duckdb")
    helper.move_csv_file = lambda *args: calls.append(("archive", *args))
    helper.move_csv_file_gcp = lambda *_args: calls.append("gcs-archive")
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)

    evidence = loader._archive_after_optional_load(
        {"duckdb": {"database": "unused"}, "csv_directory": "data", "archive": "archive"},
        "raw-observations.csv",
        pd.DataFrame([_row(session_date="", session_date_status="unknown")]),
        "shares",
    )

    assert evidence["loadable"] == 0
    assert calls == [("archive", "data", "archive", "raw-observations.csv")]


def test_load_requires_explicit_session_and_source_columns() -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([{"symbol": "ABC"}]))

    assert normalized.empty
    assert evidence["missing_session_evidence"] == 1
