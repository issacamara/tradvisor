from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTROL = (ROOT / "terraform" / "publication_control.tf").read_text()
VARIABLES = (ROOT / "terraform" / "variables.tf").read_text()


def test_publication_control_state_is_isolated_and_protected() -> None:
    assert 'resource "google_storage_bucket" "publication_control"' in CONTROL
    assert "uniform_bucket_level_access = true" in CONTROL
    assert "force_destroy               = false" in CONTROL
    assert "prevent_destroy = true" in CONTROL
    assert 'resource "google_service_account" "publication_control"' in CONTROL
    assert 'resource "google_project_iam_custom_role" "publication_control_state"' in CONTROL
    assert 'resource "google_storage_bucket_iam_member" "publication_control_state"' in CONTROL
    assert '"storage.objects.create"' in CONTROL
    assert '"storage.objects.get"' in CONTROL
    assert '"storage.objects.update"' in CONTROL
    assert '"storage.objects.delete"' not in CONTROL


def test_control_identity_has_only_queue_and_existing_job_invocation_bindings() -> None:
    assert 'resource "google_cloud_tasks_queue" "publication_control_dispatch"' in CONTROL
    assert "max_concurrent_dispatches = 1" in CONTROL
    assert "max_dispatches_per_second = 1" in CONTROL
    assert 'resource "google_cloud_tasks_queue_iam_member" "publication_control_enqueuer"' in CONTROL
    assert 'role     = "roles/cloudtasks.enqueuer"' in CONTROL
    assert 'resource "google_service_account_iam_member" "publication_control_task_token_creator"' in CONTROL
    assert 'role               = "roles/iam.serviceAccountUser"' in CONTROL
    assert 'resource "google_cloud_run_v2_job_iam_member" "publication_control_batch_invoker"' in CONTROL
    assert 'name     = google_cloud_run_v2_job.v1_batch[0].name' in CONTROL
    assert 'role     = "roles/run.invoker"' in CONTROL
    assert 'roles/run.admin' not in CONTROL
    assert 'roles/datastore.user' not in CONTROL


def test_control_resources_remain_opt_in_with_the_v1_runtime() -> None:
    assert "publication_control_enabled = local.v1_runtime_enabled" in CONTROL
    assert 'variable "publication_control_service_account_id"' in VARIABLES
