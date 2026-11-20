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


def _prior_values(plan: Mapping[str, Any]) -> str:
    prior = plan.get("prior_state")
    values = prior.get("values") if isinstance(prior, Mapping) else None
    if not isinstance(values, Mapping):
        raise BaselineComparisonError
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _unrelated_changes(plan: Mapping[str, Any]) -> str:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise BaselineComparisonError
    result: dict[str, list[str]] = {}
    for item in changes:
        if not isinstance(item, Mapping):
            raise BaselineComparisonError
        address = item.get("address")
        change = item.get("change")
        actions = change.get("actions") if isinstance(change, Mapping) else None
        if (
            not isinstance(address, str)
            or not isinstance(change, Mapping)
            or not isinstance(actions, list)
            or not all(isinstance(action, str) for action in actions)
        ):
            raise BaselineComparisonError
        if address in STAGED:
            continue
        result.setdefault(address, []).append(
            json.dumps(change, sort_keys=True, separators=(",", ":"))
        )
    return json.dumps(
        {address: sorted(items) for address, items in result.items()},
        sort_keys=True,
        separators=(",", ":"),
    )


def _output_changes(plan: Mapping[str, Any]) -> str:
    changes = plan.get("output_changes", {})
    if not isinstance(changes, Mapping):
        raise BaselineComparisonError
    return json.dumps(changes, sort_keys=True, separators=(",", ":"))


def classify(baseline: Mapping[str, Any], proposed: Mapping[str, Any]) -> str:
    if _prior_values(baseline) != _prior_values(proposed):
        raise BaselineComparisonError
    if (
        _unrelated_changes(baseline) == _unrelated_changes(proposed)
        and _output_changes(baseline) == _output_changes(proposed)
    ):
        return "matches-development-baseline"
    return "new-or-different-from-development-baseline"


def _load_plan(plan_path: Path, working_directory: Path) -> Mapping[str, Any]:
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
        raise BaselineComparisonError from error
    if not isinstance(value, Mapping):
        raise BaselineComparisonError
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-plan", required=True, type=Path)
    parser.add_argument("--baseline-working-directory", required=True, type=Path)
    parser.add_argument("--proposed-plan", required=True, type=Path)
    parser.add_argument("--proposed-working-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        baseline = _load_plan(args.baseline_plan, args.baseline_working_directory)
        proposed = _load_plan(args.proposed_plan, args.proposed_working_directory)
        classification = classify(baseline, proposed)
    except BaselineComparisonError:
        print("Development baseline comparison: inconclusive.", file=sys.stderr)
        return 1
    print(f"Development baseline comparison: {classification}.")
    return 0 if classification == "matches-development-baseline" else 1


if __name__ == "__main__":
    raise SystemExit(main())
