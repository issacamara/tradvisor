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

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


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
        raise PlanVerificationError("invalid-plan-format")
    if key == "prior_state":
        state_values = state_values.get("values")
        if not isinstance(state_values, Mapping):
            raise PlanVerificationError("invalid-plan-format")
    root = state_values.get("root_module")
    if not isinstance(root, Mapping):
        raise PlanVerificationError("invalid-plan-format")
    addresses = {resource.get("address") for resource in _resources(root)}
    return {address for address in addresses if isinstance(address, str)}


def verify(document: Mapping[str, Any]) -> None:
    prior = _addresses(document, "prior_state")
    planned = _addresses(document, "planned_values")
    if not PROTECTED <= prior or not PROTECTED <= planned:
        raise PlanVerificationError("missing-protected-resources")
    if not STAGED <= planned:
        raise PlanVerificationError("missing-staged-resources")

    resource_changes = document.get("resource_changes")
    if not isinstance(resource_changes, list):
        raise PlanVerificationError("invalid-plan-format")
    changes: dict[str, list[list[str]]] = {}
    for resource_change in resource_changes:
        if not isinstance(resource_change, Mapping):
            raise PlanVerificationError("invalid-plan-format")
        address = resource_change.get("address")
        change = resource_change.get("change")
        actions = change.get("actions") if isinstance(change, Mapping) else None
        if not isinstance(address, str) or not isinstance(actions, list) or not all(
            isinstance(action, str) for action in actions
        ):
            raise PlanVerificationError("invalid-plan-format")
        changes.setdefault(address, []).append(actions)

    for address in PROTECTED:
        if any(actions != ["no-op"] for actions in changes.get(address, [])):
            raise PlanVerificationError("protected-actions")
    for address in STAGED:
        if any(actions not in (["create"], ["no-op"]) for actions in changes.get(address, [])):
            raise PlanVerificationError("staged-actions")
    for address, actions_list in changes.items():
        if address not in PROTECTED and address not in STAGED:
            if any(actions != ["no-op"] for actions in actions_list):
                raise PlanVerificationError("other-actions")


def main() -> int:
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, Mapping):
            raise PlanVerificationError("invalid-plan-format")
        verify(value)
    except PlanVerificationError as error:
        print(
            f"FI-1 staging plan verification failed ({error.category}); inspect private plan evidence.",
            file=sys.stderr,
        )
        return 1
    except (json.JSONDecodeError, OSError):
        print(
            "FI-1 staging plan verification failed (invalid-plan-format); inspect private plan evidence.",
            file=sys.stderr,
        )
        return 1
    print("FI-1 staging plan preservation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
