from __future__ import annotations

import inspect
import importlib.util
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "functions" / "shares"
LEGACY_SCRIPTS = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(LEGACY_SCRIPTS))


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scraper = _load_script("share_scraper_for_tests", "scrape_shares.py")
loader = _load_script("share_loader_for_tests", "insert_shares.py")
actual_helper = importlib.util.spec_from_file_location(
    "share_helper_for_signature_tests", LEGACY_SCRIPTS / "helper.py"
)
assert actual_helper is not None and actual_helper.loader is not None
helper_module = importlib.util.module_from_spec(actual_helper)
sys.modules[actual_helper.name] = helper_module
actual_helper.loader.exec_module(helper_module)
actual_helper = helper_module


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
    monkeypatch.setattr(scraper, "scrape_brvm_session", lambda _url: (None, "unknown"))
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
    assert observation["source_id"] == "sikafinance-shares"
    assert observation["parser_version"] == "shares-parser-v2"
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
    monkeypatch.setattr(scraper, "scrape_brvm_session", lambda _url: (None, "unknown"))
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
    monkeypatch.setattr(scraper, "scrape_brvm_session", lambda _url: (None, "unknown"))
    row = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc)
    ).iloc[0]

    assert row["open"] == "1.23,45"
    assert row["parsed_open"] == ""
    assert row["numeric_parse_status"] == "invalid"
    assert row["numeric_parse_errors"] == "open"


def test_official_closed_weekday_session_is_attached_to_sika_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "scrape",
        lambda _url: [
            {
                "symbol": "ABC",
                "name": "Example",
                "open": "1 000",
                "high": "1 100",
                "low": "900",
                "volume": "12",
                "close": "1 050",
            }
        ],
    )
    monkeypatch.setattr(
        scraper,
        "scrape_brvm_session",
        lambda _url: (datetime(2026, 10, 2, tzinfo=timezone.utc).date(), "verified"),
    )

    row = scraper.scrape_brvm_shares(
        "fixture://shares", collected_at=datetime(2026, 10, 2, 20, tzinfo=timezone.utc)
    ).iloc[0]

    assert row["session_date"] == "2026-10-02"
    assert row["original_source_date"] == "2026-10-02"
    assert row["session_date_status"] == "verified"


def test_brvm_session_resolver_requires_closed_non_holiday_weekday() -> None:
    closed_weekday = "Vendredi, 2 octobre, 2026 - 15:17\nSeance fermee\n01/01/2026"
    assert scraper.resolve_brvm_session(closed_weekday) == (
        datetime(2026, 10, 2, tzinfo=timezone.utc).date(),
        "verified",
    )

    holiday = "Vendredi, 25 decembre, 2026 - 15:17\nSeance fermee\n25/12/2026"
    assert scraper.resolve_brvm_session(holiday) == (None, "unknown")

    open_weekday = "Vendredi, 2 octobre, 2026 - 10:17\nSeance ouverte\n01/01/2026"
    assert scraper.resolve_brvm_session(open_weekday) == (None, "unknown")


def test_same_day_scrapes_preserve_each_raw_gcs_evidence_object(monkeypatch) -> None:
    stored = {}

    class PreconditionFailed(Exception):
        pass

    class Blob:
        def __init__(self, name):
            self.name = name

        def upload_from_string(self, payload, **kwargs):
            assert kwargs == {"content_type": "text/csv", "if_generation_match": 0}
            if self.name in stored:
                raise PreconditionFailed()
            stored[self.name] = payload

    class Bucket:
        name = "data-123"

        def blob(self, name):
            return Blob(name)

    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google_cloud = ModuleType("google.cloud")
    google_storage = ModuleType("google.cloud.storage")
    google_storage.Client = lambda: SimpleNamespace(bucket=lambda _name: Bucket())
    google_api_core = ModuleType("google.api_core")
    google_exceptions = ModuleType("google.api_core.exceptions")
    google_exceptions.PreconditionFailed = PreconditionFailed
    google.auth = google_auth
    google.cloud = google_cloud
    google_cloud.storage = google_storage
    google.api_core = google_api_core
    google_api_core.exceptions = google_exceptions
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", google_storage)
    monkeypatch.setitem(sys.modules, "google.api_core", google_api_core)
    monkeypatch.setitem(sys.modules, "google.api_core.exceptions", google_exceptions)
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setenv("K_SERVICE", "share-scraper")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")
    collected_at = datetime(2026, 9, 22, 8, tzinfo=timezone.utc)

    first_result = scraper._save_raw_observations(
        pd.DataFrame([{"symbol": "ABC", "close": "1 050,75"}]), collected_at
    )
    second_result = scraper._save_raw_observations(
        pd.DataFrame([{"symbol": "ABC", "close": "1 051,00"}]), collected_at
    )
    assert first_result != second_result
    assert sorted(stored) == [
        "shares-2026-09-22T080000000000Z-1.csv",
        "shares-2026-09-22T080000000000Z.csv",
    ]
    assert any("1 050,75" in content for content in stored.values())
    assert any("1 051,00" in content for content in stored.values())


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
    assert tuple(normalized.columns) == loader.NORMALIZED_COLUMNS


