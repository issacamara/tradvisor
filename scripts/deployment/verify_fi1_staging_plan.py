"""Fail closed when the FI-1 staging plan does not preserve existing resources."""

from __future__ import annotations

import argparse
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
STAGED_REPLACEMENT_JOB = "google_cloud_run_v2_job.fi1_financials_replacement[0]"
RUNTIME_IMAGE_RESOURCES = {
    "google_cloud_run_v2_service.v1_api[0]": "google_cloud_run_v2_service",
    "google_cloud_run_v2_service.publication_control[0]": "google_cloud_run_v2_service",
    "google_cloud_run_v2_job.v1_batch[0]": "google_cloud_run_v2_job",
}
COMPUTED_AFTER_UNKNOWN_FIELDS = frozenset(
    {
        "conditions",
        "create_time",
        "creator",
        "delete_time",
        "effective_annotations",
        "effective_labels",
        "etag",
        "execution_count",
        "expire_time",
        "generation",
        "id",
        "last_modifier",
        "latest_created_execution",
        "latest_created_revision",
        "latest_ready_revision",
        "observed_generation",
        "reconciling",
        "terraform_labels",
        "terminal_condition",
        "traffic_statuses",
        "uid",
        "update_time",
        "uri",
    }
)
COMPUTED_AFTER_UNKNOWN_PATHS = frozenset(
    {
        ("template", "revision"),
        ("template", "0", "revision"),
        ("template", "0", "template", "revision"),
        ("template", "0", "template", "0", "revision"),
    }
)
_MISSING = object()


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


def _planned_resource_values(document: Mapping[str, Any], address: str) -> Mapping[str, Any]:
    planned = document.get("planned_values")
    root = planned.get("root_module") if isinstance(planned, Mapping) else None
    if isinstance(root, Mapping):
        for resource in _resources(root):
            if resource.get("address") == address:
                values = resource.get("values")
                if isinstance(values, Mapping):
                    return values
    raise PlanVerificationError("missing-staged-resources")


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


