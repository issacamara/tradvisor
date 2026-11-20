from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.deployment.classify_fi1_baseline_plan as comparator
from scripts.deployment.classify_fi1_baseline_plan import (
    BaselineComparisonError,
    classify,
    classify_with_details,
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
    proposed["resource_changes"][0]["change"]["before"]["labels"]["source"] = "changed-before"
    proposed["resource_changes"][0]["change"]["after"]["labels"]["source"] = "changed"

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"
    _, details = classify_with_details(baseline, proposed)
    assert details == (
        "non-noop-unrelated-changes-differ; no-op-changes-match; "
        "output-changes-match; data-source-reads-match; "
        "runtime-image-consumers-match; source-archives-match; "
        "other-managed-action-differences; image-only-updates-match"
    )


def test_baseline_comparison_compares_noop_change_values() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    baseline["resource_changes"][0]["change"]["actions"] = ["no-op"]
    proposed["resource_changes"][0]["change"]["actions"] = ["no-op"]
    proposed["resource_changes"][0]["change"]["after"]["labels"]["source"] = "changed"

    assert classify(baseline, proposed) == "new-or-different-from-development-baseline"
    _, details = classify_with_details(baseline, proposed)
    assert details == (
        "non-noop-unrelated-changes-identical; no-op-only-differences; "
        "output-changes-match; data-source-reads-match; "
        "runtime-image-consumers-match; source-archives-match; "
        "other-managed-actions-match; image-only-updates-match"
    )


def test_diagnostics_separate_data_reads_runtime_images_and_source_archives() -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["resource_changes"][0]["change"]["after"]["labels"]["source"] = "changed"
    data_read = {
        "address": "data.google_project.current",
        "mode": "data",
        "type": "google_project",
        "change": {"actions": ["read"], "before": None, "after": {"id": "old"}},
    }
    proposed_data_read = deepcopy(data_read)
    proposed_data_read["change"]["after"]["id"] = "new"
    baseline["resource_changes"].append(data_read)
    proposed["resource_changes"].append(proposed_data_read)

    def runtime_change(image: str) -> dict[str, Any]:
        return {
            "address": "google_cloud_run_v2_service.api",
            "mode": "managed",
            "type": "google_cloud_run_v2_service",
            "change": {
                "actions": ["update"],
                "before": {"template": {"containers": [{"image": "old"}]}},
                "after": {"template": {"containers": [{"image": image}]}},
            },
        }

    baseline["resource_changes"].append(runtime_change("old"))
    proposed["resource_changes"].append(runtime_change("new"))
    archive = {
        "address": "google_storage_bucket_object.retained-src-code",
        "mode": "managed",
        "type": "google_storage_bucket_object",
        "change": {"actions": ["update"], "before": {"md5hash": "old"}, "after": {"md5hash": "old"}},
    }
    proposed_archive = deepcopy(archive)
    proposed_archive["change"]["after"]["md5hash"] = "new"
    baseline["resource_changes"].append(archive)
    proposed["resource_changes"].append(proposed_archive)

    _, details = classify_with_details(baseline, proposed)

    assert details == (
        "non-noop-unrelated-changes-differ; no-op-changes-match; "
        "output-changes-match; data-source-read-differences; "
        "runtime-image-consumer-differences; source-archive-differences; "
        "other-managed-action-differences; image-only-update-differences"
    )


def test_non_noop_summary_uses_fixed_groups_and_action_labels() -> None:
    plan = _plan()
    plan["resource_changes"] = [
        {
            "address": "google_cloud_run_v2_service.workflow_dispatcher[0]",
            "type": "google_cloud_run_v2_service",
            "change": {
                "actions": ["update"],
                "before": {"template": {"containers": [{"image": "old"}]}},
                "after": {"template": {"containers": [{"image": "private-image"}]}},
            },
        },
        {
            "address": "data.archive_file.assets",
            "mode": "data",
            "type": "archive_file",
            "change": {"actions": ["read"], "before": None, "after": {"output_md5": "private"}},
        },
        {
            "address": "google_storage_bucket_object.retained-src-code[\"function\"]",
            "type": "google_storage_bucket_object",
            "change": {"actions": ["update"], "before": {"md5": "a"}, "after": {"md5": "b"}},
        },
        {
            "address": "google_cloud_run_v2_job.v1_batch[0]",
            "type": "google_cloud_run_v2_job",
            "change": {"actions": ["delete", "create"], "before": {}, "after": {}},
        },
        {
            "address": "google_project_service.other",
            "type": "google_project_service",
            "change": {"actions": ["create"], "before": None, "after": {}},
        },
        {
            "address": "google_cloud_run_v2_job.fi1_financials_replacement[0]",
            "type": "google_cloud_run_v2_job",
            "change": {"actions": ["create"], "before": None, "after": {}},
        },
    ]

    summary = comparator._non_noop_group_summary(plan, "proposed")

    assert summary == (
        "proposed-non-noop-groups=data-source-reads:read; "
        "other-managed:create; runtime-image-consumers:replace; "
        "source-archives:update-other; staged-fi1:create; "
        "workflow-dispatcher:update-image-only[after-map-present+before-map-present+image-tag]"
    )
    assert "private-image" not in summary
    assert "private" not in summary
    assert "google_" not in summary


def test_change_categories_use_fixed_schema_fields_and_ignore_after_unknown_values() -> None:
    item = {"type": "google_cloud_run_v2_service"}
    change = {
        "before": {
            "template": {"containers": [{"image": "old", "env": [{"value": "secret"}]}]},
            "labels": {"managed-by": "old"},
            "deletion_protection": False,
            "uri": "old-endpoint",
            "display_name": "old-name",
        },
        "after": {
            "template": {"containers": [{"image": "new", "env": [{"value": None}]}]},
            "labels": {"managed-by": "new"},
            "deletion_protection": True,
            "uri": None,
            "display_name": "new-name",
        },
        "after_unknown": {
            "uri": True,
            "template": {"containers": [{"env": [{"value": True}]}]},
        },
    }

    categories = comparator._change_categories(item, change)

    assert categories == {
        "before-map-present",
        "after-map-present",
        "image-tag",
        "declared-metadata",
        "deletion-protection",
        "other-top-level-config",
        "computed-unknown",
    }
    assert comparator._change_categories(
        item, {"before": {"uri": "old"}, "after": {"uri": "new"}}
    ) == {
        "before-map-present",
        "after-map-present",
        "computed-endpoint-revision",
    }
    assert "secret" not in str(categories)
    assert "display_name" not in str(categories)


def test_change_categories_label_public_top_level_cloud_run_fields() -> None:
    item = {"type": "google_cloud_run_v2_service"}
    before = {
        "binary_authorization": {"use_default": True},
        "ingress": "old",
        "launch_stage": "old",
        "client_version": "old",
        "annotations": {"private-key": "old"},
        "custom_audiences": ["old"],
        "description": "old",
        "execution_count": 1,
        "location": "old",
        "name": "old",
        "project": "old",
        "scaling": {"min_instance_count": 0},
        "terraform_labels": {"private-key": "old"},
        "effective_labels": {"private-key": "old"},
        "effective_annotations": {"private-key": "old"},
        "invoker_iam_disabled": False,
        "traffic": [{"percent": 50}],
        "generation": 1,
        "uid": "old",
        "id": "old",
    }
    after = {
        "binary_authorization": {"use_default": False},
        "ingress": "new",
        "launch_stage": "new",
        "client_version": "new",
        "annotations": {"private-key": "new"},
        "custom_audiences": ["new"],
        "description": "new",
        "execution_count": 2,
        "location": "new",
        "name": "new",
        "project": "new",
        "scaling": {"min_instance_count": 1},
        "terraform_labels": {"private-key": "new"},
        "effective_labels": {"private-key": "new"},
        "effective_annotations": {"private-key": "new"},
        "invoker_iam_disabled": True,
        "traffic": [{"percent": 100}],
        "generation": 2,
        "uid": "new",
        "id": "new",
    }

    categories = comparator._change_categories(
        item, {"before": before, "after": after}
    )

    assert categories == {
        "before-map-present",
        "after-map-present",
        "binary-authorization",
        "custom-audiences",
        "description",
        "execution-count",
        "location",
        "name",
        "project",
        "scaling-nonzero-or-other",
        "terraform-id",
        "computed-provider-metadata",
        "ingress",
        "launch-stage",
        "client-version",
        "declared-metadata",
        "terraform-effective-metadata",
        "invoker-iam-check",
        "traffic-config",
        "computed-provider-metadata",
    }
    assert "private-key" not in str(categories)


def test_scaling_diagnostics_normalize_only_zero_and_unset_forms() -> None:
    item = {"type": "google_cloud_run_v2_service"}
    zero_to_unset = comparator._change_categories(
        item,
        {
            "before": {"scaling": [{"min_instance_count": 0}]},
            "after": {"scaling": None},
        },
    )
    unset_to_zero = comparator._change_categories(
        item,
        {
            "before": {"scaling": []},
            "after": {"scaling": {"min_instance_count": 0}},
        },
    )
    capacity_change = comparator._change_categories(
        item,
        {
            "before": {"scaling": {"min_instance_count": 0}},
            "after": {"scaling": {"min_instance_count": 1}},
        },
    )

    assert "scaling-zero-vs-unset" in zero_to_unset
    assert "scaling-zero-vs-unset" in unset_to_zero
    assert "scaling-nonzero-or-other" in capacity_change
    assert "min_instance_count" not in str(zero_to_unset | unset_to_zero | capacity_change)


def test_change_categories_report_non_mapping_before_or_after() -> None:
    categories = comparator._change_categories(
        {"type": "google_cloud_run_v2_service"},
        {"before": None, "after": {}},
    )

    assert categories == {
        "before-map-absent",
        "after-map-present",
        "other-top-level-config",
    }


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


def test_backend_generation_reads_default_workspace_object_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation = {}

    def run_command(arguments, **kwargs):
        invocation["arguments"] = arguments
        invocation["kwargs"] = kwargs
        return SimpleNamespace(stdout="123456789\n")

    monkeypatch.setattr(
        comparator, "_run_terraform", lambda *_args: "default\n"
    )
    monkeypatch.setattr(comparator.subprocess, "run", run_command)

    generation = comparator._backend_state_object_generation(
        working_directory=Path("private-directory"),
        state_bucket="private-bucket",
        state_prefix="private-prefix",
        gcp_project="dev-tradvisor",
        phase="baseline",
    )

    assert generation == "123456789"
    assert invocation["arguments"] == [
        "gcloud",
        "storage",
        "objects",
        "describe",
        "gs://private-bucket/private-prefix/default.tfstate",
        "--project=dev-tradvisor",
        "--format=value(generation)",
        "--quiet",
    ]
    assert invocation["kwargs"]["capture_output"] is True
    assert invocation["kwargs"]["timeout"] == 30


def test_backend_generation_fails_closed_for_non_default_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        comparator, "_run_terraform", lambda *_args: "private-workspace\n"
    )
    monkeypatch.setattr(
        comparator.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("gcloud must not run"),
    )

    with pytest.raises(BaselineComparisonError) as error:
        comparator._backend_state_object_generation(
            working_directory=Path("private-directory"),
            state_bucket="private-bucket",
            state_prefix="private-prefix",
            gcp_project="dev-tradvisor",
            phase="baseline",
        )

    assert error.value.category == "baseline-workspace-not-default"
    assert "private-workspace" not in str(error.value)


