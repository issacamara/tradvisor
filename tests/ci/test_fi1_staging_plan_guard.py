from __future__ import annotations

import io
import json
import sys
from copy import deepcopy
from typing import Any

import pytest

from scripts.deployment.verify_fi1_staging_plan import (
    PROTECTED,
    STAGED,
    PlanVerificationError,
    main,
    verify,
    verify_delivery,
)

API_IMAGE = "europe-central2-docker.pkg.dev/dev-tradvisor/tradvisor/api@sha256:" + "a" * 64
FI1_IMAGE = "europe-central2-docker.pkg.dev/dev-tradvisor/tradvisor/financial-ingestion@sha256:" + "b" * 64


def _plan() -> dict[str, Any]:
    protected = sorted(PROTECTED)
    staged = sorted(STAGED)
    protected_resources = [
        {"address": address} for address in protected
    ]
    planned_resources = protected_resources + [{"address": address} for address in staged]
    return {
        "format_version": "1.2",
        "prior_state": {"values": {"root_module": {"resources": protected_resources}}},
        "planned_values": {"root_module": {"resources": planned_resources}},
        "resource_changes": [
            {"address": address, "change": {"actions": ["create"]}}
            for address in staged
        ],
    }


def _delivery_plan() -> dict[str, Any]:
    plan = _plan()
    runtime = {
        "google_cloud_run_v2_service.v1_api[0]": (
            "google_cloud_run_v2_service",
            {"template": [{"revision": "old", "containers": [{"image": "old-api"}]}]},
            {"template": [{"revision": None, "containers": [{"image": API_IMAGE}]}]},
            {"template": [{"revision": True}]},
        ),
        "google_cloud_run_v2_service.publication_control[0]": (
            "google_cloud_run_v2_service",
            {"template": {"revision": "old", "containers": [{"image": "old-api"}]}},
            {"template": {"revision": None, "containers": [{"image": API_IMAGE}]}},
            {"template": {"revision": True}},
        ),
        "google_cloud_run_v2_job.v1_batch[0]": (
            "google_cloud_run_v2_job",
            {"template": [{"template": [{"revision": "old", "containers": [{"image": "old-api"}]}]}]},
            {"template": [{"template": [{"revision": None, "containers": [{"image": API_IMAGE}]}]}]},
            {"template": [{"template": [{"revision": True}]}]},
        ),
    }
    prior = plan["prior_state"]["values"]["root_module"]["resources"]
    planned = plan["planned_values"]["root_module"]["resources"]
    replacement_address = "google_cloud_run_v2_job.fi1_financials_replacement[0]"
    replacement_values = {
        "template": [
            {"template": [{"containers": [{"image": FI1_IMAGE}]}]}
        ]
    }
    for resource in planned:
        if resource["address"] == replacement_address:
            resource.update(
                {
                    "mode": "managed",
                    "type": "google_cloud_run_v2_job",
                    "values": replacement_values,
                }
            )
    for resource in plan["resource_changes"]:
        if resource["address"] == replacement_address:
            resource.update({"mode": "managed", "type": "google_cloud_run_v2_job"})
            resource["change"].update(
                {"before": None, "after": replacement_values, "after_unknown": {}}
            )
    for address, (resource_type, before, after, after_unknown) in runtime.items():
        prior.append({"address": address})
        planned.append({"address": address})
        plan["resource_changes"].append(
            {
                "address": address,
                "mode": "managed",
                "type": resource_type,
                "change": {
                    "actions": ["update"],
                    "before": before,
                    "after": after,
                    "after_unknown": after_unknown,
                },
            }
        )
    return plan


def _resource_change(plan: dict[str, Any], address: str) -> dict[str, Any]:
    return next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == address
    )


def test_fi1_staging_plan_allows_only_expected_additions() -> None:
    verify(_plan())


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_protected_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"].append(
        {"address": sorted(PROTECTED)[0], "change": {"actions": actions}}
    )

    with pytest.raises(PlanVerificationError) as error:
        verify(plan)
    assert error.value.category == "protected-actions"


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_unexpected_staged_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"][0]["change"]["actions"] = actions

    with pytest.raises(PlanVerificationError) as error:
        verify(plan)
    assert error.value.category == "staged-actions"


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_unrelated_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"].append(
        {
            "address": "google_cloud_run_v2_service.unrelated[0]",
            "change": {"actions": actions},
        }
    )

    with pytest.raises(PlanVerificationError) as error:
        verify(plan)
    assert error.value.category == "other-actions"


