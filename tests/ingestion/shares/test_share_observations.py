from __future__ import annotations

import inspect
import importlib.util
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
from backend.contracts.analytical_storage import SHARE_PRICE_REVISIONS_V1


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
actual_helper = _load_script("share_helper_for_signature_tests", "helper.py")


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


@pytest.mark.parametrize("value", ["1.23,45", "12,34.56", "1,23,456", "1 23,45"])
def test_malformed_separator_grouping_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        scraper.parse_localized_decimal(value)


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
    assert observation["source_revision_id"] == retry.iloc[0]["source_revision_id"]
    assert observation["source_id"] == "richbourse-shares"
    assert observation["parser_version"] == "shares-parser-v1"
    assert observation["basis"] == "actual"
    assert observation["price_basis_ref"] == "raw-v1"


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


def test_scraper_preserves_raw_malformed_grouping_as_invalid(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "scrape",
        lambda _url: [
            {
                "symbol": "ABC",
                "name": "Example",
                "open": "1.23,45",
                "high": "1 100,50",
                "low": "900,00",
                "volume": "12",
                "close": "1 050,75",
            }
        ],
    )
    row = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc)
    ).iloc[0]

    assert row["open"] == "1.23,45"
    assert row["parsed_open"] == ""
    assert row["numeric_parse_status"] == "invalid"
    assert row["numeric_parse_errors"] == "open"


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
        "open": "1 000,25",
        "high": "1 100,50",
        "low": "900,00",
        "volume": "12",
        "close": "1 050,75",
        "session_date": "2026-09-21",
        "session_date_status": "verified",
        "trade_status": "traded",
        "collected_at": "2026-09-22T08:00:00Z",
        "known_at": "2026-09-22T08:00:00Z",
        "observation_id": "observation-1",
        "source_id": "richbourse-shares",
        "source_revision_id": "source-revision-1",
        "parser_version": "shares-parser-v1",
        "basis": "actual",
        "original_source_date": "2026-09-21",
        "price_basis_ref": "raw-v1",
        "suspension_status": "unknown",
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
    assert normalized.loc[0, "session_date"].isoformat() == "2026-09-21"
    assert str(normalized.loc[0, "high"]) == "1100.50"
    assert normalized.loc[0, "volume"] == 12
    assert normalized.loc[0, "source_observation_id"] == "observation-1"
    assert normalized.loc[0, "collected_at"] == "2026-09-22 08:00:00"
    assert pd.isna(normalized.loc[0, "validated_available_at"])
    assert len(normalized.loc[0, "revision_id"]) == 64


def test_normalized_rows_match_immutable_share_revision_contract() -> None:
    normalized, _ = loader.prepare_normalized_rows(pd.DataFrame([_row()]))

    assert loader.REVISION_TABLE == SHARE_PRICE_REVISIONS_V1.table_name
    assert loader.REVISION_KEYS == SHARE_PRICE_REVISIONS_V1.immutable_key
    assert tuple(normalized.columns) == tuple(
        field.name for field in SHARE_PRICE_REVISIONS_V1.fields
    )
    assert normalized.loc[0, "session_date"].isoformat() == "2026-09-21"
    assert normalized.loc[0, "original_source_date"].isoformat() == "2026-09-21"
    assert normalized.loc[0, "basis"] == "actual"
    assert normalized.loc[0, "price_basis_ref"] == "raw-v1"
    assert normalized.loc[0, "source_id"] == "richbourse-shares"


@pytest.mark.parametrize(
    "field",
    ["source_id", "source_revision_id", "known_at", "basis", "price_basis_ref"],
)
def test_missing_contract_evidence_withholds_normalized_row(field: str) -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(**{field: ""}, original_source_date="")])
    )

    assert normalized.empty
    assert evidence["missing_contract_evidence"] == 1