def test_backend_generation_fails_closed_when_workspace_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_workspace_read(_arguments, _directory, _failure_category):
        raise BaselineComparisonError("private-workspace-error")

    monkeypatch.setattr(comparator, "_run_terraform", fail_workspace_read)
    monkeypatch.setattr(
        comparator.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("gcloud must not run"),
    )

    with pytest.raises(BaselineComparisonError) as error:
        comparator._backend_state_object_generation(
            working_directory=Path("private-directory"),
            state_bucket="private-bucket",
            state_prefix="private-prefix",
            gcp_project="dev-tradvisor",
            phase="baseline",
        )

    assert error.value.category == "baseline-workspace-read-failed"
    assert "private-workspace-error" not in str(error.value)


def test_backend_generation_read_failure_does_not_expose_command_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        comparator, "_run_terraform", lambda *_args: "default\n"
    )

    def fail_with_private_data(*_args, **_kwargs):
        raise OSError("private-uri private-generation")

    monkeypatch.setattr(comparator.subprocess, "run", fail_with_private_data)

    with pytest.raises(BaselineComparisonError) as error:
        comparator._backend_state_object_generation(
            working_directory=Path("private-directory"),
            state_bucket="private-bucket",
            state_prefix="private-prefix",
            gcp_project="dev-tradvisor",
            phase="baseline",
        )

    assert error.value.category == "baseline-state-object-read-failed"
    assert "private-uri" not in str(error.value)
    assert "private-generation" not in str(error.value)


