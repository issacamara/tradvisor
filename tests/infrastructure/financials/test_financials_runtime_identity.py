from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
IAM = (ROOT / "terraform/iam.tf").read_text()
FUNCTIONS = (ROOT / "terraform/functions.tf").read_text()
BUCKETS = (ROOT / "terraform/buckets.tf").read_text()
VARIABLES = (ROOT / "terraform/variables.tf").read_text()
FI1 = (ROOT / "terraform/fi1_financial.tf").read_text()


def test_legacy_financial_function_identity_and_grants_are_retired() -> None:
    assert 'resource "google_service_account" "financials_runtime"' not in IAM
    assert 'resource "google_secret_manager_secret_iam_member" "financials_openrouter"' not in IAM
    assert "financials_runtime_service_account_id" not in VARIABLES
    assert 'member  = "serviceAccount:${google_service_account.financials_runtime.email}"' not in IAM
    assert '"scrape_financials"' not in VARIABLES.split('variable "functions"', 1)[1].split("\n}", 1)[0]
    assert '"scrape_financials"' not in BUCKETS

    assert 'resource "google_service_account" "fi1_financial_runtime"' in IAM
    assert 'resource "google_secret_manager_secret_iam_member" "fi1_financial_openrouter"' in IAM
    assert 'resource "google_cloud_run_v2_job" "fi1_financials"' in FI1
    assert 'resource "google_service_account" "tradvisor_sa"' in IAM


def test_nonfinancial_function_runtime_stays_on_shared_ingestion_identity() -> None:
    functions = FUNCTIONS.split('resource "google_cloudfunctions2_function" "retained_functions"', 1)[1]
    assert "service_account_email            = google_service_account.tradvisor_sa.email" in functions
    assert 'resource "google_cloudfunctions2_function" "retained_initialization_functions"' in FUNCTIONS
    assert '"scrape_ratings_init"' in VARIABLES