def test_fi1_staging_plan_requires_protected_resources_in_prior_and_planned_state() -> None:
    plan = deepcopy(_plan())
    plan["prior_state"]["values"]["root_module"]["resources"].pop()

    with pytest.raises(PlanVerificationError) as error:
        verify(plan)
    assert error.value.category == "missing-protected-resources"


def test_fi1_staging_plan_requires_replacement_job_and_invoker() -> None:
    plan = deepcopy(_plan())
    plan["planned_values"]["root_module"]["resources"].pop()

    with pytest.raises(PlanVerificationError) as error:
        verify(plan)
    assert error.value.category == "missing-staged-resources"


def test_failure_diagnostic_emits_only_sanitized_category(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan()
    plan["resource_changes"].append(
        {
            "address": "google_cloud_run_v2_service.private_resource_identifier",
            "change": {"actions": ["update"]},
        }
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(plan)))

    assert main([]) == 1
    diagnostic = capsys.readouterr().err
    assert "other-actions" in diagnostic
    assert "private_resource_identifier" not in diagnostic


def test_delivery_guard_allows_only_exact_release_image_updates_on_initial_stage() -> None:
    assert verify_delivery(_delivery_plan(), API_IMAGE, FI1_IMAGE) is True


def test_delivery_guard_handles_partially_staged_prior_state() -> None:
    plan = _delivery_plan()
    existing_staged = sorted(STAGED)[0]
    plan["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": existing_staged}
    )
    for resource in plan["resource_changes"]:
        if resource["address"] == existing_staged:
            resource["change"]["actions"] = ["no-op"]

    assert verify_delivery(plan, API_IMAGE, FI1_IMAGE) is True


def test_delivery_guard_skips_plans_with_no_initial_staged_resources() -> None:
    plan = _plan()
    staged = set(STAGED)
    plan["planned_values"]["root_module"]["resources"] = [
        resource
        for resource in plan["planned_values"]["root_module"]["resources"]
        if resource["address"] not in staged
    ]
    plan["resource_changes"] = []
    plan["resource_changes"].append(
        {"address": "google_project_service.normal_delivery", "change": {"actions": ["delete"]}}
    )

    assert verify_delivery(plan, API_IMAGE, FI1_IMAGE) is False


def test_delivery_guard_rejects_partial_planned_staging() -> None:
    plan = _delivery_plan()
    missing = sorted(STAGED)[0]
    plan["planned_values"]["root_module"]["resources"] = [
        resource
        for resource in plan["planned_values"]["root_module"]["resources"]
        if resource["address"] != missing
    ]

    with pytest.raises(PlanVerificationError) as error:
        verify_delivery(plan, API_IMAGE, FI1_IMAGE)
    assert error.value.category == "missing-staged-resources"


def test_delivery_guard_requires_create_action_for_new_staged_resource() -> None:
    plan = _delivery_plan()
    missing = sorted(STAGED)[0]
    plan["resource_changes"] = [
        resource for resource in plan["resource_changes"] if resource["address"] != missing
    ]

    with pytest.raises(PlanVerificationError) as error:
        verify_delivery(plan, API_IMAGE, FI1_IMAGE)
    assert error.value.category == "staged-actions"


def test_delivery_guard_leaves_ordinary_delivery_unchanged() -> None:
    plan = _delivery_plan()
    prior = plan["prior_state"]["values"]["root_module"]["resources"]
    prior.extend({"address": address} for address in STAGED)
    for resource in plan["resource_changes"]:
        if resource["address"] in STAGED:
            resource["change"]["actions"] = ["no-op"]
    plan["resource_changes"].append(
        {"address": "google_project_service.normal_delivery", "change": {"actions": ["delete"]}}
    )

    assert verify_delivery(plan, API_IMAGE, FI1_IMAGE) is False


