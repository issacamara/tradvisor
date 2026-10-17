"""Typed transport contracts for the Tradvisor backend."""

from backend.contracts.envelopes import ApiError, ErrorEnvelope, ResponseEnvelope, ResponseMeta
from backend.contracts.analysis import (
    AnalyticalBatch,
    AnalyticalMetric,
    LongTermObjectiveState,
    LongTermResult,
    NormalizedCapital,
    NormalizedCompany,
    NormalizedDividend,
    NormalizedDividendCoverage,
    NormalizedFinancial,
    NormalizedPrice,
    NormalizedRating,
    NormalizedSession,
    Provenance,
    Revision,
)
from backend.contracts.scalars import (
    INT64_MAX,
    INT64_MIN,
    MAX_COMMAND_BYTES,
    MAX_SAFE_INTEGER,
    Money,
    NonNegativeMoney,
)

__all__ = [
    "AnalyticalBatch",
    "AnalyticalMetric",
    "ApiError",
    "ErrorEnvelope",
    "INT64_MAX",
    "INT64_MIN",
    "LongTermResult",
    "LongTermObjectiveState",
    "MAX_COMMAND_BYTES",
    "MAX_SAFE_INTEGER",
    "Money",
    "NonNegativeMoney",
    "NormalizedCapital",
    "NormalizedCompany",
    "NormalizedDividend",
    "NormalizedDividendCoverage",
    "NormalizedFinancial",
    "NormalizedPrice",
    "NormalizedRating",
    "NormalizedSession",
    "Provenance",
    "ResponseEnvelope",
    "ResponseMeta",
    "Revision",
]
