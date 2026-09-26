from __future__ import annotations

import hashlib
import io
import json
import os
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
from scrape_shares import parse_localized_decimal


NORMALIZED_COLUMNS = (
    "symbol",
    "session_date",
    "revision_id",
    "source_id",
    "source_observation_id",
    "source_revision_id",
    "session_date_status",
    "trade_status",
    "close",
    "high",
    "low",
    "volume",
    "basis",
    "original_source_date",
    "price_basis_ref",
    "validated_available_at",
    "actual_xof_turnover",
    "liquidity_basis",
    "suspension_status",
    "reason_codes",
    "source_published_at",
    "collected_at",
    "known_at",
    "snapshot_uri",
    "snapshot_sha256",
    "parser_version",
)
REVISION_TABLE = "share_price_revisions_v1"
REVISION_KEYS = ("symbol", "session_date", "revision_id")


def prepare_normalized_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Map evidenced observations to the immutable share-revision contract."""
    import pandas as pd

    required = {"symbol", "open", "high", "low", "volume", "close", "session_date"}
    missing = required - set(frame.columns)
    if missing:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS), {
            "missing_session_evidence": len(frame),
            "unknown_trade_status": 0,
            "duplicate_or_revision_unknown": 0,
            "exact_retry_duplicates": 0,
            "invalid_numeric_observation": 0,
            "missing_contract_evidence": 0,
            "loadable": 0,
        }

    rows = frame.copy()
    verified = rows.get("session_date_status", pd.Series("unknown", index=rows.index)).isin(
        ["verified", "trading"]
    )
    dates = pd.to_datetime(rows["session_date"], errors="coerce", format="%Y-%m-%d")
    has_date = rows["session_date"].notna() & rows["session_date"].astype(str).str.strip().ne("") & dates.notna()
    status = rows.get("trade_status", pd.Series("unknown", index=rows.index))
    volume = rows["volume"].map(_parse_optional_decimal)
    reported_traded = status.eq("traded")
    valid_traded_volume = volume.notna() & volume.gt(0) & volume.mod(1).eq(0)

    numeric_valid = rows.get(
        "numeric_parse_status", pd.Series("valid", index=rows.index)
    ).ne("invalid")
    numeric_valid &= ~reported_traded | valid_traded_volume
    parsed_values = {}
    for column in ("open", "high", "low", "close"):
        parsed_values[column] = rows[column].map(_parse_optional_decimal)
        malformed = rows[column].notna() & rows[column].astype(str).str.strip().ne("") & parsed_values[column].isna()
        numeric_valid &= ~malformed
    numeric_valid &= parsed_values["close"].notna()
    for column in ("open", "high", "low", "close"):
        supplied = rows[column].notna() & rows[column].astype(str).str.strip().ne("")
        positive = pd.Series(
            [value is None or value > 0 for value in parsed_values[column]], index=rows.index
        )
        numeric_valid &= ~supplied | positive

    candle_valid = pd.Series(
        [
            (high is None) == (low is None)
            and (high is None or (close is not None and low <= close <= high))
            and (opening is None or (high is not None and low <= opening <= high))
            for opening, high, low, close in zip(
                parsed_values["open"],
                parsed_values["high"],
                parsed_values["low"],
                parsed_values["close"],
            )
        ],
        index=rows.index,
    )
    numeric_valid &= candle_valid
    eligible = verified & has_date & reported_traded & numeric_valid
    missing_date_count = int((~verified | ~has_date).sum())
    unknown_trade_count = int((verified & has_date & ~reported_traded).sum())
    invalid_numeric_count = int(
        (verified & has_date & reported_traded & ~numeric_valid).sum()
    )
    candidates = rows.loc[eligible].copy()
    candidates["session_date"] = dates.loc[candidates.index].dt.date
    for column in ("open", "high", "low", "close"):
        candidates[column] = parsed_values[column].loc[candidates.index]
    candidates["volume"] = volume.loc[candidates.index].map(int)

    source_id = candidates.get("source_id", pd.Series("", index=candidates.index)).map(
        _clean_evidence_text
    )
    source_observation = candidates.get(
        "source_observation_id",
        candidates.get("observation_id", pd.Series("", index=candidates.index)),
    ).map(_clean_evidence_text)
    source_revision = candidates.get(
        "source_revision_id", pd.Series("", index=candidates.index)
    ).map(_clean_evidence_text)
    collected_at = candidates.get(
        "collected_at", pd.Series("", index=candidates.index)
    ).map(_normalize_collected_at)
    known_at = candidates.get(
        "known_at", pd.Series("", index=candidates.index)
    ).map(_normalize_collected_at)
    parser_version = candidates.get(
        "parser_version", pd.Series("", index=candidates.index)
    ).map(_clean_evidence_text)
    basis = candidates.get("basis", pd.Series("", index=candidates.index)).map(
        _clean_evidence_text
    )
    price_basis_ref = candidates.get(
        "price_basis_ref", pd.Series("", index=candidates.index)
    ).map(_clean_evidence_text)
    original_source_date = candidates.get(
        "original_source_date", pd.Series("", index=candidates.index)
    )
    original_dates = pd.to_datetime(
        original_source_date, errors="coerce", format="%Y-%m-%d"
    )
    original_date_text = original_source_date.fillna("").astype(str).str.strip()
    original_date_valid = original_date_text.ne("") & original_dates.notna()
    traceable = (
        source_id.ne("")
        & source_observation.ne("")
        & source_revision.ne("")
        & collected_at.ne("")
        & known_at.ne("")
        & parser_version.ne("")
        & basis.ne("")
        & price_basis_ref.ne("")
        & original_date_valid
    )
    untraceable_count = int((~traceable).sum())
    candidates = candidates.loc[traceable].copy()
    candidates["source_id"] = source_id.loc[candidates.index]
    candidates["source_observation_id"] = source_observation.loc[candidates.index]
    candidates["source_revision_id"] = source_revision.loc[candidates.index]
    candidates["collected_at"] = collected_at.loc[candidates.index]
    candidates["known_at"] = known_at.loc[candidates.index]
    candidates["parser_version"] = parser_version.loc[candidates.index]
    candidates["basis"] = basis.loc[candidates.index]
    candidates["original_source_date"] = original_dates.loc[candidates.index].dt.date
    candidates["price_basis_ref"] = price_basis_ref.loc[candidates.index]
    candidates["session_date_status"] = "trading"
    candidates["trade_status"] = "traded"
    candidates["validated_available_at"] = candidates["known_at"]
    candidates["actual_xof_turnover"] = candidates.get(
        "actual_xof_turnover", pd.Series(None, index=candidates.index)
    ).map(_parse_optional_decimal)
    candidates["liquidity_basis"] = candidates.get(
        "liquidity_basis", pd.Series(None, index=candidates.index)
    )
    candidates["suspension_status"] = candidates.get(
        "suspension_status", pd.Series("unknown", index=candidates.index)
    ).fillna("unknown").astype(str)
    candidates["reason_codes"] = candidates["suspension_status"].map(
        lambda status: ("suspension_status_unknown",) if status == "unknown" else ()
    )
    candidates["source_published_at"] = candidates.get(
        "source_published_at", pd.Series(None, index=candidates.index)
    ).map(_normalize_collected_at).replace("", None)
    for column in ("snapshot_uri", "snapshot_sha256"):
        if column not in candidates:
            candidates[column] = None
    candidates["revision_id"] = candidates.apply(_revision_id, axis=1)

    exact_retry_mask = candidates.duplicated(list(REVISION_KEYS), keep="first")
    exact_retry_count = int(exact_retry_mask.sum())
    candidates = candidates.loc[~exact_retry_mask]

    normalized = candidates.loc[:, list(NORMALIZED_COLUMNS)].reset_index(drop=True)
    return normalized, {
        "missing_session_evidence": missing_date_count,
        "unknown_trade_status": unknown_trade_count,
        "duplicate_or_revision_unknown": untraceable_count,
        "exact_retry_duplicates": exact_retry_count,
        "invalid_numeric_observation": invalid_numeric_count,
        "missing_contract_evidence": untraceable_count,
        "loadable": len(normalized),
    }


def _parse_optional_decimal(value: object):
    if pd.isna(value) or not str(value).strip():
        return None
    try:
        parsed = parse_localized_decimal(str(value))
    except ValueError:
        return None
    if parsed is None:
        return None
    micros = parsed * 1_000_000
    if micros != micros.to_integral_value() or micros > 2**63 - 1:
        return None
    return parsed


def _clean_evidence_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_collected_at(value: object) -> str:
    text = _clean_evidence_text(value)
    if not text:
        return ""
    try:
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if instant.tzinfo is None or instant.utcoffset() is None:
        return ""
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _revision_id(row: pd.Series) -> str:
    """Bind a revision to every persisted value so matched writes are immutable."""
    payload = {
        column: _revision_value(row[column])
        for column in NORMALIZED_COLUMNS
        if column != "revision_id"
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _revision_value(value: object) -> object:
    if isinstance(value, tuple):
        return list(value)
    if pd.isna(value):
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _archive_after_optional_load(config, file, raw_frame: pd.DataFrame, asset: str) -> dict[str, int]:
    from helper import (
        get_project_number,
        move_csv_file,
        move_csv_file_gcp,
        upsert_into_bigquery,
    )

    normalized, evidence = prepare_normalized_rows(raw_frame)

    if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
        from google.auth import default

        _, project_id = default()
        if not normalized.empty:
            upsert_into_bigquery(
                normalized,
                project_id,
                "stocks",
                REVISION_TABLE,
                list(REVISION_KEYS),
                update_matched=False,
            )
        project_number = get_project_number(project_id)
        move_csv_file_gcp(f"data-{project_number}", f"archive-{project_number}", file.name)
    else:
        if not normalized.empty:
            _insert_revisions_into_duckdb(
                normalized, config["duckdb"]["database"], REVISION_TABLE
            )
        move_csv_file(config["csv_directory"], config["archive"], file)
    return evidence


def _insert_revisions_into_duckdb(
    frame: pd.DataFrame, db_path: str, table: str, *, connect=None
) -> None:
    """Insert revision rows behind a storage-enforced uniqueness boundary."""
    if connect is None:
        import duckdb

        connect = duckdb.connect

    quoted_table = _quoted_identifier(table)
    database_path = os.path.join(os.path.dirname(__file__), "..", db_path)
    column_definitions = {
        "symbol": "VARCHAR NOT NULL",
        "close": "DECIMAL(38, 6) NOT NULL",
        "high": "DECIMAL(38, 6)",
        "low": "DECIMAL(38, 6)",
        "volume": "BIGINT",
        "session_date": "DATE NOT NULL",
        "revision_id": "VARCHAR NOT NULL",
        "source_id": "VARCHAR NOT NULL",
        "source_observation_id": "VARCHAR NOT NULL",
        "source_revision_id": "VARCHAR NOT NULL",
        "source_published_at": "TIMESTAMP",
        "collected_at": "TIMESTAMP NOT NULL",
        "known_at": "TIMESTAMP NOT NULL",
        "snapshot_uri": "VARCHAR",
        "snapshot_sha256": "VARCHAR",
        "parser_version": "VARCHAR NOT NULL",
        "session_date_status": "VARCHAR NOT NULL",
        "trade_status": "VARCHAR NOT NULL",
        "basis": "VARCHAR NOT NULL",
        "original_source_date": "DATE NOT NULL",
        "price_basis_ref": "VARCHAR NOT NULL",
        "validated_available_at": "TIMESTAMP",
        "actual_xof_turnover": "DECIMAL(38, 6)",
        "liquidity_basis": "VARCHAR",
        "suspension_status": "VARCHAR NOT NULL",
        "reason_codes": "VARCHAR NOT NULL",
    }
    definitions = ", ".join(
        f"{_quoted_identifier(column)} {column_definitions[column]}"
        for column in NORMALIZED_COLUMNS
    )
    unique_columns = ", ".join(_quoted_identifier(column) for column in REVISION_KEYS)
    unique_index = _quoted_identifier(f"{table}_symbol_session_revision_uidx")
    columns = ", ".join(_quoted_identifier(column) for column in NORMALIZED_COLUMNS)
    placeholders = ", ".join("?" for _ in NORMALIZED_COLUMNS)
    records = [
        tuple(_database_value(row[column]) for column in NORMALIZED_COLUMNS)
        for _, row in frame.iterrows()
    ]

    with connect(database_path) as connection:
        try:
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {quoted_table} "
                f"({definitions}, UNIQUE ({unique_columns}))"
            )
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {unique_index} "
                f"ON {quoted_table} ({unique_columns})"
            )
            connection.executemany(
                f"INSERT OR IGNORE INTO {quoted_table} ({columns}) VALUES ({placeholders})",
                records,
            )
        except Exception as error:
            raise RuntimeError(
                f"{table} must expose the normalized share revision schema"
            ) from error


def _quoted_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"invalid table or column identifier: {value!r}")
    return f'"{value}"'


def _database_value(value: object) -> object:
    if isinstance(value, tuple):
        return json.dumps(value)
    if pd.isna(value):
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def process_share_files(config, files: Iterable[object]) -> list[dict[str, int]]:
    """Archive each complete raw file, loading only verified observations."""
    import pandas as pd

    evidence = []
    for file in files:
        if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
            raw_frame = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
        else:
            raw_frame = pd.read_csv(file, sep="|")
        evidence.append(_archive_after_optional_load(config, file, raw_frame, "shares"))
    return evidence


def entry_point(request=None):
    import yaml
    from helper import load_files

    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)
    process_share_files(config, load_files(config, "shares"))
    return "Share observations archived; only verified rows were loaded.\n"


if not (os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET")):
    if __name__ == "__main__":
        print(entry_point())
