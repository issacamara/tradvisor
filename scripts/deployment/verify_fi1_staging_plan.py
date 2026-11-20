"""Fail closed when the FI-1 staging plan does not preserve existing resources."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from typing import Any


PROTECTED = frozenset(
    {
        "google_cloud_run_v2_job.fi1_financials[0]",
        "google_cloud_run_v2_job_iam_member.fi1_financial_scheduler_invoker[0]",
        "google_cloud_scheduler_job.fi1_financials[0]",
        "google_bigquery_table.financials",
        "google_bigquery_table.financials_staging",
    }
)
STAGED = frozenset(
    {
        "google_cloud_run_v2_job.fi1_financials_replacement[0]",
        "google_cloud_run_v2_job_iam_member.fi1_financial_replacement_invoker[0]",
    }
)


class PlanVerificationError(ValueError):
    """A plan did not meet the FI-1 staging preservation contract."""


def _resources(module: Mapping[str, Any] | None) -> Iterator[Mapping[str, Any]]:
    if not isinstance(module, Mapping):
        return
    for resource in module.get("resources", []):
        if isinstance(resource, Mapping):
            yield resource
    for child in module.get("child_modules", []):
        if isinstance(child, Mapping):
            yield from _resources(child)


def _addresses(state: Mapping[str, Any], key: str) -> set[str]:
    state_values = state.get(key)
    if not isinstance(state_values, Mapping):
        raise PlanVerificationError("missing plan state")
    if key == "prior_state":
        state_values = state_values.get("values")
        if not isinstance(state_values, Mapping):
            raise PlanVerificationError("missing prior state values")
    root = state_values.get("root_module")
    if not isinstance(root, Mapping):
        raise PlanVerificationError("missing plan root module")
    addresses = {resource.get("address") for resource in _resources(root)}
    return {address for address in addresses if isinstance(address, str)}


def verify(document: Mapping[str, Any]) -> None:
    prior = _addresses(document, "prior_state")
    planned = _addresses(document, "planned_values")
    if not PROTECTED <= prior or not PROTECTED <= planned:
        raise PlanVerificationError("protected resources are absent from plan state")
    if not STAGED <= planned:
        raise PlanVerificationError("staged resources are absent from planned state")

    resource_changes = document.get("resource_changes")
    if not isinstance(resource_changes, list):
        raise PlanVerificationError("missing resource changes")
    changes: dict[str, list[list[str]]] = {}
    for resource_change in resource_changes:
        if not isinstance(resource_change, Mapping):
            raise PlanVerificationError("invalid resource change")
        address = resource_change.get("address")
        change = resource_change.get("change")
        actions = change.get("actions") if isinstance(change, Mapping) else None
        if not isinstance(address, str) or not isinstance(actions, list) or not all(
            isinstance(action, str) for action in actions
        ):
            raise PlanVerificationError("invalid resource change")
        changes.setdefault(address, []).append(actions)

    for address in PROTECTED:
        if any(actions != ["no-op"] for actions in changes.get(address, [])):
            raise PlanVerificationError("protected resource change detected")
    for address in STAGED:
        if any(actions not in (["create"], ["no-op"]) for actions in changes.get(address, [])):
            raise PlanVerificationError("staged resource has an unexpected change")
    for address, actions_list in changes.items():
        if address not in PROTECTED and address not in STAGED:
            if any(actions != ["no-op"] for actions in actions_list):
                raise PlanVerificationError("unexpected resource change detected")


def main() -> int:
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, Mapping):
            raise PlanVerificationError("invalid plan document")
        verify(value)
    except (json.JSONDecodeError, OSError, PlanVerificationError):
        print("FI-1 staging plan verification failed; inspect private plan evidence.", file=sys.stderr)
        return 1
    print("FI-1 staging plan preservation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
