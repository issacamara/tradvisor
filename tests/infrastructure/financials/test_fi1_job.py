from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
FINANCIAL = (ROOT / "terraform/fi1_financial.tf").read_text()
IAM = (ROOT / "terraform/iam.tf").read_text()
FUNCTIONS = (ROOT / "terraform/functions.tf").read_text()
VARIABLES = (ROOT / "terraform/variables.tf").read_text()
TABLES = (ROOT / "terraform/main.tf").read_text()
OPERATIONS = (ROOT / "docs/operations/fi1-financial-job.md").read_text()


def _block(source: str, declaration: str, name: str) -> str:
    match = re.search(
        rf'{re.escape(declaration)}\s+"{re.escape(name)}"\s*\{{',
        source,
    )
    assert match, f"missing {declaration}.{name}"
    start = match.end()
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"unclosed {declaration}.{name}")


def _resource(source: str, resource_type: str, name: str) -> str:
    return _block(source, f'resource "{resource_type}"', name)


def _variable(name: str) -> str:
    return _block(VARIABLES, "variable", name)


def test_fi1_job_is_disabled_by_default_and_requires_a_digest_image() -> None:
    enabled = _variable("manage_fi1_financial_job")
    image = _variable("fi1_financial_job_image")
    job = _resource(FINANCIAL, "google_cloud_run_v2_job", "fi1_financials")

    assert "default     = false" in enabled
    assert "count               = var.manage_fi1_financial_job ? 1 : 0" in job
    assert 'default     = ""' in image
    assert "@sha256:" in image
    assert "image = var.fi1_financial_job_image" in job
    assert "length(trimspace(var.fi1_financial_job_image)) > 0" in job
    assert "deletion_protection = true" in job
    assert "prevent_destroy = true" in job


def test_job_is_private_bounded_and_injects_only_the_secret_reference() -> None:
    job = _resource(FINANCIAL, "google_cloud_run_v2_job", "fi1_financials")

    assert "task_count  = 1" in job
    assert "parallelism = 1" in job
    assert 'timeout         = "${var.fi1_financial_job_timeout_seconds}s"' in job
    assert "max_retries     = 0" in job
    assert 'cpu    = "1"' in job
    assert 'memory = "2Gi"' in job
    assert 'name = "OPENROUTER_API_KEY"' in job
    assert "value_source" in job and "secret_key_ref" in job
    assert "google_secret_manager_secret.openrouter.secret_id" in job
    assert 'version = "latest"' in job
    assert "secret_data" not in job
    assert "secret_version" not in job
    assert 'name  = "TRADVISOR_FINANCIALS_MODEL_PRIMARY"' in job
    assert 'value = "gemma-4-31b-it"' in job
    assert 'value = "nvidia/nemotron-3.5-lightning:free,openai/gpt-4o-mini"' in job

    for variable, maximum in (
        ("fi1_financial_job_timeout_seconds", "3600"),
        ("fi1_financial_job_max_concurrent_requests", "4"),
        ("fi1_financial_job_max_reports_per_symbol", "5"),
    ):
        assert f"<= {maximum}" in _variable(variable)


def test_job_identity_has_only_required_bigquery_table_and_secret_access() -> None:
    runtime = _resource(IAM, "google_service_account", "fi1_financial_runtime")
    job_user = _resource(IAM, "google_project_iam_member", "fi1_financial_bigquery_job_user")
    firestore = _resource(IAM, "google_project_iam_member", "fi1_financial_firestore")
    companies = _resource(IAM, "google_bigquery_table_iam_member", "fi1_companies_reader")
    financials = _resource(IAM, "google_bigquery_table_iam_member", "fi1_financials_editor")
    staging = _resource(IAM, "google_bigquery_table_iam_member", "fi1_financials_staging_editor")
    secret = _resource(IAM, "google_secret_manager_secret_iam_member", "fi1_financial_openrouter")

    assert "var.fi1_financial_runtime_service_account_id" in runtime
    assert "prevent_destroy = true" in runtime
    assert 'role    = "roles/bigquery.jobUser"' in job_user
    assert 'role    = "roles/datastore.user"' in firestore
    assert "google_service_account.fi1_financial_runtime[0].email" in firestore
    assert "google_bigquery_table.brvm_companies.table_id" in companies
    assert 'role       = "roles/bigquery.dataViewer"' in companies
    assert "google_bigquery_table.financials.table_id" in financials
    assert "google_bigquery_table.financials_staging.table_id" in staging
    assert 'role       = "roles/bigquery.dataEditor"' in financials + staging
    assert "google_secret_manager_secret.openrouter.project" in secret
    assert "google_secret_manager_secret.openrouter.secret_id" in secret
    assert 'role      = "roles/secretmanager.secretAccessor"' in secret
    assert "google_service_account.fi1_financial_runtime[0].email" in (
        job_user + companies + financials + staging + secret
    )

    fi1_iam = "\n".join(
        _resource(IAM, kind, name)
        for kind, name in (
            ("google_project_iam_member", "fi1_financial_bigquery_job_user"),
            ("google_project_iam_member", "fi1_financial_firestore"),
            ("google_bigquery_table_iam_member", "fi1_companies_reader"),
            ("google_bigquery_table_iam_member", "fi1_financials_editor"),
            ("google_bigquery_table_iam_member", "fi1_financials_staging_editor"),
            ("google_secret_manager_secret_iam_member", "fi1_financial_openrouter"),
        )
    )
    assert "storage." not in fi1_iam
    assert "roles/storage" not in fi1_iam
    assert "roles/secretmanager.secretAccessor" not in job_user + companies + financials + staging