def test_backend_generation_stability_allows_refresh_variation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    baseline = _plan()
    proposed = deepcopy(baseline)
    proposed["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": "refreshed.resource"}
    )
    monkeypatch.setattr(comparator, "_run_terraform", lambda *_args: "")
    monkeypatch.setattr(
        comparator, "_backend_state_object_generation", lambda *_args: "123"
    )
    monkeypatch.setattr(
        comparator,
        "_load_plan",
        lambda path, _directory, _category: (
            baseline if path.name.startswith("baseline") else proposed
        ),
    )

    result = comparator.compare_with_backend_state(
        baseline_plan=tmp_path / "baseline.tfplan",
        baseline_directory=tmp_path / "baseline",
        proposed_plan=tmp_path / "proposed.tfplan",
        proposed_directory=tmp_path / "proposed",
        state_bucket="private-bucket",
        state_prefix="private-prefix",
        gcp_project="dev-tradvisor",
    )

    assert result[0] == "matches-development-baseline"
    assert result[1].endswith(
        "baseline-non-noop-groups=other-managed:update-other; "
        "proposed-non-noop-groups=other-managed:update-other"
    )


@pytest.mark.parametrize(
    ("generations", "expected_category"),
    [
        (["1", "2"], "baseline-state-object-generation-changed"),
        (["1", "1", "2"], "between-plans-state-object-generation-changed"),
        (["1", "1", "1", "2"], "proposed-state-object-generation-changed"),
    ],
)
def test_state_object_generation_diagnostics_identify_change_phase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    generations: list[str],
    expected_category: str,
) -> None:
    generation_reads = iter(generations)
    monkeypatch.setattr(comparator, "_run_terraform", lambda *_args: "")
    monkeypatch.setattr(
        comparator,
        "_backend_state_object_generation",
        lambda *_args: next(generation_reads),
    )

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
            gcp_project="dev-tradvisor",
        )

    assert error.value.category == expected_category


