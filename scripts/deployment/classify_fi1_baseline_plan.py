"""Compare unrelated plan changes without exposing plan data in workflow logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Tuple

if __package__:
    from scripts.deployment.verify_fi1_staging_plan import STAGED
else:
    from verify_fi1_staging_plan import STAGED


class BaselineComparisonError(ValueError):
    """The plans cannot be compared safely."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


StateFingerprint = Tuple[str, int, bytes]


def _run_terraform(
    arguments: list[str], working_directory: Path, failure_category: str
) -> str:
    try:
        completed = subprocess.run(
            ["terraform", *arguments],
            cwd=working_directory,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise BaselineComparisonError(failure_category) from error
    return completed.stdout


def _state_fingerprint(working_directory: Path) -> StateFingerprint:
    try:
        state_text = _run_terraform(
            ["state", "pull"], working_directory, "backend-state-read-failed"
        )
        state = json.loads(state_text)
    except (BaselineComparisonError, UnicodeError, json.JSONDecodeError) as error:
        raise BaselineComparisonError("backend-state-read-failed") from error
    if (
        not isinstance(state, Mapping)
        or not isinstance(state.get("lineage"), str)
        or type(state.get("serial")) is not int
    ):
        raise BaselineComparisonError("backend-state-read-failed")
    try:
        canonical_state = json.dumps(state, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise BaselineComparisonError("backend-state-read-failed") from error
    digest = hashlib.sha256(canonical_state.encode("utf-8")).digest()
    return state["lineage"], state["serial"], digest


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
    except (
        OSError,
        UnicodeError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as error:
        raise BaselineComparisonError(category) from error
    if not isinstance(value, Mapping):
        raise BaselineComparisonError(category)
    return value


def compare_with_backend_state(
    *,
    baseline_plan: Path,
    baseline_directory: Path,
    proposed_plan: Path,
    proposed_directory: Path,
    state_bucket: str,
    state_prefix: str,
) -> str:
    backend_args = [
        f"-backend-config=bucket={state_bucket}",
        f"-backend-config=prefix={state_prefix}",
        "-input=false",
        "-no-color",
    ]
    _run_terraform(
        ["init", *backend_args], baseline_directory, "baseline-init-failed"
    )
    _run_terraform(
        ["init", *backend_args], proposed_directory, "proposed-init-failed"
    )

    state_before = _state_fingerprint(baseline_directory)
    _run_terraform(
        ["plan", f"-out={baseline_plan}", "-input=false", "-no-color"],
        baseline_directory,
        "baseline-plan-failed",
    )
    state_between = _state_fingerprint(baseline_directory)
    if state_before != state_between:
        raise BaselineComparisonError("backend-state-changed")

    _run_terraform(
        ["plan", f"-out={proposed_plan}", "-input=false", "-no-color"],
        proposed_directory,
        "proposed-plan-failed",
    )
    state_after = _state_fingerprint(proposed_directory)
    if state_before != state_after:
        raise BaselineComparisonError("backend-state-changed")

    baseline = _load_plan(baseline_plan, baseline_directory, "baseline-load-failed")
    proposed = _load_plan(proposed_plan, proposed_directory, "proposed-load-failed")
    return classify(baseline, proposed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-plan", required=True, type=Path)
    parser.add_argument("--baseline-working-directory", required=True, type=Path)
    parser.add_argument("--proposed-plan", required=True, type=Path)
    parser.add_argument("--proposed-working-directory", required=True, type=Path)
    parser.add_argument("--state-bucket", required=True)
    parser.add_argument("--state-prefix", required=True)
    args = parser.parse_args()
    try:
        classification = compare_with_backend_state(
            baseline_plan=args.baseline_plan,
            baseline_directory=args.baseline_working_directory,
            proposed_plan=args.proposed_plan,
            proposed_directory=args.proposed_working_directory,
            state_bucket=args.state_bucket,
            state_prefix=args.state_prefix,
        )
    except BaselineComparisonError as error:
        print(f"Development baseline comparison: {error.category}.", file=sys.stderr)
        return 1
    print(f"Development baseline comparison: {classification}.")
    return 0 if classification == "matches-development-baseline" else 1


if __name__ == "__main__":
    raise SystemExit(main())