def test_delivery_guard_rejects_protected_and_unrelated_destructive_actions() -> None:
    for address in (sorted(PROTECTED)[0], "google_project_service.private_resource"):
        plan = _delivery_plan()
        plan["resource_changes"].append(
            {"address": address, "change": {"actions": ["delete", "create"]}}
        )
        with pytest.raises(PlanVerificationError):
            verify_delivery(plan, API_IMAGE, FI1_IMAGE)


def test_delivery_guard_rejects_staged_updates_and_runtime_replacements() -> None:
    staged = _delivery_plan()
    staged["resource_changes"][0]["change"]["actions"] = ["update"]
    with pytest.raises(PlanVerificationError):
        verify_delivery(staged, API_IMAGE, FI1_IMAGE)

    runtime = _delivery_plan()
    _resource_change(runtime, "google_cloud_run_v2_job.v1_batch[0]")["change"]["actions"] = [
        "delete",
        "create",
    ]
    with pytest.raises(PlanVerificationError):
        verify_delivery(runtime, API_IMAGE, FI1_IMAGE)


def test_delivery_guard_requires_release_image_and_rejects_config_differences() -> None:
    wrong_image = _delivery_plan()
    batch_change = _resource_change(wrong_image, "google_cloud_run_v2_job.v1_batch[0]")["change"]
    batch_change["after"]["template"][0]["template"][0]["containers"][0]["image"] = "private-image"
    with pytest.raises(PlanVerificationError):
        verify_delivery(wrong_image, API_IMAGE, FI1_IMAGE)

    changed_config = _delivery_plan()
    batch_change = _resource_change(changed_config, "google_cloud_run_v2_job.v1_batch[0]")["change"]
    batch_change["after"]["template"][0]["template"][0]["task_count"] = 2
    with pytest.raises(PlanVerificationError):
        verify_delivery(changed_config, API_IMAGE, FI1_IMAGE)


def test_delivery_guard_binds_staged_job_image_to_fi1_release() -> None:
    wrong_create = _delivery_plan()
    replacement = _resource_change(
        wrong_create, "google_cloud_run_v2_job.fi1_financials_replacement[0]"
    )
    replacement["change"]["after"]["template"][0]["template"][0]["containers"][0]["image"] = "private-image"
    with pytest.raises(PlanVerificationError) as error:
        verify_delivery(wrong_create, API_IMAGE, FI1_IMAGE)
    assert error.value.category == "staged-image-invalid"

    partial = _delivery_plan()
    address = "google_cloud_run_v2_job.fi1_financials_replacement[0]"
    partial["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": address}
    )
    _resource_change(partial, address)["change"]["actions"] = ["no-op"]
    planned_job = next(
        resource
        for resource in partial["planned_values"]["root_module"]["resources"]
        if resource["address"] == address
    )
    planned_job["values"]["template"][0]["template"][0]["containers"][0]["image"] = "private-image"
    with pytest.raises(PlanVerificationError) as error:
        verify_delivery(partial, API_IMAGE, FI1_IMAGE)
    assert error.value.category == "staged-image-invalid"


def test_delivery_guard_allows_only_known_computed_unknown_fields() -> None:
    plan = _delivery_plan()
    batch_change = _resource_change(plan, "google_cloud_run_v2_job.v1_batch[0]")["change"]
    batch_change["after_unknown"]["environment_variables"] = True
    with pytest.raises(PlanVerificationError) as error:
        verify_delivery(plan, API_IMAGE, FI1_IMAGE)
    assert error.value.category == "unexplained-unknown-values"


def test_delivery_guard_diagnostic_emits_only_fixed_category(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _delivery_plan()
    batch = _resource_change(plan, "google_cloud_run_v2_job.v1_batch[0]")
    batch["change"]["after"]["template"][0]["template"][0]["task_count"] = "private-value"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(plan)))

    assert main(["--delivery-api-image", API_IMAGE, "--delivery-fi1-image", FI1_IMAGE]) == 1
    diagnostic = capsys.readouterr().err
    assert "runtime-image-update-invalid" in diagnostic
    assert "private-value" not in diagnostic


def test_delivery_guard_emits_only_fixed_staging_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_delivery_plan())))

    assert main(["--delivery-api-image", API_IMAGE, "--delivery-fi1-image", FI1_IMAGE]) == 0
    assert capsys.readouterr().out.strip() == "initial_staging=true"
