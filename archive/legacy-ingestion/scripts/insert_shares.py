from __future__ import annotations

import io
import os
from collections.abc import Iterable

import pandas as pd
from scrape_shares import parse_localized_decimal


NORMALIZED_COLUMNS = ("symbol", "name", "open", "high", "low", "volume", "close", "date")


def prepare_normalized_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Select only dated, verified, unambiguous traded observations for analysis."""
    import pandas as pd

    required = {"symbol", "name", "open", "high", "low", "volume", "close", "session_date"}
    missing = required - set(frame.columns)
    if missing:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS), {
            "missing_session_evidence": len(frame),
            "unknown_trade_status": 0,
            "duplicate_or_revision_unknown": 0,
            "invalid_numeric_observation": 0,
            "loadable": 0,
        }

    rows = frame.copy()
    verified = rows.get("session_date_status", pd.Series("unknown", index=rows.index)).eq("verified")
    dates = pd.to_datetime(rows["session_date"], errors="coerce", format="%Y-%m-%d")
    has_date = rows["session_date"].notna() & rows["session_date"].astype(str).str.strip().ne("") & dates.notna()
    status = rows.get("trade_status", pd.Series("unknown", index=rows.index))
    volume = rows["volume"].map(lambda value: parse_localized_decimal(str(value)))
    traded = status.eq("traded") & volume.gt(0) & volume.mod(1).eq(0)

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

    duplicate_mask = candidates.duplicated(["symbol", "_session_date"], keep=False)
    duplicate_count = int(duplicate_mask.sum())
    candidates = candidates.loc[~duplicate_mask]
    candidates["date"] = candidates.pop("_session_date")
    for column in ("open", "high", "low", "close"):
        candidates[column] = parsed_values[column].loc[candidates.index]
    candidates["volume"] = candidates["volume"].map(
        lambda value: int(parse_localized_decimal(str(value)))
    )

    normalized = candidates.loc[:, list(NORMALIZED_COLUMNS)].reset_index(drop=True)
    return normalized, {
        "missing_session_evidence": missing_date_count,
        "unknown_trade_status": unknown_trade_count,
        "duplicate_or_revision_unknown": duplicate_count,
        "invalid_numeric_observation": invalid_numeric_count,
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
        insert_into_bigquery,
        insert_into_duckdb,
        move_csv_file,
        move_csv_file_gcp,
    )

    normalized, evidence = prepare_normalized_rows(raw_frame)
    if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
        from google.auth import default

        credentials, project_id = default()
        if not normalized.empty:
            insert_into_bigquery(normalized, project_id, "stocks", asset)
        project_number = get_project_number(project_id)
        move_csv_file_gcp(f"data-{project_number}", f"archive-{project_number}", file.name)
    else:
        if not normalized.empty:
            insert_into_duckdb(normalized, config["duckdb"]["database"], asset)
        move_csv_file(config["csv_directory"], config["archive"], file)
    return evidence


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
