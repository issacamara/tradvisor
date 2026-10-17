from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable
from datetime import datetime, timezone

import pandas as pd
from ingestion_observability import observed_entrypoint
from scrape_shares import parse_localized_decimal


NORMALIZED_COLUMNS = (
    "symbol",
    "session_date",
    "source_observation_id",
    "source_revision_id",
    "close",
    "high",
    "low",
    "volume",
)
MARKET_TABLE = "shares"
MARKET_KEYS = ("symbol", "date")
MARKET_COLUMNS = ("symbol", "name", "open", "high", "low", "close", "volume", "date")


def prepare_normalized_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep loadable canonical-share rows with their source provenance."""
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
    candidates["source_observation_id"] = source_observation.loc[candidates.index]
    candidates["source_revision_id"] = source_revision.loc[candidates.index]
    exact_retry_mask = candidates.duplicated(
        ["symbol", "session_date", "source_revision_id"], keep="first"
    )
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


def _load_then_archive(
    file,
    raw_frame: pd.DataFrame,
    configuration=None,
) -> dict[str, int]:
    from helper import (
        get_project_number,
        move_csv_file_gcp,
        upsert_shares_and_archive,
    )

    normalized, evidence = prepare_normalized_rows(raw_frame)
    market_rows = project_market_rows(raw_frame, normalized)
    from google.auth import default

    _, project_id = default()
    if configuration is not None:
        configuration.validate_application_default_project(project_id)
    dataset = configuration.dataset if configuration is not None else "stocks"
    if configuration is not None and configuration.table_for("shares") != (
        f"{project_id}.{dataset}.{MARKET_TABLE}"
    ):
        raise ValueError("share target does not match the managed staging contract")
    project_number = get_project_number(project_id) if configuration is None else None
    data_bucket = (
        configuration.data_bucket if configuration is not None else f"data-{project_number}"
    )
    archive_bucket = (
        configuration.archive_bucket
        if configuration is not None
        else f"archive-{project_number}"
    )

    def archive() -> None:
        move_csv_file_gcp(data_bucket, archive_bucket, file.name)

    if not market_rows.empty:
        run_id = "shares-" + hashlib.sha256(file.name.encode("utf-8")).hexdigest()
        upsert_shares_and_archive(
            market_rows,
            project_id,
            dataset,
            archive,
            run_id=run_id,
        )
    else:
        archive()
    return evidence


def project_market_rows(raw_frame: pd.DataFrame, normalized: pd.DataFrame) -> pd.DataFrame:
    """Project verified observations into the canonical lowercase market table."""
    if normalized.empty:
        return pd.DataFrame(columns=MARKET_COLUMNS)
    if "observation_id" not in raw_frame:
        raise ValueError("raw share observations must include observation_id")

    raw_by_observation = raw_frame.drop_duplicates("observation_id", keep="last").set_index(
        "observation_id"
    )
    source_rows = raw_by_observation.reindex(normalized["source_observation_id"].tolist())
    if source_rows["symbol"].isna().any():
        raise ValueError("normalized share observation is missing its raw source row")

    def as_float(value: object):
        if pd.isna(value):
            return None
        return float(value)

    market_rows = pd.DataFrame(
        {
            "symbol": normalized["symbol"].tolist(),
            "name": source_rows.get("name", pd.Series("", index=source_rows.index)).tolist(),
            "open": source_rows["open"].map(_parse_optional_decimal).map(as_float).tolist(),
            "high": normalized["high"].map(as_float).tolist(),
            "low": normalized["low"].map(as_float).tolist(),
            "close": normalized["close"].map(as_float).tolist(),
            "volume": normalized["volume"].map(as_float).tolist(),
            "date": normalized["session_date"].tolist(),
        }
    )
    return market_rows.drop_duplicates(list(MARKET_KEYS), keep="last").loc[:, MARKET_COLUMNS]


def process_share_files(
    files: Iterable[object], configuration=None
) -> list[dict[str, int]]:
    """Archive each complete raw file, loading only verified observations."""
    import pandas as pd

    evidence = []
    for file in files:
        raw_frame = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
        evidence.append(_load_then_archive(file, raw_frame, configuration))
    return evidence


@observed_entrypoint("ingestion.shares.insert")
def entry_point(request=None):
    from helper import load_files
    from ingestion_configuration import IngestionConfiguration

    configuration = IngestionConfiguration.from_environment()

    process_share_files(load_files(configuration, "shares"), configuration)
    return "Share observations archived; only verified rows were loaded.\n"


if __name__ == "__main__":
    entry_point()