def test_exact_retry_is_collapsed_but_changed_price_revision_is_retained() -> None:
    rows = pd.DataFrame(
        [
            _row(observation_id="revision-a", source_revision_id="source-a"),
            _row(observation_id="revision-a", source_revision_id="source-a"),
            _row(close="1 051,00", observation_id="revision-b", source_revision_id="source-b"),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert evidence["loadable"] == 2
    assert evidence["exact_retry_duplicates"] == 1
    assert evidence["duplicate_or_revision_unknown"] == 0
    assert normalized[["symbol", "session_date"]].drop_duplicates().shape[0] == 1
    assert normalized["revision_id"].nunique() == 2
    assert set(normalized["source_revision_id"]) == {"source-a", "source-b"}
    assert {str(value) for value in normalized["close"]} == {"1050.75", "1051.00"}


def test_revision_identity_ignores_recollection_metadata_but_tracks_business_changes() -> None:
    rows = pd.DataFrame(
        [
            _row(
                observation_id="observation-first",
                collected_at="2026-09-22T08:00:00Z",
                known_at="2026-09-22T08:01:00Z",
            ),
            _row(
                observation_id="observation-retry",
                collected_at="2026-09-23T08:00:00Z",
                known_at="2026-09-23T08:01:00Z",
            ),
            _row(
                observation_id="observation-correction",
                collected_at="2026-09-23T08:00:00Z",
                known_at="2026-09-23T08:01:00Z",
                close="1 051,00",
            ),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert evidence["loadable"] == 2
    assert evidence["exact_retry_duplicates"] == 1
    assert normalized["revision_id"].nunique() == 2
    assert set(normalized["source_observation_id"]) == {
        "observation-first",
        "observation-correction",
    }


def test_untraceable_revision_is_withheld_without_inventing_evidence() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(observation_id="", source_revision_id="")])
    )

    assert normalized.empty
    assert evidence["duplicate_or_revision_unknown"] == 1


def test_invalid_numeric_values_are_withheld_from_normalized_load() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(high="unavailable", numeric_parse_status="invalid")])
    )

    assert normalized.empty
    assert evidence["invalid_numeric_observation"] == 1


