from __future__ import annotations

from copy import deepcopy
import json
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


def _state(serial: int = 12) -> dict[str, Any]:
    return {
        "version": 4,
        "terraform_version": "1.9.8",
        "serial": serial,
        "lineage": "private-lineage",
        "resources": [{"type": "private_type", "instances": [{"attributes": {"secret": "private"}}]}],
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


def test_baseline_comparison_allows_refresh_variation_with_same_planned_changes() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": "private.resource"}
    )

    assert classify(baseline, proposed) == "matches-development-baseline"


def test_backend_state_stability_distinguishes_refresh_variation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": "refreshed.resource"}
    )
    state_text = json.dumps(_state())

    def run_terraform(arguments, _working_directory, _failure_category):
        return state_text if arguments[:2] == ["state", "pull"] else ""

    monkeypatch.setattr(comparator, "_run_terraform", run_terraform)
    monkeypatch.setattr(
        comparator,
        "_load_plan",
        lambda path, _directory, _category: baseline if path.name.startswith("baseline") else proposed,
    )

    result = comparator.compare_with_backend_state(
        baseline_plan=tmp_path / "baseline.tfplan",
        baseline_directory=tmp_path / "baseline",
        proposed_plan=tmp_path / "proposed.tfplan",
        proposed_directory=tmp_path / "proposed",
        state_bucket="private-bucket",
        state_prefix="private-prefix",
    )

    assert result == "matches-development-baseline"


def test_backend_state_change_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    state_reads = 0

    def run_terraform(arguments, _working_directory, _failure_category):
        nonlocal state_reads
        if arguments[:2] == ["state", "pull"]:
            state_reads += 1
            return json.dumps(_state(serial=12 if state_reads == 1 else 13))
        return ""

    monkeypatch.setattr(comparator, "_run_terraform", run_terraform)

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
        )
    assert error.value.category == "baseline-state-lineage-or-serial-changed"


def test_backend_state_fingerprint_detects_payload_change_with_same_serial(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    state_reads = 0

    def run_terraform(arguments, _working_directory, _failure_category):
        nonlocal state_reads
        if arguments[:2] == ["state", "pull"]:
            state_reads += 1
            state = _state()
            if state_reads == 2:
                state["resources"][0]["instances"][0]["attributes"]["secret"] = "changed"
            return json.dumps(state)
        return ""

    monkeypatch.setattr(comparator, "_run_terraform", run_terraform)

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
        )
    assert error.value.category == "baseline-state-payload-only-changed"


@pytest.mark.parametrize(
    ("change_kind", "expected_category"),
    [
        ("lineage-or-serial", "proposed-state-lineage-or-serial-changed"),
        ("payload", "proposed-state-payload-only-changed"),
    ],
)
def test_proposed_state_diagnostics_identify_difference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    change_kind: str,
    expected_category: str,
) -> None:
    state_reads = 0

    def run_terraform(arguments, _working_directory, _failure_category):
        nonlocal state_reads
        if arguments[:2] != ["state", "pull"]:
            return ""
        state_reads += 1
        state = _state()
        if state_reads == 3:
            if change_kind == "lineage-or-serial":
                state["serial"] += 1
            else:
                state["resources"][0]["instances"][0]["attributes"][
                    "secret"
                ] = "private-changed"
        return json.dumps(state)

    monkeypatch.setattr(comparator, "_run_terraform", run_terraform)
    monkeypatch.setattr(comparator, "_load_plan", lambda *_args: _plan())

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
        )

    assert error.value.category == expected_category
    assert "private-changed" not in str(error.value)


def test_backend_state_read_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def run_terraform(arguments, _working_directory, failure_category):
        if arguments[:2] == ["state", "pull"]:
            raise BaselineComparisonError(failure_category)
        return ""

    monkeypatch.setattr(comparator, "_run_terraform", run_terraform)

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
        )
    assert error.value.category == "baseline-state-read-failed"


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
            "--state-bucket",
            "private-bucket",
            "--state-prefix",
            "private-prefix",
        ],
    )
    monkeypatch.setattr(
        comparator,
        "compare_with_backend_state",
        lambda **_kwargs: "new-or-different-from-development-baseline",
    )

    assert comparator.main() == 1
    output = capsys.readouterr().out
    assert output == "Development baseline comparison: new-or-different-from-development-baseline.\n"
    assert "private-bucket" not in output
    assert "private-prefix" not in output


@pytest.mark.parametrize(
    ("failure_category",),
    [
        ("baseline-state-read-failed",),
        ("baseline-state-lineage-or-serial-changed",),
        ("proposed-state-payload-only-changed",),
        ("baseline-plan-failed",),
    ],
)
def test_cli_distinguishes_backend_failure_without_echoing_private_inputs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_category: str,
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
            "--state-bucket",
            "private-bucket",
            "--state-prefix",
            "private-prefix",
        ],
    )
    monkeypatch.setattr(
        comparator,
        "compare_with_backend_state",
        lambda **_kwargs: (_ for _ in ()).throw(
            BaselineComparisonError(failure_category)
        ),
    )

    assert comparator.main() == 1
    diagnostic = capsys.readouterr().err
    assert diagnostic == f"Development baseline comparison: {failure_category}.\n"
    assert "private-path" not in diagnostic
    assert "private-directory" not in diagnostic
