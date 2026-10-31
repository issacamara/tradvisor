from pathlib import Path
import re


ROOT = Path(__file__).parents[3]
IAM = (ROOT / "terraform/iam.tf").read_text()
FUNCTIONS = (ROOT / "terraform/functions.tf").read_text()
VARIABLES = (ROOT / "terraform/variables.tf").read_text()
DOC = (ROOT / "docs/operations/financials-runtime-identity.md").read_text()


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


def _resource_block(source: str, resource_type: str, name: str) -> str:
    return _block(source, f'resource "{resource_type}"', name)


def test_financials_runtime_account_is_destroy_protected_and_configurable() -> None:
    account = _resource_block(IAM, "google_service_account", "financials_runtime")
    variable = _block(VARIABLES, "variable", "financials_runtime_service_account_id")

    assert "prevent_destroy = true" in account
    assert 'default     = "tradvisor-financials-runtime"' in variable
    assert "validation {" in variable


def test_only_recurring_financials_functions_select_the_dedicated_identity() -> None:
    function_block = _resource_block(FUNCTIONS, "google_cloudfunctions2_function", "functions")
    identity_selection = (
        'contains(["scrape_financials", "insert_financials"], each.key) '
        "? google_service_account.financials_runtime.email : google_service_account.tradvisor_sa.email"
    )

    assert f"service_account_email            = {identity_selection}" in function_block
    assert f"TRADVISOR_INGESTION_SERVICE_ACCOUNT  = {identity_selection}" in function_block
    initialization = _resource_block(
        FUNCTIONS, "google_cloudfunctions2_function", "initialization_functions"
    )
    assert "service_account_email = google_service_account.tradvisor_sa.email" in initialization
    assert "TRADVISOR_INGESTION_SERVICE_ACCOUNT  = google_service_account.tradvisor_sa.email" in initialization
    assert '"scrape_financials_init"' not in identity_selection


def test_financials_runtime_grants_match_documented_nonsecret_inventory() -> None:
    expected = {
        ("google_project_iam_member", "financials_runtime_bigquery_job_user", "roles/bigquery.jobUser"),
        (
            "google_bigquery_dataset_iam_member",
            "financials_runtime_data_editor",
            "roles/bigquery.dataEditor",
        ),
        ("google_storage_bucket_iam_member", "financials_runtime_data_bucket", "roles/storage.objectUser"),
        (
            "google_storage_bucket_iam_member",
            "financials_runtime_archive_bucket",
            "roles/storage.objectUser",
        ),
    }
    for resource_type, name, role in expected:
        assert f'resource "{resource_type}" "{name}"' in IAM
        assert f'"{role}"' in _resource_block(IAM, resource_type, name)

    dedicated_blocks = "\n".join(
        _resource_block(IAM, kind, name)
        for kind, name, _ in expected
    )
    assert "serviceAccount:${google_service_account.financials_runtime.email}" in dedicated_blocks
    assert "roles/secretmanager.secretAccessor" not in dedicated_blocks
    assert "roles/logging.logWriter" not in dedicated_blocks
    assert "roles/storage.admin" not in dedicated_blocks
    assert "google_bigquery_dataset.stocks[count.index].dataset_id" in dedicated_blocks
    assert "count      = var.manage_legacy_bigquery_datasets ? 1 : 0" in dedicated_blocks
    assert "roles/bigquery.dataEditor" in DOC
    assert "roles/storage.objectUser" in DOC


def test_shared_project_bindings_and_other_ingestion_functions_are_preserved() -> None:
    shared = _resource_block(IAM, "google_service_account", "tradvisor_sa")
    assert "prevent_destroy = true" in shared

    for binding in ("function_invoker", "log_writer", "sms_accessor", "bq_data_editor", "storage_admin"):
        block = _resource_block(IAM, "google_project_iam_binding", binding)
        assert "google_service_account.tradvisor_sa.email" in block

    normalized_doc = " ".join(DOC.split())
    assert "all other ingestion functions" in normalized_doc
    assert "invocation grants are unchanged" in normalized_doc
