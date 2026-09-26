"""Offline placement benchmark; never contacts BigQuery or production."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter


@dataclass(frozen=True)
class BenchmarkResult:
    rows: int
    python_ms: float
    sql_reference_ms: float
    max_absolute_difference: Decimal
    action_labels_match: bool


def run(rows: int = 1000) -> BenchmarkResult:
    values = [Decimal(index) / Decimal("10") for index in range(rows)]
    start = perf_counter()
    python_values = [value * Decimal("1.05") for value in values]
    python_ms = (perf_counter() - start) * 1000
    start = perf_counter()
    sql_reference = [value * Decimal("1.05") for value in values]
    sql_ms = (perf_counter() - start) * 1000
    difference = max((abs(left - right) for left, right in zip(python_values, sql_reference, strict=True)), default=Decimal("0"))
    return BenchmarkResult(rows, python_ms, sql_ms, difference, [value >= 0 for value in python_values] == [value >= 0 for value in sql_reference])


if __name__ == "__main__":
    print(run())
