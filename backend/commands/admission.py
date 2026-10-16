"""Trusted admission mutation command; never exposed as an HTTP route."""

from __future__ import annotations

import argparse

from backend.admin.admission import AdmissionDecision, apply_admission_decision
from backend.commands.admin_support import (
    add_common_arguments,
    build_clients,
    emit_failure,
    emit_success,
    logger,
    parse_utc,
    require_identifier,
    valid_action,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply one trusted admission decision")
    add_common_arguments(parser)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--action", required=True, choices=("deny", "grant"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    events = logger("tradvisor.command.admission")
    try:
        operation_id = require_identifier(args.operation_id, field="operation-id")
        operator = require_identifier(args.operator, field="operator")
        subject = require_identifier(args.subject, field="subject")
        action = valid_action(args.action)
        if args.sequence < 1:
            raise ValueError("sequence must be positive")
        clients = build_clients()
        result = apply_admission_decision(
            clients.store,
            AdmissionDecision(
                operation_id=operation_id,
                subject=subject,
                email=args.email,
                action=action,  # type: ignore[arg-type]
                generation=require_identifier(args.generation, field="generation"),
                operator=operator,
                predecessor=(require_identifier(args.predecessor, field="predecessor") if args.predecessor else None),
                sequence=args.sequence,
                created_at=parse_utc(args.created_at),
            ),
        )
        emit_success(events, command="admission", operation_id=operation_id, action=action, sequence=result.decision_sequence, active=result.active)
        return 0
    except Exception as error:
        emit_failure(events, command="admission", operation_id=getattr(args, "operation_id", None), error=error)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised by the container entry point
    raise SystemExit(main())
