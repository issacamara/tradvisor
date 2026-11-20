"""Compare unrelated plan changes without exposing plan data in workflow logs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional, Tuple

if __package__:
    from scripts.deployment.verify_fi1_staging_plan import PROTECTED, STAGED
else:
    from verify_fi1_staging_plan import PROTECTED, STAGED


class BaselineComparisonError(ValueError):
    """The plans cannot be compared safely."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


WORKFLOW_DISPATCHER = "google_cloud_run_v2_service.workflow_dispatcher[0]"
COMPUTED_ENDPOINT_REVISION_FIELDS = {
    "latest_created_revision",
    "latest_ready_revision",
    "uri",
}
_MISSING = object()


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


def _serialize_change_groups(changes: Mapping[str, list[str]]) -> str:
    return json.dumps(
        {address: sorted(items) for address, items in changes.items()},
        sort_keys=True,
        separators=(",", ":"),
    )


def _same_except_image(before: Any, after: Any) -> Tuple[bool, bool]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        if before.keys() != after.keys():
            return False, False
        image_changed = False
        for key in before:
            if key == "image":
                image_changed = image_changed or before[key] != after[key]
                continue
            equal, nested_image_changed = _same_except_image(before[key], after[key])
            if not equal:
                return False, False
            image_changed = image_changed or nested_image_changed
        return True, image_changed
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return False, False
        image_changed = False
        for before_item, after_item in zip(before, after):
            equal, nested_image_changed = _same_except_image(before_item, after_item)
            if not equal:
                return False, False
            image_changed = image_changed or nested_image_changed
        return True, image_changed
    return before == after, False


def _is_image_only_update(item: Mapping[str, Any], change: Mapping[str, Any]) -> bool:
    if item.get("type") not in {
        "google_cloud_run_v2_service",
        "google_cloud_run_v2_job",
    }:
        return False
    if change.get("actions") != ["update"]:
        return False
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return False
    equal_except_image, image_changed = _same_except_image(before, after)
    return equal_except_image and image_changed


def _unrelated_change_groups(
    plan: Mapping[str, Any],
) -> Tuple[str, str, str, str, str, str, str]:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise BaselineComparisonError("malformed-resource-changes")
    non_noop: dict[str, list[str]] = {}
    no_op: dict[str, list[str]] = {}
    data_source_reads: dict[str, list[str]] = {}
    runtime_image_consumers: dict[str, list[str]] = {}
    source_archives: dict[str, list[str]] = {}
    other_managed_actions: dict[str, list[str]] = {}
    image_only_updates: dict[str, list[str]] = {}
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
        target = no_op if actions == ["no-op"] else non_noop
        target.setdefault(address, []).append(serialized_change)
        if actions != ["no-op"]:
            mode = item.get("mode", "managed")
            if mode == "data":
                data_source_reads.setdefault(address, []).append(serialized_change)
            elif item.get("type") in {
                "google_cloud_run_v2_service",
                "google_cloud_run_v2_job",
            }:
                runtime_image_consumers.setdefault(address, []).append(serialized_change)
                if _is_image_only_update(item, change):
                    image_only_updates.setdefault(address, []).append(serialized_change)
            elif item.get("type") == "google_storage_bucket_object" and "src-code" in address:
                source_archives.setdefault(address, []).append(serialized_change)
            else:
                other_managed_actions.setdefault(address, []).append(serialized_change)
    return (
        _serialize_change_groups(non_noop),
        _serialize_change_groups(no_op),
        _serialize_change_groups(data_source_reads),
        _serialize_change_groups(runtime_image_consumers),
        _serialize_change_groups(source_archives),
        _serialize_change_groups(other_managed_actions),
        _serialize_change_groups(image_only_updates),
    )


