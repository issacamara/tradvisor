"""Deterministic, immutable envelopes for already-calculated catalog batches."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel

AvailabilityStatus = Literal["available", "unavailable"]


class BatchValidationError(ValueError):
    """Raised when a catalog cannot produce one complete validated batch."""


class InputNotReadyError(BatchValidationError):
    """Raised before output assembly when required source inputs are not ready."""


@dataclass(frozen=True)
class CalculationOutput:
    """One calculation family for a symbol; unavailable results stay explicit."""

    name: str
    status: AvailabilityStatus
    value: Any = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockCalculation:
    """All declared calculation outcomes for one expected catalog symbol."""

    symbol: str
    outputs: tuple[CalculationOutput, ...]


@dataclass(frozen=True)
class OutputAvailability:
    name: str
    status: AvailabilityStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class StockManifestEntry:
    symbol: str
    availability: tuple[OutputAvailability, ...]


@dataclass(frozen=True)
class BatchManifest:
    catalog_id: str
    effective_session: str
    input_snapshot_id: str
    rule_version: str
    revision: int
    batch_id: str
    supersedes_batch_id: str | None
    symbols: tuple[StockManifestEntry, ...]
    content_sha256: str


@dataclass(frozen=True)
class AnalyticalBatch:
    """Canonical outputs and their complete manifest, ready for persistence."""

    batch_id: str
    catalog_id: str
    effective_session: str
    input_snapshot_id: str
    rule_version: str
    revision: int
    supersedes_batch_id: str | None
    stocks: tuple[StockCalculation, ...]
    manifest: BatchManifest


def _canonical(value: Any) -> Any:
    """Convert calculation outputs to deterministic JSON-compatible values."""

    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _canonical(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise BatchValidationError("calculation output mapping keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise BatchValidationError("calculation outputs cannot contain non-finite decimals")
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Enum):
        return _canonical(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not (float("-inf") < value < float("inf")):
            raise BatchValidationError("calculation outputs cannot contain non-finite floats")
        return value
    raise BatchValidationError(f"unsupported calculation output type: {type(value).__name__}")


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _batch_id(
    catalog_id: str, effective_session: str, input_snapshot_id: str, rule_version: str
) -> str:
    identity = _digest((catalog_id, effective_session, input_snapshot_id, rule_version))
    return f"analysis-batch-v1:{identity}"


def _validate_output(output: CalculationOutput) -> None:
    if not output.name or not output.name.strip():
        raise BatchValidationError("calculation output name must be non-empty")
    if output.status == "available":
        if output.value is None or output.reason_codes:
            raise BatchValidationError("available output requires a value and no unavailability reasons")
        _canonical(output.value)
    elif output.status == "unavailable":
        if output.value is not None or not output.reason_codes:
            raise BatchValidationError("unavailable output requires reasons and cannot carry a value")
    else:
        raise BatchValidationError(f"unsupported output status: {output.status!r}")


def build_analytical_batch(
    *,
    catalog_id: str,
    effective_session: str | date,
    input_snapshot_id: str,
    rule_version: str,
    expected_symbols: tuple[str, ...] | list[str],
    expected_output_names: tuple[str, ...] | list[str],
    stocks: tuple[StockCalculation, ...] | list[StockCalculation],
    inputs_ready: bool,
    pending_inputs: tuple[str, ...] = (),
    revision: int = 1,
    supersedes_batch_id: str | None = None,
) -> AnalyticalBatch:
    """Validate and canonically assemble outputs without invoking calculators.

    ``input_snapshot_id`` identifies the catalog-wide immutable input view.
    Corrections use a new input snapshot identity and may point to the prior
    batch through ``supersedes_batch_id``. Callers persist the returned value
    atomically only after this function succeeds.
    """

    if not inputs_ready or pending_inputs:
        raise InputNotReadyError("required analytical inputs are not ready")
    if not all((catalog_id, input_snapshot_id, rule_version)):
        raise BatchValidationError("catalog, input snapshot, and rule version are required")
    session = effective_session.isoformat() if isinstance(effective_session, date) else effective_session
    if not session:
        raise BatchValidationError("effective session is required")
    if revision < 1:
        raise BatchValidationError("batch revision must be positive")
    if (revision == 1) != (supersedes_batch_id is None):
        raise BatchValidationError("revisions after the first must name the batch they supersede")
    if supersedes_batch_id == _batch_id(catalog_id, session, input_snapshot_id, rule_version):
        raise BatchValidationError("a correction must have a new batch identity")

    expected = tuple(sorted(expected_symbols))
    if not expected or any(not symbol for symbol in expected):
        raise BatchValidationError("catalog must declare at least one non-empty symbol")
    if len(set(expected)) != len(expected):
        raise BatchValidationError("catalog symbols must be unique")
    output_names = tuple(sorted(expected_output_names))
    if not output_names or any(not name or not name.strip() for name in output_names):
        raise BatchValidationError("catalog must declare non-empty output families")
    if len(set(output_names)) != len(output_names):
        raise BatchValidationError("catalog output families must be unique")
    by_symbol = {stock.symbol: stock for stock in stocks}
    if len(by_symbol) != len(stocks):
        raise BatchValidationError("each catalog symbol must have exactly one stock result")
    if set(by_symbol) != set(expected):
        raise BatchValidationError("stock results must cover the complete declared catalog")

    canonical_stocks: list[StockCalculation] = []
    manifest_symbols: list[StockManifestEntry] = []
    for symbol in expected:
        stock = by_symbol[symbol]
        names = [output.name for output in stock.outputs]
        if len(set(names)) != len(names):
            raise BatchValidationError(f"duplicate calculation output for {symbol}")
        if set(names) != set(output_names):
            raise BatchValidationError(
                f"calculation outputs for {symbol} must declare every catalog output family"
            )
        for output in stock.outputs:
            _validate_output(output)
        ordered_outputs = tuple(sorted(stock.outputs, key=lambda output: output.name))
        canonical_stocks.append(StockCalculation(symbol, ordered_outputs))
        manifest_symbols.append(
            StockManifestEntry(
                symbol,
                tuple(
                    OutputAvailability(output.name, output.status, output.reason_codes)
                    for output in ordered_outputs
                ),
            )
        )

    batch_id = _batch_id(catalog_id, session, input_snapshot_id, rule_version)
    content_sha256 = _digest(tuple(canonical_stocks))
    manifest = BatchManifest(
        catalog_id=catalog_id,
        effective_session=session,
        input_snapshot_id=input_snapshot_id,
        rule_version=rule_version,
        revision=revision,
        batch_id=batch_id,
        supersedes_batch_id=supersedes_batch_id,
        symbols=tuple(manifest_symbols),
        content_sha256=content_sha256,
    )
    return AnalyticalBatch(
        batch_id=batch_id,
        catalog_id=catalog_id,
        effective_session=session,
        input_snapshot_id=input_snapshot_id,
        rule_version=rule_version,
        revision=revision,
        supersedes_batch_id=supersedes_batch_id,
        stocks=tuple(canonical_stocks),
        manifest=manifest,
    )