def test_monthly_scheduler_invokes_only_the_fi1_job_with_resource_level_iam() -> None:
    scheduler = _resource(FINANCIAL, "google_cloud_scheduler_job", "fi1_financials")
    caller = _resource(IAM, "google_service_account", "fi1_financial_scheduler")
    invoker = _resource(IAM, "google_cloud_run_v2_job_iam_member", "fi1_financial_scheduler_invoker")
    activation = _variable("activate_fi1_financial_schedule")

    assert 'default     = "0 20 1 * *"' in _variable("fi1_financial_job_schedule")
    assert 'time_zone   = "Africa/Bamako"' in scheduler
    assert "run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/" in scheduler
    assert 'http_method = "POST"' in scheduler
    assert "oauth_token" in scheduler
    assert "google_service_account.fi1_financial_scheduler[0].email" in scheduler
    assert "retry_count = 0" in scheduler
    assert "paused      = !var.activate_fi1_financial_schedule" in scheduler
    assert "default     = false" in activation
    assert "var.manage_fi1_financial_job" in activation
    assert "prevent_destroy = true" in scheduler

    assert "prevent_destroy = true" in caller
    assert 'role     = "roles/run.invoker"' in invoker
    assert "google_cloud_run_v2_job.fi1_financials[0].name" in invoker
    assert "serviceAccount:${google_service_account.fi1_financial_scheduler[0].email}" in invoker
    assert "google_project_iam_member" not in invoker


def test_activation_pauses_only_the_legacy_financial_scheduler() -> None:
    legacy_scheduler = _resource(FUNCTIONS, "google_cloud_scheduler_job", "jobs")

    assert "each.value.name == \"financials\" && var.activate_fi1_financial_schedule" in legacy_scheduler
    assert "var.manage_legacy_schedules ? var.jobs : {}" in legacy_scheduler
    assert 'resource "google_workflows_workflow" "workflows"' in FUNCTIONS
    assert 'resource "google_workflows_workflow" "financials_initialization"' in FUNCTIONS
    assert "financials" in OPERATIONS and "later legacy" in OPERATIONS
    assert "historical archive or revision assets" in OPERATIONS


def test_terraform_owned_financial_tables_remain_lifecycle_protected() -> None:
    for name, table in (("financials", "financials"), ("financials_staging", "financials_staging")):
        resource = _resource(TABLES, "google_bigquery_table", name)
        assert re.search(rf'table_id\s*=\s*"{table}"', resource)
        assert "deletion_protection = true" in resource
        assert "prevent_destroy = true" in resource

    assert '"${var.project_id}.stocks.financials"' in FINANCIAL
    assert '"${var.project_id}.stocks.financials_staging"' in FINANCIAL


def test_cloud_run_overlap_limit_and_firestore_lease_contract_are_documented() -> None:
    assert "task_count = 1" in OPERATIONS
    assert "parallelism = 1" in OPERATIONS
    assert "no Terraform" in OPERATIONS
    assert "does not add a lock or other state" in OPERATIONS
    assert "#362" in OPERATIONS
    assert "roles/datastore.user" in OPERATIONS
    assert "Firestore transactional control path" in OPERATIONS
    assert "one-active-execution guarantee" in OPERATIONS