def _unknown_paths(value: Any, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if value is True:
        return {path}
    if isinstance(value, Mapping):
        return {
            unknown
            for key, child in value.items()
            for unknown in _unknown_paths(child, (*path, str(key)))
        }
    if isinstance(value, list):
        return {
            unknown
            for index, child in enumerate(value)
            for unknown in _unknown_paths(child, (*path, str(index)))
        }
    return set()


def _same_except_image(
    before: Any,
    after: Any,
    unknown_paths: set[tuple[str, ...]],
    image_path: tuple[str, ...],
    path: tuple[str, ...] = (),
) -> bool:
    if path == image_path or any(
        path[: len(unknown)] == unknown for unknown in unknown_paths
    ):
        return True
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        keys = before.keys() | after.keys()
        return all(
            _same_except_image(
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                unknown_paths,
                image_path,
                (*path, str(key)),
            )
            for key in keys
        )
    if isinstance(before, list) and isinstance(after, list):
        return all(
            _same_except_image(
                before[index] if index < len(before) else _MISSING,
                after[index] if index < len(after) else _MISSING,
                unknown_paths,
                image_path,
                (*path, str(index)),
            )
            for index in range(max(len(before), len(after)))
        )
    return before == after


def _block_value(
    value: Mapping[str, Any], key: str, path: tuple[str, ...]
) -> tuple[Mapping[str, Any], tuple[str, ...]]:
    block = value.get(key, _MISSING)
    if isinstance(block, Mapping):
        return block, (*path, key)
    if isinstance(block, list) and len(block) == 1 and isinstance(block[0], Mapping):
        return block[0], (*path, key, "0")
    raise PlanVerificationError("runtime-image-update-invalid")


def _container_image(
    value: Any, address: str
) -> tuple[tuple[str, ...], str]:
    if not isinstance(value, Mapping):
        raise PlanVerificationError("runtime-image-update-invalid")
    current, path = _block_value(value, "template", ())
    if address in {
        "google_cloud_run_v2_job.v1_batch[0]",
        STAGED_REPLACEMENT_JOB,
    }:
        current, path = _block_value(current, "template", path)
    containers = current.get("containers", _MISSING)
    if isinstance(containers, list) and containers and isinstance(containers[0], Mapping):
        container = containers[0]
        image_path = (*path, "containers", "0", "image")
    elif isinstance(containers, Mapping):
        container = containers
        image_path = (*path, "containers", "image")
    else:
        raise PlanVerificationError("runtime-image-update-invalid")
    image = container.get("image")
    if not isinstance(image, str) or not image:
        raise PlanVerificationError("runtime-image-update-invalid")
    return image_path, image


def _check_runtime_image_update(
    resource: Mapping[str, Any], address: str, api_image: str
) -> None:
    if resource.get("mode", "managed") != "managed":
        raise PlanVerificationError("runtime-image-update-invalid")
    if resource.get("type") != RUNTIME_IMAGE_RESOURCES[address]:
        raise PlanVerificationError("runtime-image-update-invalid")
    change = resource.get("change")
    if not isinstance(change, Mapping):
        raise PlanVerificationError("invalid-plan-format")
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise PlanVerificationError("runtime-image-update-invalid")
    before_path, before_image = _container_image(before, address)
    after_path, after_image = _container_image(after, address)
    if before_path != after_path or before_image == after_image or after_image != api_image:
        raise PlanVerificationError("runtime-image-update-invalid")
    raw_unknown = change.get("after_unknown", {})
    if not isinstance(raw_unknown, Mapping):
        raise PlanVerificationError("invalid-plan-format")
    unknown_paths = _unknown_paths(raw_unknown)
    if any(
        not path
        or (
            path[0] not in COMPUTED_AFTER_UNKNOWN_FIELDS
            and path not in COMPUTED_AFTER_UNKNOWN_PATHS
        )
        for path in unknown_paths
    ):
        raise PlanVerificationError("unexplained-unknown-values")
    if not _same_except_image(before, after, unknown_paths, before_path):
        raise PlanVerificationError("runtime-image-update-invalid")


def _check_staged_job_image(
    resource_values: Any, fi1_image: str
) -> None:
    _, image = _container_image(resource_values, STAGED_REPLACEMENT_JOB)
    if image != fi1_image:
        raise PlanVerificationError("staged-image-invalid")


def verify_delivery(
    document: Mapping[str, Any], api_image: str, fi1_image: str | None = None
) -> bool:
    """Check only the initial staged plan; return false for ordinary delivery."""

    prior = _addresses(document, "prior_state")
    planned = _addresses(document, "planned_values")
    if not (STAGED & planned) - prior:
        return False
    if not PROTECTED <= prior or not PROTECTED <= planned:
        raise PlanVerificationError("missing-protected-resources")
    if not STAGED <= planned:
        raise PlanVerificationError("missing-staged-resources")
    if not isinstance(api_image, str) or not api_image:
        raise PlanVerificationError("runtime-image-update-invalid")
    if not isinstance(fi1_image, str) or not fi1_image:
        raise PlanVerificationError("staged-image-invalid")
    _check_staged_job_image(
        _planned_resource_values(document, STAGED_REPLACEMENT_JOB), fi1_image
    )

    resource_changes = document.get("resource_changes")
    if not isinstance(resource_changes, list):
        raise PlanVerificationError("invalid-plan-format")
    changes: dict[str, list[Mapping[str, Any]]] = {}
    for resource in resource_changes:
        if not isinstance(resource, Mapping):
            raise PlanVerificationError("invalid-plan-format")
        address = resource.get("address")
        change = resource.get("change")
        actions = change.get("actions") if isinstance(change, Mapping) else None
        if (
            not isinstance(address, str)
            or not isinstance(actions, list)
            or not actions
            or not all(isinstance(action, str) for action in actions)
        ):
            raise PlanVerificationError("invalid-plan-format")
        changes.setdefault(address, []).append(resource)

    for address in PROTECTED:
        if any(
            resource["change"]["actions"] != ["no-op"]
            for resource in changes.get(address, [])
        ):
            raise PlanVerificationError("protected-actions")
    for address in STAGED:
        staged_changes = changes.get(address, [])
        if address not in prior and not staged_changes:
            raise PlanVerificationError("staged-actions")
        allowed_actions = {"create"} if address not in prior else {"no-op"}
        if any(
            resource["change"]["actions"][0] not in allowed_actions
            or resource["change"]["actions"] not in (["create"], ["no-op"])
            for resource in staged_changes
        ):
            raise PlanVerificationError("staged-actions")
        if address == STAGED_REPLACEMENT_JOB:
            for resource in staged_changes:
                if resource["change"]["actions"] == ["create"]:
                    change = resource["change"]
                    _check_staged_job_image(change.get("after"), fi1_image)
    for address, resources in changes.items():
        if address in PROTECTED or address in STAGED:
            continue
        for resource in resources:
            actions = resource["change"]["actions"]
            if actions == ["no-op"]:
                continue
            if address not in RUNTIME_IMAGE_RESOURCES or actions != ["update"]:
                raise PlanVerificationError("other-actions")
            if address not in prior or address not in planned:
                raise PlanVerificationError("runtime-image-update-invalid")
            _check_runtime_image_update(resource, address, api_image)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-api-image")
    parser.add_argument("--delivery-fi1-image")
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, Mapping):
            raise PlanVerificationError("invalid-plan-format")
        args = parser.parse_args(argv)
        if args.delivery_api_image is None:
            if args.delivery_fi1_image is not None:
                raise PlanVerificationError("invalid-plan-format")
            verify(value)
            staging = None
        else:
            staging = verify_delivery(
                value, args.delivery_api_image, args.delivery_fi1_image
            )
    except PlanVerificationError as error:
        print(
            f"FI-1 plan verification failed ({error.category}); inspect private plan evidence.",
            file=sys.stderr,
        )
        return 1
    except (json.JSONDecodeError, OSError):
        print(
            "FI-1 plan verification failed (invalid-plan-format); inspect private plan evidence.",
            file=sys.stderr,
        )
        return 1
    if staging is None:
        print("FI-1 plan preservation check passed.")
    else:
        print(f"initial_staging={'true' if staging else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
