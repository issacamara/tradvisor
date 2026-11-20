"""Compare unrelated plan changes without exposing plan data in workflow logs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

if __package__:
    from scripts.deployment.verify_fi1_staging_plan import STAGED
else:
    from verify_fi1_staging_plan import STAGED


class BaselineComparisonError(ValueError):
    """The plans cannot be compared safely."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


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


def _require_default_workspace(working_directory: Path, phase: str) -> None:
    try:
        workspace = _run_terraform(
            ["workspace", "show"],
            working_directory,
            f"{phase}-workspace-read-failed",
        )
    except BaselineComparisonError as error:
        raise BaselineComparisonError(f"{phase}-workspace-read-failed") from error
    if workspace.strip() != "default":
        raise BaselineComparisonError(f"{phase}-workspace-not-default")


def _backend_state_object_generation(
    working_directory: Path,
    state_bucket: str,
    state_prefix: str,
    gcp_project: str,
    phase: str,
) -> str:
    _require_default_workspace(working_directory, phase)
    normalized_prefix = state_prefix.rstrip("/")
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", state_bucket)
        or not normalized_prefix
        or any(
            segment in {".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9._-]+", segment)
            for segment in normalized_prefix.split("/")
        )
        or not re.fullmatch(r"[a-z][a-z0-9-]+", gcp_project)
    ):
        raise BaselineComparisonError(f"{phase}-state-object-read-failed")
    object_uri = f"gs://{state_bucket}/{normalized_prefix}/default.tfstate"
    try:
        completed = subprocess.run(
            [
                "gcloud",
                "storage",
                "objects",
                "describe",
                object_uri,
                f"--project={gcp_project}",
                "--format=value(generation)",
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise BaselineComparisonError(f"{phase}-state-object-read-failed") from error
    generation = completed.stdout.strip()
    if not re.fullmatch(r"[0-9]+", generation):
        raise BaselineComparisonError(f"{phase}-state-object-read-failed")
    return generation


def _state_generation_change_category(
    before: str, after: str, phase: str
) -> Optional[str]:
    if before != after:
        return f"{phase}-state-object-generation-changed"
    return None


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
    gcp_project: str,
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

    baseline_generation_before = _backend_state_object_generation(
        baseline_directory,
        state_bucket,
        state_prefix,
        gcp_project,
        "baseline",
    )
    _run_terraform(
        ["plan", f"-out={baseline_plan}", "-input=false", "-no-color"],
        baseline_directory,
        "baseline-plan-failed",
    )
    baseline_generation_after = _backend_state_object_generation(
        baseline_directory,
        state_bucket,
        state_prefix,
        gcp_project,
        "baseline",
    )
    change_category = _state_generation_change_category(
        baseline_generation_before, baseline_generation_after, "baseline"
    )
    if change_category:
        raise BaselineComparisonError(change_category)

    proposed_generation_before = _backend_state_object_generation(
        proposed_directory,
        state_bucket,
        state_prefix,
        gcp_project,
        "proposed",
    )
    change_category = _state_generation_change_category(
        baseline_generation_after, proposed_generation_before, "between-plans"
    )
    if change_category:
        raise BaselineComparisonError(change_category)

    _run_terraform(
        ["plan", f"-out={proposed_plan}", "-input=false", "-no-color"],
        proposed_directory,
        "proposed-plan-failed",
    )
    proposed_generation_after = _backend_state_object_generation(
        proposed_directory,
        state_bucket,
        state_prefix,
        gcp_project,
        "proposed",
    )
    change_category = _state_generation_change_category(
        proposed_generation_before, proposed_generation_after, "proposed"
    )
    if change_category:
        raise BaselineComparisonError(change_category)

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
    parser.add_argument("--gcp-project", required=True)
    args = parser.parse_args()
    try:
        classification = compare_with_backend_state(
            baseline_plan=args.baseline_plan,
            baseline_directory=args.baseline_working_directory,
            proposed_plan=args.proposed_plan,
            proposed_directory=args.proposed_working_directory,
            state_bucket=args.state_bucket,
            state_prefix=args.state_prefix,
            gcp_project=args.gcp_project,
        )
    except BaselineComparisonError as error:
        print(f"Development baseline comparison: {error.category}.", file=sys.stderr)
        return 1
    print(f"Development baseline comparison: {classification}.")
    return 0 if classification == "matches-development-baseline" else 1


if __name__ == "__main__":
    raise SystemExit(main())
