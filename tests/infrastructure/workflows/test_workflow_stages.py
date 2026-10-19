from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = (ROOT / "terraform" / "functions.tf").read_text()
VARIABLES = (ROOT / "terraform" / "variables.tf").read_text()
IAM = (ROOT / "terraform" / "iam.tf").read_text()
RUNTIME = (ROOT / "terraform" / "runtime.tf").read_text()


def _workflows() -> list[tuple[str, list[str], list[str], str]]:
    return [
            (source, re.findall(r'"([a-z_]+)"', functions), re.findall(r'"([a-z.]+)"', targets), writer_key)
            for source, functions, targets, writer_key in re.findall(
            r'\{\s*source\s*=\s*"([a-z]+)"\s*,\s*functions\s*=\s*(\[[^]]+\])\s*,\s*targets\s*=\s*(\[[^]]+\])\s*,\s*writer_key\s*=\s*"([a-z.]+)"\s*\}',
            FUNCTIONS,
        )
    ]


def test_workflow_sources_and_persistence_stages_are_explicit_and_stable() -> None:
    workflows = _workflows()
    assert workflows == [
        ("shares", ["scrape_shares", "insert_shares"], ["stocks.shares"], "stocks.shares"),
        ("dividends", ["scrape_dividends", "insert_dividends"], ["stocks.dividends"], "stocks.dividends"),
        ("financials", ["scrape_financials"], ["stocks.financials"], "stocks.financials"),
        ("ratings", ["scrape_ratings", "insert_ratings"], ["stocks.ratings"], "stocks.ratings"),
    ]
    target_owners = [target for _, _, targets, _ in workflows for target in targets]
    assert len(target_owners) == len(set(target_owners))
    writer_keys = [writer_key for *_, writer_key in workflows]
    assert writer_keys == target_owners
    assert 'workflow_writer_keys = { for stage in local.workflow_stages : stage.writer_key => stage.source }' in FUNCTIONS
    assert 'resource "google_cloud_tasks_queue" "workflow_writers"' in FUNCTIONS
    assert 'max_concurrent_dispatches = 1' in FUNCTIONS
    assert 'max_dispatches_per_second = 1' in FUNCTIONS
    assert 'cloudtasks.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/queues/${each.value.name}-writer/tasks' in FUNCTIONS
    assert 'google_cloud_run_v2_service.workflow_dispatcher[0].uri}/internal/workflows/${each.value.name}-wf/dispatch' in FUNCTIONS
    assert 'resource "google_cloud_tasks_queue_iam_member" "workflow_queue_enqueuer"' in IAM
    assert 'resource "google_project_iam_member" "workflow_queue_enqueuer"' not in IAM
    assert 'resource "google_cloud_run_v2_service" "workflow_dispatcher"' in RUNTIME
    assert 'INGRESS_TRAFFIC_INTERNAL_ONLY' in RUNTIME
    dispatcher = RUNTIME.split('resource "google_cloud_run_v2_service" "workflow_dispatcher"', 1)[1]
    api = RUNTIME.split('resource "google_cloud_run_v2_service" "workflow_dispatcher"', 1)[0]
    assert 'name  = "WORKER_AUDIENCE"' in dispatcher
    assert 'value = google_cloud_run_v2_service.workflow_dispatcher[0].uri' in dispatcher
    assert 'name  = "WORKER_SERVICE_ACCOUNT"' in dispatcher
    assert 'value = google_service_account.tradvisor_sa.email' in dispatcher
    assert 'name  = "WORKER_AUDIENCE"' not in api


def test_workflow_addresses_remain_count_indexed_and_failures_stop_the_chain() -> None:
    assert re.search(
        r'resource "google_workflows_workflow" "workflows"\s*\{[^}]*'
            r'count\s+= var\.manage_legacy_workflows \? length\(var\.functions\) / 2 : 0',
        FUNCTIONS,
        re.S,
    )
    workflow_block = FUNCTIONS.split(
        'resource "google_workflows_workflow" "workflows"', 1
    )[1].split('resource "google_cloud_tasks_queue"', 1)[0]
    assert "for_each" not in workflow_block
    assert "try:" not in FUNCTIONS
    assert "except:" not in FUNCTIONS


def test_configured_source_schedules_are_enabled_and_managed() -> None:
    assert 'job5 = { name = "financials", schedule = "0 20 1 * *" }' in VARIABLES
    assert 'job6 = { name = "ratings", schedule = "0 20 1 * *" }' in VARIABLES
    assert "paused_schedule_keys = toset([])" in FUNCTIONS
    assert "paused = contains(local.paused_schedule_keys, each.key)" in FUNCTIONS
    assert "prevent_destroy = true" in FUNCTIONS
    assert "ignore_changes  = [description, schedule, time_zone, http_target, paused]" not in FUNCTIONS


def test_scheduler_cloud_tasks_body_uses_rest_api_json_field_names() -> None:
    scheduler = FUNCTIONS.split('resource "google_cloud_scheduler_job" "jobs"', 1)[1]
    payload = scheduler.split("body = base64encode(jsonencode({", 1)[1].split("    }))", 1)[0]

    assert "body = base64encode(jsonencode({" in scheduler
    assert "httpRequest = {" in payload
    assert "httpMethod = \"POST\"" in payload
    assert (
        'url        = "${google_cloud_run_v2_service.workflow_dispatcher[0].uri}'
        '/internal/workflows/${each.value.name}-wf/dispatch"'
    ) in payload
    assert "oidcToken = {" in payload
    assert "serviceAccountEmail = google_service_account.tradvisor_sa.email" in payload
    assert "audience            = google_cloud_run_v2_service.workflow_dispatcher[0].uri" in payload
    assert "http_request" not in payload
    assert "http_method" not in payload
    assert "oauth_token" not in payload
    assert "service_account_email" not in payload
    assert "oauthToken" not in payload