def test_verified_rows_project_to_the_canonical_lowercase_market_schema() -> None:
    raw = pd.DataFrame([_row(name="Example issuer")])
    normalized, _ = loader.prepare_normalized_rows(raw)

    market_rows = loader.project_market_rows(raw, normalized)

    assert loader.MARKET_TABLE == "shares"
    assert loader.MARKET_KEYS == ("symbol", "date")
    assert tuple(market_rows.columns) == loader.MARKET_COLUMNS
    assert market_rows.to_dict("records") == [
        {
            "symbol": "ABC",
            "name": "Example issuer",
            "open": 1000.25,
            "high": 1100.5,
            "low": 900.0,
            "close": 1050.75,
            "volume": 12.0,
            "date": datetime(2026, 9, 21).date(),
        }
    ]


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


def test_exact_retry_is_collapsed_and_changed_correction_projects_one_canonical_row() -> None:
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
    assert set(normalized["source_revision_id"]) == {"source-a", "source-b"}
    assert {str(value) for value in normalized["close"]} == {"1050.75", "1051.00"}
    canonical = loader.project_market_rows(rows, normalized)
    assert canonical.to_dict("records") == [
        {
            "symbol": "ABC",
            "name": "",
            "open": 1000.25,
            "high": 1100.5,
            "low": 900.0,
            "close": 1051.0,
            "volume": 12.0,
            "date": datetime(2026, 9, 21).date(),
        }
    ]


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


def test_cloud_load_uses_actual_helper_signature_and_canonical_market_keys(monkeypatch) -> None:
    signature = inspect.signature(actual_helper.upsert_shares_and_archive)
    signature.bind(
        pd.DataFrame(),
        "project",
        "stocks",
        lambda: None,
        run_id="shares-run",
    )

    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    helper.move_csv_file_gcp = lambda *args: calls.append(("gcs-archive", *args))

    def upsert(
        frame,
        project_id,
        dataset,
        archive,
        *,
        run_id,
    ):
        calls.append(
            (
                "upsert",
                len(frame),
                project_id,
                dataset,
                run_id,
                frame.to_dict("records"),
            )
        )
        archive()

    helper.upsert_shares_and_archive = upsert
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    evidence = loader._load_then_archive(
        SimpleNamespace(name="shares.csv"),
        pd.DataFrame([_row()]),
    )

    assert evidence["loadable"] == 1
    assert calls == [
        (
            "upsert",
            1,
            "project",
            "stocks",
            "shares-" + hashlib.sha256(b"shares.csv").hexdigest(),
            [
                {
                    "symbol": "ABC",
                    "name": "",
                    "open": 1000.25,
                    "high": 1100.5,
                    "low": 900.0,
                    "close": 1050.75,
                    "volume": 12.0,
                    "date": datetime(2026, 9, 21).date(),
                }
            ],
        ),
        ("gcs-archive", "data-123", "archive-123", "shares.csv"),
    ]


def test_share_completion_follows_the_managed_write_and_is_sanitized(monkeypatch) -> None:
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    helper.move_csv_file_gcp = lambda *_args: None
    helper.upsert_shares_and_archive = lambda *_args, **_kwargs: "a" * 64
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)

    revisions: list[str] = []
    loader._load_then_archive(
        SimpleNamespace(name="shares.csv"), pd.DataFrame([_row()]), completion_revisions=revisions
    )
    completion = loader.managed_import_completion(
        "shares", revisions, completed_at=datetime(2026, 10, 18, tzinfo=timezone.utc)
    )

    assert completion == {
        "source": "shares",
        "status": "succeeded",
        "managed_write": {
            "revision_fingerprint": hashlib.sha256(b'["' + b"a" * 64 + b'"]').hexdigest(),
            "completed_at": "2026-10-18T00:00:00Z",
        },
    }
    replay = loader.managed_import_completion(
        "shares", list(reversed(revisions)), completed_at=datetime(2026, 10, 18, tzinfo=timezone.utc)
    )
    assert replay["managed_write"]["revision_fingerprint"] == completion["managed_write"]["revision_fingerprint"]


