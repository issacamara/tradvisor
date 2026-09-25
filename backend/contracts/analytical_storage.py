"""Additive logical BigQuery table contracts for immutable source revisions.

These catalogs describe a proposed repository contract. They do not assert that
any BigQuery table exists or that a deployment location/schema has been verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BigQueryType = Literal["STRING", "DATE", "TIMESTAMP", "INT64", "NUMERIC"]
BigQueryMode = Literal["REQUIRED", "NULLABLE", "REPEATED"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: BigQueryType
    mode: BigQueryMode = "NULLABLE"


@dataclass(frozen=True)
class TableSpec:
    table_name: str
    version: int
    fields: tuple[FieldSpec, ...]
    immutable_key: tuple[str, ...]
    partition_candidates: tuple[str, ...]

    def __post_init__(self) -> None:
        field_names = tuple(field.name for field in self.fields)
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"{self.table_name} contains duplicate fields")
        if not self.immutable_key or not set(self.immutable_key) <= set(field_names):
            raise ValueError(f"{self.table_name} immutable key must name declared fields")
        if not set(self.partition_candidates) <= set(field_names):
            raise ValueError(f"{self.table_name} partition candidates must name declared fields")


_SOURCE_REVISION_FIELDS = (
    FieldSpec("source_id", "STRING", "REQUIRED"),
    FieldSpec("source_observation_id", "STRING", "REQUIRED"),
    FieldSpec("source_revision_id", "STRING", "REQUIRED"),
    FieldSpec("revision_id", "STRING", "REQUIRED"),
    FieldSpec("source_published_at", "TIMESTAMP"),
    FieldSpec("collected_at", "TIMESTAMP", "REQUIRED"),
    FieldSpec("known_at", "TIMESTAMP", "REQUIRED"),
    FieldSpec("snapshot_uri", "STRING"),
    FieldSpec("snapshot_sha256", "STRING"),
    FieldSpec("parser_version", "STRING", "REQUIRED"),
)


SHARE_PRICE_REVISIONS_V1 = TableSpec(
    table_name="share_price_revisions_v1",
    version=1,
    fields=(
        FieldSpec("symbol", "STRING", "REQUIRED"),
        FieldSpec("session_date", "DATE", "REQUIRED"),
        FieldSpec("revision_id", "STRING", "REQUIRED"),
        *_SOURCE_REVISION_FIELDS[:3],
        FieldSpec("session_date_status", "STRING", "REQUIRED"),
        FieldSpec("trade_status", "STRING", "REQUIRED"),
        FieldSpec("close", "NUMERIC"),
        FieldSpec("high", "NUMERIC"),
        FieldSpec("low", "NUMERIC"),
        FieldSpec("volume", "INT64"),
        FieldSpec("basis", "STRING", "REQUIRED"),
        FieldSpec("original_source_date", "DATE", "REQUIRED"),
        FieldSpec("price_basis_ref", "STRING", "REQUIRED"),
        FieldSpec("validated_available_at", "TIMESTAMP"),
        FieldSpec("actual_xof_turnover", "NUMERIC"),
        FieldSpec("liquidity_basis", "STRING"),
        FieldSpec("suspension_status", "STRING", "REQUIRED"),
        FieldSpec("reason_codes", "STRING", "REPEATED"),
        *_SOURCE_REVISION_FIELDS[4:],
    ),
    immutable_key=("symbol", "session_date", "revision_id"),
    partition_candidates=("session_date", "collected_at"),
)


ANNUAL_FINANCIAL_REVISIONS_V1 = TableSpec(
    table_name="annual_financial_revisions_v1",
    version=1,
    fields=(
        FieldSpec("company_id", "STRING", "REQUIRED"),
        FieldSpec("fiscal_period_start", "DATE", "REQUIRED"),
        FieldSpec("fiscal_period_end", "DATE", "REQUIRED"),
        FieldSpec("report_scope", "STRING", "REQUIRED"),
        FieldSpec("revision_id", "STRING", "REQUIRED"),
        *_SOURCE_REVISION_FIELDS[:3],
        FieldSpec("currency", "STRING", "REQUIRED"),
        FieldSpec("original_scale", "STRING"),
        FieldSpec("revenue", "NUMERIC"),
        FieldSpec("ordinary_owner_earnings", "NUMERIC"),
        FieldSpec("equity", "NUMERIC"),
        FieldSpec("opening_equity", "NUMERIC"),
        FieldSpec("interest_bearing_debt", "NUMERIC"),
        FieldSpec("unrestricted_cash", "NUMERIC"),
        FieldSpec("current_assets", "NUMERIC"),
        FieldSpec("current_liabilities", "NUMERIC"),
        FieldSpec("publication_status", "STRING", "REQUIRED"),
        FieldSpec("reason_codes", "STRING", "REPEATED"),
        *_SOURCE_REVISION_FIELDS[4:],
    ),
    immutable_key=(
        "company_id",
        "fiscal_period_start",
        "fiscal_period_end",
        "report_scope",
        "source_id",
        "source_observation_id",
        "revision_id",
    ),
    partition_candidates=("fiscal_period_end", "collected_at"),
)


ANALYTICAL_SOURCE_TABLES = (
    SHARE_PRICE_REVISIONS_V1,
    ANNUAL_FINANCIAL_REVISIONS_V1,
)
