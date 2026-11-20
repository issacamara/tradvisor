from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts.deployment.verify_fi1_staging_plan import (
    PROTECTED,
    STAGED,
    PlanVerificationError,
    verify,
)


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


def test_fi1_staging_plan_allows_only_expected_additions() -> None:
    verify(_plan())


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_protected_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"].append(
        {"address": sorted(PROTECTED)[0], "change": {"actions": actions}}
    )

    with pytest.raises(PlanVerificationError):
        verify(plan)


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_unexpected_staged_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"][0]["change"]["actions"] = actions

    with pytest.raises(PlanVerificationError):
        verify(plan)


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["update"]])
def test_fi1_staging_plan_rejects_unrelated_resource_changes(actions: list[str]) -> None:
    plan = _plan()
    plan["resource_changes"].append(
        {
            "address": "google_cloud_run_v2_service.unrelated[0]",
            "change": {"actions": actions},
        }
    )

    with pytest.raises(PlanVerificationError):
        verify(plan)


def test_fi1_staging_plan_requires_protected_resources_in_prior_and_planned_state() -> None:
    plan = deepcopy(_plan())
    plan["prior_state"]["values"]["root_module"]["resources"].pop()

    with pytest.raises(PlanVerificationError):
        verify(plan)


def test_fi1_staging_plan_requires_replacement_job_and_invoker() -> None:
    plan = deepcopy(_plan())
    plan["planned_values"]["root_module"]["resources"].pop()

    with pytest.raises(PlanVerificationError):
        verify(plan)