def test_share_archive_failure_never_records_a_completion_revision(monkeypatch) -> None:
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"

    def upsert(_frame, _project, _dataset, archive, *, run_id):
        archive()
        return "a" * 64

    helper.upsert_shares_and_archive = upsert
    helper.move_csv_file_gcp = lambda *_args: (_ for _ in ()).throw(OSError("archive failed"))
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)

    revisions: list[str] = []
    with pytest.raises(OSError, match="archive failed"):
        loader._load_then_archive(
            SimpleNamespace(name="shares.csv"), pd.DataFrame([_row()]), completion_revisions=revisions
        )

    assert revisions == []


def test_cloud_load_withholds_incomplete_target_row_but_archives(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"
    helper.upsert_shares_and_archive = lambda *_args, **_kwargs: calls.append("upsert")
    helper.move_csv_file_gcp = lambda *args: calls.append(("archive", *args))
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    evidence = loader._load_then_archive(
        SimpleNamespace(name="shares-incomplete.csv"), pd.DataFrame([_row(original_source_date="")])
    )

    assert evidence["loadable"] == 0
    assert evidence["missing_contract_evidence"] == 1
    assert calls == [("archive", "data-123", "archive-123", "shares-incomplete.csv")]


def test_retry_after_archive_failure_does_not_duplicate_canonical_observations(monkeypatch) -> None:
    canonical = {}
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"

    def upsert(frame, *_args):
        for row in frame.to_dict("records"):
            canonical[(row["symbol"], row["date"])] = row

    def archive(*_args):
        nonlocal archive_attempts
        archive_attempts += 1
        if archive_attempts == 1:
            raise OSError("archive move failed after data commit")


    helper.move_csv_file_gcp = archive

    def staged_upsert(frame, _project, _dataset, archive_callback, *, run_id):
        upsert(frame)
        archive_callback()

    helper.upsert_shares_and_archive = staged_upsert
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    with pytest.raises(OSError, match="archive move failed"):
        loader._load_then_archive(SimpleNamespace(name="retry.csv"), pd.DataFrame([_row()]))
    retry = loader._load_then_archive(SimpleNamespace(name="retry.csv"), pd.DataFrame([_row()]))

    assert retry["loadable"] == 1
    assert retry["duplicate_or_revision_unknown"] == 0
    assert len(canonical) == 1
    assert archive_attempts == 2


def test_bigquery_failure_leaves_gcs_object_retryable(monkeypatch) -> None:
    calls = []
    helper = ModuleType("helper")
    helper.get_project_number = lambda _project: "123"

    def upsert(*_args):
        calls.append("upsert")
        if len(calls) == 1:
            raise RuntimeError("BigQuery unavailable")

    def staged_upsert(_frame, _project, _dataset, archive_callback, *, run_id):
        upsert()
        archive_callback()

    helper.upsert_shares_and_archive = staged_upsert
    helper.move_csv_file_gcp = lambda *_args: calls.append("archive")
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")
    google.auth = google_auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setenv("K_SERVICE", "share-loader")
    monkeypatch.setenv("FUNCTION_TARGET", "entry_point")

    with pytest.raises(RuntimeError, match="BigQuery unavailable"):
        loader._load_then_archive(SimpleNamespace(name="retry.csv"), pd.DataFrame([_row()]))
    loader._load_then_archive(SimpleNamespace(name="retry.csv"), pd.DataFrame([_row()]))

    assert calls == ["upsert", "upsert", "archive"]


def test_share_entrypoints_do_not_require_cloud_function_marker_variables() -> None:
    for module_path in (SCRIPTS / "scrape_shares.py", SCRIPTS / "insert_shares.py"):
        source = module_path.read_text()
        assert "K_SERVICE" not in source
        assert "FUNCTION_TARGET" not in source


def test_importing_share_modules_has_no_storage_side_effects(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)

    _load_script("side_effect_free_scraper", "scrape_shares.py")
    _load_script("side_effect_free_loader", "insert_shares.py")

    assert not list(tmp_path.iterdir())


def test_load_requires_explicit_session_and_source_columns() -> None:
    normalized, evidence = loader.prepare_normalized_rows(pd.DataFrame([{"symbol": "ABC"}]))

    assert normalized.empty
    assert evidence["missing_session_evidence"] == 1