def _output_changes(plan: Mapping[str, Any]) -> str:
    changes = plan.get("output_changes", {})
    if not isinstance(changes, Mapping):
        raise BaselineComparisonError("malformed-output-changes")
    try:
        return json.dumps(changes, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise BaselineComparisonError("malformed-output-changes") from error


def _action_label(actions: list[str], change: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    if actions == ["create"]:
        return "create"
    if actions == ["delete"]:
        return "delete"
    if actions == ["read"]:
        return "read"
    if len(actions) == 2 and set(actions) == {"create", "delete"}:
        return "replace"
    if actions == ["update"]:
        return "update-image-only" if _is_image_only_update(item, change) else "update-other"
    return "other"


def _unknown_leaf_paths(value: Any, path: Tuple[str, ...] = ()) -> set[Tuple[str, ...]]:
    if value is True:
        return {path}
    if isinstance(value, Mapping):
        return {
            leaf
            for key, child in value.items()
            for leaf in _unknown_leaf_paths(child, (*path, str(key)))
        }
    if isinstance(value, list):
        return {
            leaf
            for index, child in enumerate(value)
            for leaf in _unknown_leaf_paths(child, (*path, str(index)))
        }
    return set()


def _changed_leaf_paths(
    before: Any,
    after: Any,
    unknown_paths: set[Tuple[str, ...]],
    path: Tuple[str, ...] = (),
) -> set[Tuple[str, ...]]:
    if any(path[: len(unknown)] == unknown for unknown in unknown_paths):
        return set()
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        return {
            leaf
            for key in before.keys() | after.keys()
            for leaf in _changed_leaf_paths(
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                unknown_paths,
                (*path, str(key)),
            )
        }
    if isinstance(before, list) and isinstance(after, list):
        changed: set[Tuple[str, ...]] = set()
        for index in range(max(len(before), len(after))):
            old = before[index] if index < len(before) else _MISSING
            new = after[index] if index < len(after) else _MISSING
            changed.update(
                _changed_leaf_paths(old, new, unknown_paths, (*path, str(index)))
            )
        return changed
    if before != after:
        return {path}
    return set()


def _change_categories(item: Mapping[str, Any], change: Mapping[str, Any]) -> set[str]:
    unknown = _unknown_leaf_paths(change.get("after_unknown"))
    categories: set[str] = set()
    for path in _changed_leaf_paths(change.get("before"), change.get("after"), unknown):
        keys = set(path)
        if keys & {"image", "tag"}:
            categories.add("image-tag")
        elif keys & {"client", "labels", "annotations"}:
            categories.add("metadata")
        elif "deletion_protection" in keys:
            categories.add("deletion-protection")
        elif keys & COMPUTED_ENDPOINT_REVISION_FIELDS:
            categories.add("endpoint-revision-computed-only")
        elif "template" in keys:
            categories.add("workload-config")
        else:
            categories.add("other")
    if unknown:
        categories.add("computed-unknown")
    return categories or {"none"}


def _non_noop_group_summary(plan: Mapping[str, Any], label: str) -> str:
    groups: dict[str, set[str]] = {}
    change_categories: dict[str, set[str]] = {}
    for item in plan["resource_changes"]:
        address = item["address"]
        change = item["change"]
        actions = change["actions"]
        if actions == ["no-op"]:
            continue
        if address in PROTECTED:
            group = "protected-fi1"
        elif address in STAGED:
            group = "staged-fi1"
        elif address == WORKFLOW_DISPATCHER:
            group = "workflow-dispatcher"
        elif item.get("mode") == "data":
            group = "data-source-reads"
        elif item.get("type") in {
            "google_cloud_run_v2_service",
            "google_cloud_run_v2_job",
        }:
            group = "runtime-image-consumers"
        elif item.get("type") == "google_storage_bucket_object" and "src-code" in address:
            group = "source-archives"
        else:
            group = "other-managed"
        groups.setdefault(group, set()).add(_action_label(actions, change, item))
        if actions == ["update"] and group in {
            "workflow-dispatcher",
            "runtime-image-consumers",
        }:
            change_categories.setdefault(group, set()).update(
                _change_categories(item, change)
            )

    if not groups:
        return f"{label}-non-noop-groups=none"
    summary = "; ".join(
        f"{group}:{'+'.join(sorted(groups[group]))}"
        + (
            f"[{'+'.join(sorted(change_categories[group]))}]"
            if group in change_categories
            else ""
        )
        for group in sorted(groups)
    )
    return f"{label}-non-noop-groups={summary}"


def classify_with_details(
    baseline: Mapping[str, Any], proposed: Mapping[str, Any]
) -> Tuple[str, str]:
    (
        baseline_non_noop,
        baseline_noop,
        baseline_data_reads,
        baseline_runtime_consumers,
        baseline_source_archives,
        baseline_other_actions,
        baseline_image_updates,
    ) = _unrelated_change_groups(baseline)
    (
        proposed_non_noop,
        proposed_noop,
        proposed_data_reads,
        proposed_runtime_consumers,
        proposed_source_archives,
        proposed_other_actions,
        proposed_image_updates,
    ) = _unrelated_change_groups(proposed)
    non_noop_equal = baseline_non_noop == proposed_non_noop
    noop_equal = baseline_noop == proposed_noop
    outputs_equal = _output_changes(baseline) == _output_changes(proposed)
    classification = (
        "matches-development-baseline"
        if non_noop_equal and noop_equal and outputs_equal
        else "new-or-different-from-development-baseline"
    )

    details = [
        "non-noop-unrelated-changes-identical"
        if non_noop_equal
        else "non-noop-unrelated-changes-differ",
    ]
    if noop_equal:
        details.append("no-op-changes-match")
    elif non_noop_equal and outputs_equal:
        details.append("no-op-only-differences")
    else:
        details.append("no-op-changes-differ")
    if outputs_equal:
        details.append("output-changes-match")
    elif non_noop_equal and noop_equal:
        details.append("output-only-differences")
    else:
        details.append("output-changes-differ")
    details.append(
        "data-source-reads-match"
        if baseline_data_reads == proposed_data_reads
        else "data-source-read-differences"
    )
    details.append(
        "runtime-image-consumers-match"
        if baseline_runtime_consumers == proposed_runtime_consumers
        else "runtime-image-consumer-differences"
    )
    details.append(
        "source-archives-match"
        if baseline_source_archives == proposed_source_archives
        else "source-archive-differences"
    )
    details.append(
        "other-managed-actions-match"
        if baseline_other_actions == proposed_other_actions
        else "other-managed-action-differences"
    )
    details.append(
        "image-only-updates-match"
        if baseline_image_updates == proposed_image_updates
        else "image-only-update-differences"
    )
    return classification, "; ".join(details)


def classify(baseline: Mapping[str, Any], proposed: Mapping[str, Any]) -> str:
    return classify_with_details(baseline, proposed)[0]


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
) -> Tuple[str, str]:
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
    classification, details = classify_with_details(baseline, proposed)
    details = "; ".join(
        (
            details,
            _non_noop_group_summary(baseline, "baseline"),
            _non_noop_group_summary(proposed, "proposed"),
        )
    )
    return classification, details


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
        classification, details = compare_with_backend_state(
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
    print(f"Development baseline comparison details: {details}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