def test_invalid_traded_volume_is_withheld_instead_of_aborting_file() -> None:
    normalized, evidence = loader.prepare_normalized_rows(
        pd.DataFrame([_row(volume="not published", numeric_parse_status="invalid")])
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
    assert pd.isna(normalized.loc[0, "high"])
    assert pd.isna(normalized.loc[0, "low"])


def test_raw_file_is_archived_when_no_observation_is_loadable(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "unused"
    helper.move_csv_file = lambda *args: calls.append(("archive", *args))
    helper.move_csv_file_gcp = lambda *_args: calls.append("gcs-archive")
    helper.upsert_into_bigquery = lambda *_args: calls.append("bigquery")
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setattr(
        loader,
        "_insert_revisions_into_duckdb",
        lambda *_args: calls.append("duckdb"),
    )
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


def test_cloud_load_uses_actual_helper_signature_and_revision_keys(monkeypatch) -> None:
    signature = inspect.signature(actual_helper.upsert_into_bigquery)
    signature.bind(
        pd.DataFrame(),
        "project",
        "stocks",
        loader.REVISION_TABLE,
        list(loader.REVISION_KEYS),
        update_matched=False,
    )

    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    helper.move_csv_file = lambda *_args: calls.append("local-archive")
    helper.move_csv_file_gcp = lambda *args: calls.append(("gcs-archive", *args))

    def upsert(
        frame,
        project_id,
        dataset,
        table,
        primary_keys,
        *,
        update_matched=True,
    ):
        calls.append(
            (
                "upsert",
                len(frame),
                project_id,
                dataset,
                table,
                tuple(primary_keys),
                update_matched,
                frame.loc[0, "validated_available_at"],
            )
        )

    helper.upsert_into_bigquery = upsert
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    evidence = loader._archive_after_optional_load(
        {},
        SimpleNamespace(name="shares.csv"),
        pd.DataFrame([_row()]),
        "shares",
        commit_clock=lambda: datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
    )

    assert evidence["loadable"] == 1
    assert calls == [
        (
            "upsert",
            1,
            "project",
            "stocks",
            loader.REVISION_TABLE,
            loader.REVISION_KEYS,
            False,
            "2026-09-24 12:00:00",
        ),
        ("gcs-archive", "data-123", "archive-123", "shares.csv"),
    ]


def test_cloud_load_withholds_incomplete_target_row_but_archives(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    helper.upsert_into_bigquery = lambda *_args, **_kwargs: calls.append("upsert")
    helper.move_csv_file_gcp = lambda *args: calls.append(("archive", *args))
    helper.move_csv_file = lambda *_args: None
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    evidence = loader._archive_after_optional_load(
        {}, SimpleNamespace(name="shares-incomplete.csv"),
        pd.DataFrame([_row(original_source_date="")]), "shares",
    )

    assert evidence["loadable"] == 0
    assert evidence["missing_contract_evidence"] == 1
    assert calls == [("archive", "data-123", "archive-123", "shares-incomplete.csv")]


def test_write_boundary_deduplicates_concurrent_retries_and_keeps_revision(
    tmp_path,
) -> None:
    original, _ = loader.prepare_normalized_rows(pd.DataFrame([_row()]))
    changed, _ = loader.prepare_normalized_rows(
        pd.DataFrame([_row(close="1 060,00", observation_id="observation-2")])
    )
    database = tmp_path / "share-revisions.db"

    def connect(path):
        return sqlite3.connect(path, timeout=10)

    loader._insert_revisions_into_duckdb(
        original, str(database), loader.REVISION_TABLE, connect=connect
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                loader._insert_revisions_into_duckdb,
                changed,
                str(database),
                loader.REVISION_TABLE,
                connect=connect,
            )
            for _ in range(2)
        ]
        for future in futures:
            future.result()

    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            f"SELECT revision_id, close FROM {loader.REVISION_TABLE} ORDER BY close"
        ).fetchall()

    assert len(stored) == 2
    assert len({revision_id for revision_id, _ in stored}) == 2
    assert {str(close) for _, close in stored} == {"1050.75", "1060"}


def test_write_boundary_preserves_first_commit_timestamp_on_identical_retry(tmp_path) -> None:
    first, _ = loader.prepare_normalized_rows(
        pd.DataFrame(
            [
                _row(
                    observation_id="observation-first",
                    collected_at="2026-09-22T08:00:00Z",
                    known_at="2026-09-22T08:01:00Z",
                )
            ]
        )
    )
    retry, _ = loader.prepare_normalized_rows(
        pd.DataFrame(
            [
                _row(
                    observation_id="observation-retry",
                    collected_at="2026-09-23T08:00:00Z",
                    known_at="2026-09-23T08:01:00Z",
                )
            ]
        )
    )
    database = tmp_path / "share-revisions.db"

    loader._insert_revisions_into_duckdb(
        first,
        str(database),
        loader.REVISION_TABLE,
        connect=sqlite3.connect,
        commit_clock=lambda: datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
    )
    loader._insert_revisions_into_duckdb(
        retry,
        str(database),
        loader.REVISION_TABLE,
        connect=sqlite3.connect,
        commit_clock=lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    )

    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            f"SELECT revision_id, validated_available_at FROM {loader.REVISION_TABLE}"
        ).fetchall()

    assert stored == [(first.loc[0, "revision_id"], "2026-09-24 12:00:00")]


def test_retry_after_commit_and_archive_failure_does_not_append_again(monkeypatch) -> None:
    committed = set()
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "unused"
    helper.upsert_into_bigquery = lambda *_args: None

    def insert(frame, _database, _asset):
        committed.update(frame["revision_id"])

    def archive(*_args):
        nonlocal archive_attempts
        archive_attempts += 1
        if archive_attempts == 1:
            raise OSError("archive move failed after data commit")

    helper.move_csv_file = archive
    helper.move_csv_file_gcp = lambda *_args: None
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setattr(loader, "_insert_revisions_into_duckdb", insert)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)
    config = {"duckdb": {"database": "unused"}, "csv_directory": "data", "archive": "archive"}

    with pytest.raises(OSError, match="archive move failed"):
        loader._archive_after_optional_load(config, "retry.csv", pd.DataFrame([_row()]), "shares")
    retry = loader._archive_after_optional_load(config, "retry.csv", pd.DataFrame([_row()]), "shares")

    assert retry["loadable"] == 1
    assert retry["duplicate_or_revision_unknown"] == 0
    assert len(committed) == 1
    assert archive_attempts == 2


def test_load_requires_explicit_session_and_source_columns() -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([{"symbol": "ABC"}]))

    assert normalized.empty
    assert evidence["missing_session_evidence"] == 1
