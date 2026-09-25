"""Retryable transaction boundary shared by store implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class Transaction(Protocol):
    """Minimal transaction surface required by repository callbacks."""


class TransactionRunner(Protocol):
    """Provider adapter that may invoke the callback more than once."""

    def run(self, callback: Callable[[Transaction], T], *, max_attempts: int) -> T: ...


def run_transaction(
    runner: TransactionRunner,
    callback: Callable[[Transaction], T],
    *,
    max_attempts: int = 5,
) -> T:
    """Run a retryable, side-effect-free callback with a finite retry budget."""

    if not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts must be between 1 and 10")
    return runner.run(callback, max_attempts=max_attempts)
