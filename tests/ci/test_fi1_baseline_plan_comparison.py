from __future__ import annotations

from copy import deepcopy
import sys
from typing import Any

import pytest

import scripts.deployment.classify_fi1_baseline_plan as comparator
from scripts.deployment.classify_fi1_baseline_plan import (
    BaselineComparisonError,
    classify,
)
from scripts.deployment.verify_fi1_staging_plan import STAGED


def _plan() -> dict[str, Any]:
    return {
        "prior_state": {"values": {"root_module": {"resources": []}}},
        "resource_changes": [
            {
                "address": "google_storage_bucket.unrelated",
                "change": {
                    "actions": ["update"],
                    "before": {"labels": {"source": "baseline"}},
                    "after": {"labels": {"source": "baseline"}},
                },
            }
        ],
        "output_changes": {},
    }


def test_baseline_comparison_matches_full_unrelated_change_values() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)

    assert classify(baseline, proposed) == "matches-development-baseline"


def test_baseline_comparison_detects_new_unrelated_resource_action() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"].append(
        {
            "address": "google_cloud_run_v2_service.unrelated",
            "change": {"actions": ["create"], "before": None, "after": {"name": "private"}},
        }
    )

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"


def test_baseline_comparison_detects_same_actions_with_different_values() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"][0]["change"]["after"]["labels"]["source"] = "changed"

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"


def test_baseline_comparison_compares_noop_change_values() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    baseline["resource_changes"][0]["change"]["actions"] = ["no-op"]
    proposed["resource_changes"][0]["change"]["actions"] = ["no-op"]
    proposed["resource_changes"][0]["change"]["after"]["labels"]["source"] = "changed"

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"


def test_baseline_comparison_excludes_only_staged_fi1_addresses() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"].append(
        {
            "address": sorted(STAGED)[0],
            "change": {"actions": ["create"], "before": None, "after": {"name": "staged"}},
        }
    )

    assert classify(baseline, proposed) == "matches-development-baseline"


def test_baseline_comparison_fails_closed_on_different_prior_state() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": "private.resource"}
    )

    with pytest.raises(BaselineComparisonError) as error:
        classify(baseline, proposed)
    assert error.value.category == "prior-state-mismatch"


def test_baseline_comparison_distinguishes_malformed_resource_changes() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"] = [{"address": "private", "change": None}]

    with pytest.raises(BaselineComparisonError) as error:
        classify(baseline, proposed)
    assert error.value.category == "malformed-resource-changes"


def test_baseline_comparison_rejects_empty_resource_actions() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"][0]["change"]["actions"] = []

    with pytest.raises(BaselineComparisonError) as error:
        classify(baseline, proposed)
    assert error.value.category == "malformed-resource-changes"


def test_baseline_comparison_distinguishes_malformed_output_changes() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["output_changes"] = ["private"]

    with pytest.raises(BaselineComparisonError) as error:
        classify(baseline, proposed)
    assert error.value.category == "malformed-output-changes"


def test_baseline_comparison_checks_output_values_too() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["output_changes"] = {
        "private_output": {"actions": ["update"], "after": "private"}
    }

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"


def test_cli_outputs_only_fixed_classification(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"].append(
        {
            "address": "google_cloud_run_v2_service.private_resource_identifier",
            "change": {"actions": ["create"], "after": {"name": "private-value"}},
        }
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "classify_fi1_baseline_plan.py",
            "--baseline-plan",
            "baseline.tfplan",
            "--baseline-working-directory",
            "baseline",
            "--proposed-plan",
            "proposed.tfplan",
            "--proposed-working-directory",
            "proposed",
        ],
    )
    monkeypatch.setattr(
        comparator,
        "_load_plan",
        lambda plan_path, _working_directory, _category: baseline
        if plan_path.name.startswith("baseline")
        else proposed,
    )

    assert comparator.main() == 1
    output = capsys.readouterr().out
    assert output == "Development baseline comparison: new-or-different-from-development-baseline.\n"
    assert "private_resource_identifier" not in output
    assert "private-value" not in output


@pytest.mark.parametrize(
    ("failure_phase", "expected_category"),
    [
        ("baseline", "baseline-load-failed"),
        ("proposed", "proposed-load-failed"),
    ],
)
def test_cli_distinguishes_load_phase_without_echoing_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_phase: str,
    expected_category: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "classify_fi1_baseline_plan.py",
            "--baseline-plan",
            "baseline-private-path.tfplan",
            "--baseline-working-directory",
            "private-baseline-directory",
            "--proposed-plan",
            "proposed-private-path.tfplan",
            "--proposed-working-directory",
            "private-proposed-directory",
        ],
    )

    def load_plan(plan_path, _working_directory, category):
        is_baseline = plan_path.name.startswith("baseline")
        if is_baseline == (failure_phase == "baseline"):
            raise BaselineComparisonError(category)
        return _plan()

    monkeypatch.setattr(comparator, "_load_plan", load_plan)

    assert comparator.main() == 1
    diagnostic = capsys.readouterr().err
    assert diagnostic == f"Development baseline comparison: {expected_category}.\n"
    assert "private-path" not in diagnostic
    assert "private-directory" not in diagnostic