def test_state_object_generation_read_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def read_generation(*_args):
        raise BaselineComparisonError("baseline-state-object-read-failed")

    monkeypatch.setattr(comparator, "_run_terraform", lambda *_args: "")
    monkeypatch.setattr(comparator, "_backend_state_object_generation", read_generation)

    with pytest.raises(BaselineComparisonError) as error:
        comparator.compare_with_backend_state(
            baseline_plan=tmp_path / "baseline.tfplan",
            baseline_directory=tmp_path / "baseline",
            proposed_plan=tmp_path / "proposed.tfplan",
            proposed_directory=tmp_path / "proposed",
            state_bucket="private-bucket",
            state_prefix="private-prefix",
            gcp_project="dev-tradvisor",
        )

    assert error.value.category == "baseline-state-object-read-failed"


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
    _, details = classify_with_details(baseline, proposed)
    assert details == (
        "non-noop-unrelated-changes-identical; no-op-changes-match; "
        "output-only-differences; data-source-reads-match; "
        "runtime-image-consumers-match; source-archives-match; "
        "other-managed-actions-match; image-only-updates-match"
    )


def test_cli_outputs_only_fixed_classification_and_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
            "--gcp-project",
            "dev-tradvisor",
        ],
    )
    monkeypatch.setattr(
        comparator,
        "compare_with_backend_state",
        lambda **_kwargs: (
            "new-or-different-from-development-baseline",
            "non-noop-unrelated-changes-identical; no-op-changes-match; "
            "output-only-differences; data-source-reads-match; "
            "runtime-image-consumers-match; source-archives-match; "
            "other-managed-actions-match; image-only-updates-match",
        ),
    )

    assert comparator.main() == 0
    output = capsys.readouterr().out
    assert output == (
        "Development baseline comparison: new-or-different-from-development-baseline.\n"
        "Development baseline comparison details: "
        "non-noop-unrelated-changes-identical; no-op-changes-match; "
        "output-only-differences; data-source-reads-match; "
        "runtime-image-consumers-match; source-archives-match; "
        "other-managed-actions-match; image-only-updates-match.\n"
    )
    assert "private-bucket" not in output
    assert "private-prefix" not in output
    assert "private_output" not in output
    assert "private plan value" not in output


def test_cli_reports_identical_non_noop_changes_on_match(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
            "--gcp-project",
            "dev-tradvisor",
        ],
    )
    monkeypatch.setattr(
        comparator,
        "compare_with_backend_state",
        lambda **_kwargs: (
            "matches-development-baseline",
            "non-noop-unrelated-changes-identical; no-op-changes-match; "
            "output-changes-match; data-source-reads-match; "
            "runtime-image-consumers-match; source-archives-match; "
            "other-managed-actions-match; image-only-updates-match",
        ),
    )

    assert comparator.main() == 0
    output = capsys.readouterr().out
    assert output == (
        "Development baseline comparison: matches-development-baseline.\n"
        "Development baseline comparison details: "
        "non-noop-unrelated-changes-identical; no-op-changes-match; "
        "output-changes-match; data-source-reads-match; "
        "runtime-image-consumers-match; source-archives-match; "
        "other-managed-actions-match; image-only-updates-match.\n"
    )


@pytest.mark.parametrize(
    ("failure_category",),
    [
        ("baseline-state-object-read-failed",),
        ("baseline-state-object-generation-changed",),
        ("between-plans-state-object-generation-changed",),
        ("proposed-state-object-generation-changed",),
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
            "--gcp-project",
            "dev-tradvisor",
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
