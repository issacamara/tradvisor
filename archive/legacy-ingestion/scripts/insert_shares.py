from __future__ import annotations

import io
import os
import re
import threading
from collections.abc import Iterable

import pandas as pd
from scrape_shares import build_source_revision_id, parse_localized_decimal


NORMALIZED_COLUMNS = (
    "symbol",
    "name",
    "open",
    "high",
    "low",
    "volume",
    "close",
    "date",
    "source_revision_id",
)
REVISION_KEY = ("symbol", "date", "source_revision_id")
_DUCKDB_WRITE_LOCK = threading.Lock()


def _empty_evidence(row_count: int) -> dict[str, int]:
    return {
        "missing_session_evidence": row_count,
        "unknown_trade_status": 0,
        "duplicate_or_revision_unknown": 0,
        "invalid_numeric_observation": 0,
        "revision_identity_conflict": 0,
        "exact_retries": 0,
        "loadable": 0,
    }


def prepare_normalized_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Select only dated, verified, unambiguous traded observations for analysis."""
    import pandas as pd

    required = {"symbol", "name", "open", "high", "low", "volume", "close", "session_date"}
    missing = required - set(frame.columns)
    if missing:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS), _empty_evidence(len(frame))

    rows = frame.copy()
    verified = rows.get("session_date_status", pd.Series("unknown", index=rows.index)).eq("verified")
    dates = pd.to_datetime(rows["session_date"], errors="coerce", format="%Y-%m-%d")
    has_date = rows["session_date"].notna() & rows["session_date"].astype(str).str.strip().ne("") & dates.notna()
    status = rows.get("trade_status", pd.Series("unknown", index=rows.index))
    volume = rows["volume"].map(_parse_optional_decimal)
    traded = status.eq("traded") & volume.map(
        lambda value: value is not None and value > 0 and value == value.to_integral_value()
    )

    numeric_valid = rows.get(
        "numeric_parse_status", pd.Series("valid", index=rows.index)
    ).ne("invalid")
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
    eligible = verified & has_date & traded & numeric_valid
    missing_date_count = int((~verified | ~has_date).sum())
    unknown_trade_count = int((verified & has_date & ~traded).sum())
    invalid_numeric_count = int((verified & has_date & traded & ~numeric_valid).sum())
    candidates = rows.loc[eligible].copy()
    candidates["_session_date"] = dates.loc[candidates.index].dt.date
    supplied_revision = candidates.get(
        "source_revision_id", pd.Series("", index=candidates.index)
    ).fillna("").astype(str).str.strip()
    revision_ids = [
        revision if revision else build_source_revision_id(row.to_dict())
        for revision, (_, row) in zip(supplied_revision, candidates.iterrows())
    ]
    candidates["date"] = candidates.pop("_session_date")
    for column in ("open", "high", "low", "close"):
        candidates[column] = parsed_values[column].loc[candidates.index]
    candidates["volume"] = volume.loc[candidates.index].map(int)
    candidates["source_revision_id"] = revision_ids

    key_columns = ["symbol", "date", "source_revision_id"]
    value_columns = list(NORMALIZED_COLUMNS)
    conflict_indexes: set[object] = set()
    for _, group in candidates.groupby(key_columns, sort=False, dropna=False):
        if len(group[value_columns].drop_duplicates()) > 1:
            conflict_indexes.update(group.index)
    conflict_mask = candidates.index.to_series().isin(conflict_indexes)
    conflict_count = int(conflict_mask.sum())
    candidates = candidates.loc[~conflict_mask]

    exact_retry_mask = candidates.duplicated(key_columns, keep="first")
    exact_retry_count = int(exact_retry_mask.sum())
    candidates = candidates.loc[~exact_retry_mask]

    normalized = candidates.loc[:, list(NORMALIZED_COLUMNS)].reset_index(drop=True)
    return normalized, {
        "missing_session_evidence": missing_date_count,
        "unknown_trade_status": unknown_trade_count,
        "duplicate_or_revision_unknown": conflict_count,
        "invalid_numeric_observation": invalid_numeric_count,
        "revision_identity_conflict": conflict_count,
        "exact_retries": exact_retry_count,
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

        credentials, project_id = default()
        if not normalized.empty:
            upsert_into_bigquery(
                normalized,
                project_id,
                "stocks",
                asset,
                list(REVISION_KEY),
                update_matched=False,
            )
        project_number = get_project_number(project_id)
        move_csv_file_gcp(f"data-{project_number}", f"archive-{project_number}", file.name)
    else:
        if not normalized.empty:
            _upsert_into_duckdb(normalized, config["duckdb"]["database"], asset)
        move_csv_file(config["csv_directory"], config["archive"], file)
    return evidence


def _upsert_into_duckdb(frame: pd.DataFrame, database: str, table: str) -> None:
    """Insert immutable revisions behind a database-enforced unique key."""
    import duckdb

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) is None:
        raise ValueError(f"invalid DuckDB table name: {table!r}")
    database_path = os.path.join(os.path.dirname(__file__), "..", database)
    quoted_table = f'"{table}"'
    index_name = f'"{table}_symbol_session_revision"'
    incoming = frame.loc[:, list(NORMALIZED_COLUMNS)].copy()

    with _DUCKDB_WRITE_LOCK, duckdb.connect(database_path) as connection:
        connection.register("incoming_share_revisions", incoming)
        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {quoted_table} AS "
                "SELECT * FROM incoming_share_revisions WHERE FALSE"
            )
            columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()
            }
            missing = set(NORMALIZED_COLUMNS) - columns
            if missing:
                raise ValueError(
                    f"{table} table is missing normalized revision columns: {sorted(missing)}"
                )
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {quoted_table} "
                '("symbol", "date", "source_revision_id")'
            )
            connection.execute(
                f"INSERT OR IGNORE INTO {quoted_table} BY NAME "
                "SELECT * FROM incoming_share_revisions"
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise


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
