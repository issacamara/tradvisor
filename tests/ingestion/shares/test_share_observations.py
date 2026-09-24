from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


class _FakeDuckConnection:
    def __init__(self, state: dict, database: str) -> None:
        self.state = state
        self.database = database
        self.incoming = pd.DataFrame()
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def register(self, _name: str, frame: pd.DataFrame) -> None:
        self.incoming = frame.copy()

    def execute(self, sql: str):
        normalized = " ".join(sql.split()).upper()
        table = self.state.setdefault(self.database, {})
        if normalized.startswith("CREATE TABLE"):
            table.setdefault("columns", list(self.incoming.columns))
            table.setdefault("rows", {})
        elif normalized.startswith("PRAGMA TABLE_INFO"):
            self.result = [
                (index, column) for index, column in enumerate(table["columns"])
            ]
        elif normalized.startswith("INSERT OR IGNORE"):
            for row in self.incoming.to_dict("records"):
                key = (row["symbol"], str(row["date"]), row["source_revision_id"])
                table["rows"].setdefault(key, row)
        return self

    def fetchall(self):
        return self.result


def _install_fake_duckdb(monkeypatch) -> dict:
    state: dict = {}
    duckdb = ModuleType("duckdb")
    duckdb.connect = lambda database: _FakeDuckConnection(state, database)
    monkeypatch.setitem(sys.modules, "duckdb", duckdb)
    return state


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


def test_exact_retry_is_collapsed_while_distinct_revision_is_retained() -> None:
    rows = pd.DataFrame(
        [
            _row(observation_id="revision-a", source_revision_id="source-a"),
            _row(
                observation_id="retry-a",
                source_revision_id="source-a",
                collected_at="2026-09-22T08:01:00Z",
            ),
            _row(close="1 051,00", observation_id="revision-b", source_revision_id="source-b"),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert len(normalized) == 2
    assert set(normalized["source_revision_id"]) == {"source-a", "source-b"}
    assert evidence["exact_retries"] == 1
    assert evidence["duplicate_or_revision_unknown"] == 0


def test_conflicting_values_for_one_revision_identity_are_withheld() -> None:
    rows = pd.DataFrame(
        [
            _row(source_revision_id="source-a"),
            _row(close="1 051,00", source_revision_id="source-a"),
        ]
    )

    normalized, evidence = loader.prepare_normalized_rows(rows)

    assert normalized.empty
    assert evidence["revision_identity_conflict"] == 2
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
    helper.upsert_into_bigquery = lambda *_args, **_kwargs: calls.append("bigquery")
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


def test_existing_cloud_table_uses_shared_upsert_signature(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"

    def upsert(
        frame,
        project_id,
        dataset,
        table,
        primary_keys,
        *,
        run_id=None,
        snapshot_manifest=None,
        update_matched=True,
    ):
        calls.append(
            (frame.copy(), project_id, dataset, table, primary_keys, update_matched)
        )

    helper.upsert_into_bigquery = upsert
    helper.move_csv_file = lambda *_args: None
    helper.move_csv_file_gcp = lambda *args: calls.append(args)
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "insert-shares")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    evidence = loader._archive_after_optional_load(
        {}, SimpleNamespace(name="shares-existing.csv"), pd.DataFrame([_row()]), "shares"
    )

    assert evidence["loadable"] == 1
    upsert_call = calls[0]
    assert upsert_call[1:] == (
        "project",
        "stocks",
        "shares",
        ["symbol", "date", "source_revision_id"],
        False,
    )
    assert calls[1] == ("data-123", "archive-123", "shares-existing.csv")


def test_concurrent_exact_retries_are_idempotent_but_revisions_coexist(
    tmp_path, monkeypatch
) -> None:
    state = _install_fake_duckdb(monkeypatch)
    database = tmp_path / "shares.duckdb"
    exact, _ = loader.prepare_normalized_rows(pd.DataFrame([_row()]))
    revised, _ = loader.prepare_normalized_rows(
        pd.DataFrame([_row(close="1 060,00", observation_id="observation-2")])
    )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(loader._upsert_into_duckdb, exact, str(database), "shares")
            for _ in range(8)
        ]
        for future in futures:
            future.result()
    loader._upsert_into_duckdb(revised, str(database), "shares")

    stored = list(state[str(database)]["rows"].values())
    assert len(stored) == 2
    assert len({row["source_revision_id"] for row in stored}) == 2


def test_retry_after_commit_and_archive_failure_does_not_append_again(
    tmp_path, monkeypatch
) -> None:
    state = _install_fake_duckdb(monkeypatch)
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "unused"
    helper.upsert_into_bigquery = lambda *_args, **_kwargs: None

    def archive(*_args):
        nonlocal archive_attempts
        archive_attempts += 1
        if archive_attempts == 1:
            raise OSError("archive move failed after data commit")

    helper.move_csv_file = archive
    helper.move_csv_file_gcp = lambda *_args: None
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)
    database = tmp_path / "shares.duckdb"
    config = {
        "duckdb": {"database": str(database)},
        "csv_directory": "data",
        "archive": "archive",
    }

    with pytest.raises(OSError, match="archive move failed"):
        loader._archive_after_optional_load(config, "retry.csv", pd.DataFrame([_row()]), "shares")
    retry = loader._archive_after_optional_load(config, "retry.csv", pd.DataFrame([_row()]), "shares")

    assert retry["loadable"] == 1
    assert len(state[str(database)]["rows"]) == 1
    assert archive_attempts == 2


def test_load_requires_explicit_session_and_source_columns() -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([{"symbol": "ABC"}]))

    assert normalized.empty
    assert evidence["missing_session_evidence"] == 1
