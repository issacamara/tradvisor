"""Trusted recovery-register command; reopening remains domain-owned and fenced."""

from __future__ import annotations

import argparse

from backend.commands.admin_support import (
    add_common_arguments,
    build_clients,
    emit_failure,
    emit_success,
    logger,
    parse_utc,
    require_identifier,
)
from backend.recovery.register import RUNTIME_SUBJECT, build_intent, confirm_decision, persist_intent, verify_completeness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record one fenced recovery decision")
    add_common_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    events = logger("tradvisor.command.recovery")
    try:
        operation_id = require_identifier(args.operation_id, field="operation-id")
        operator = require_identifier(args.operator, field="operator")
        generation = require_identifier(args.generation, field="generation")
        predecessor = require_identifier(args.predecessor, field="predecessor") if args.predecessor else None
        if args.sequence < 1:
            raise ValueError("sequence must be positive")
        clients = build_clients()
        reconciliation = verify_completeness(clients.store)
        if reconciliation.globally_blocked:
            raise RuntimeError("recovery register is incomplete")
        intent = build_intent(
            operation_id=operation_id,
            subject=RUNTIME_SUBJECT,
            action="recovery",
            generation=generation,
            operator=operator,
            predecessor=predecessor,
            sequence=args.sequence,
            created_at=parse_utc(args.created_at),
        )
        persisted = persist_intent(clients.store, intent)
        head = confirm_decision(clients.store, persisted.operation_id)
        if head.operation_id != operation_id:
            raise RuntimeError("recovery decision did not become the runtime head")
        emit_success(events, command="recovery", operation_id=operation_id, action="recovery", sequence=head.sequence)
        return 0
    except Exception as error:
        emit_failure(events, command="recovery", operation_id=getattr(args, "operation_id", None), error=error)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised by the container entry point
    raise SystemExit(main())
