"""Compare unrelated plan changes without exposing plan data in workflow logs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__:
    from scripts.deployment.verify_fi1_staging_plan import STAGED
else:
    from verify_fi1_staging_plan import STAGED


class BaselineComparisonError(ValueError):
    """The plans cannot be compared safely."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _prior_values(plan: Mapping[str, Any]) -> str:
    prior = plan.get("prior_state")
    values = prior.get("values") if isinstance(prior, Mapping) else None
    if not isinstance(values, Mapping):
        raise BaselineComparisonError("malformed-prior-state")
    try:
        return json.dumps(values, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise BaselineComparisonError("malformed-prior-state") from error


def _unrelated_changes(plan: Mapping[str, Any]) -> str:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise BaselineComparisonError("malformed-resource-changes")
    result: dict[str, list[str]] = {}
    for item in changes:
        if not isinstance(item, Mapping):
            raise BaselineComparisonError("malformed-resource-changes")
        address = item.get("address")
        change = item.get("change")
        actions = change.get("actions") if isinstance(change, Mapping) else None
        if (
            not isinstance(address, str)
            or not isinstance(change, Mapping)
            or not isinstance(actions, list)
            or not actions
            or not all(isinstance(action, str) for action in actions)
        ):
            raise BaselineComparisonError("malformed-resource-changes")
        if address in STAGED:
            continue
        try:
            serialized_change = json.dumps(change, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise BaselineComparisonError("malformed-resource-changes") from error
        result.setdefault(address, []).append(serialized_change)
    return json.dumps(
        {address: sorted(items) for address, items in result.items()},
        sort_keys=True,
        separators=(",", ":"),
    )


def _output_changes(plan: Mapping[str, Any]) -> str:
    changes = plan.get("output_changes", {})
    if not isinstance(changes, Mapping):
        raise BaselineComparisonError("malformed-output-changes")
    try:
        return json.dumps(changes, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise BaselineComparisonError("malformed-output-changes") from error


def classify(baseline: Mapping[str, Any], proposed: Mapping[str, Any]) -> str:
    baseline_state = _prior_values(baseline)
    proposed_state = _prior_values(proposed)
    if baseline_state != proposed_state:
        raise BaselineComparisonError("prior-state-mismatch")
    if (
        _unrelated_changes(baseline) == _unrelated_changes(proposed)
        and _output_changes(baseline) == _output_changes(proposed)
    ):
        return "matches-development-baseline"
    return "new-or-different-from-development-baseline"


def _load_plan(
    plan_path: Path, working_directory: Path, category: str
) -> Mapping[str, Any]:
    try:
        completed = subprocess.run(
            ["terraform", "show", "-json", str(plan_path)],
            cwd=working_directory,
            check=True,
            capture_output=True,
            text=True,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise BaselineComparisonError(category) from error
    if not isinstance(value, Mapping):
        raise BaselineComparisonError(category)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-plan", required=True, type=Path)
    parser.add_argument("--baseline-working-directory", required=True, type=Path)
    parser.add_argument("--proposed-plan", required=True, type=Path)
    parser.add_argument("--proposed-working-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        baseline = _load_plan(
            args.baseline_plan,
            args.baseline_working_directory,
            "baseline-load-failed",
        )
    except BaselineComparisonError as error:
        print(f"Development baseline comparison: {error.category}.", file=sys.stderr)
        return 1
    try:
        proposed = _load_plan(
            args.proposed_plan,
            args.proposed_working_directory,
            "proposed-load-failed",
        )
    except BaselineComparisonError as error:
        print(f"Development baseline comparison: {error.category}.", file=sys.stderr)
        return 1
    try:
        classification = classify(baseline, proposed)
    except BaselineComparisonError as error:
        print(f"Development baseline comparison: {error.category}.", file=sys.stderr)
        return 1
    print(f"Development baseline comparison: {classification}.")
    return 0 if classification == "matches-development-baseline" else 1


if __name__ == "__main__":
    raise SystemExit(main())
