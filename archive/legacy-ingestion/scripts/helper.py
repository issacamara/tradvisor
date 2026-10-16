"""Shared cloud-backed ingestion helpers.

The module intentionally has no client construction or filesystem activity at
import time.  Entry points that need cloud or parsing libraries import them at
call time so a scheduler, test runner, or parser manifest inspection is safe.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from collections.abc import Callable, Sequence
from typing import Any, Mapping
from uuid import uuid4
from ingestion_observability import emit_event


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _safe_identifier(value: str, field: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"{field} must use only letters, digits, '.', '_' or '-'")
    return value


def get_symbols_from_richbourse(url):
    """Fetch all available symbols from RichBourse dropdown.
    
    Parameters:
    - url: The RichBourse page URL with the symbol dropdown (e.g., ratings or financials page)
    
    Returns:
    - List of symbol strings
    """
    from bs4 import BeautifulSoup
    from curl_cffi import requests as curl_requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    session = curl_requests.Session()
    
    max_retries = 3
    retry_delay = 10  # seconds
    
    for attempt in range(max_retries):
        response = session.get(url, headers=headers, timeout=30, impersonate="chrome", allow_redirects=True)
        
        if response.status_code == 200:
            break
        elif response.status_code == 202:
            print(f"Received 202 (Accepted). Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(retry_delay)
        else:
            raise ValueError(f"Failed to fetch page: {response.status_code}")
    else:
        # If all retries failed or kept returning 202
        raise ValueError("Failed to fetch page: Server repeatedly returned 202 Accepted.")

    
    soup = BeautifulSoup(response.content, 'html.parser')
    select = soup.find('select', {'id': 'symbole'})
    
    if not select:
        raise ValueError("Could not find symbol dropdown")
    
    symbols = []
    for option in select.find_all('option'):
        value = option.get('value', '').strip()
        if value:
            symbols.append(value)
    
    return symbols


def table_exists(table_name='ratings'):
    """Check if the BigQuery table exists.
    
    Parameters:
    - table_name: Name of the table to check (default: 'ratings')
    
    Returns:
    - True if table exists, False otherwise
    """
    from google.auth import default
    from google.cloud import bigquery
    
    credentials, project_id = default()
    client = bigquery.Client(credentials=credentials, project=project_id)
    
    try:
        dataset_ref = client.dataset('stocks')
        table_ref = dataset_ref.table(table_name)
        client.get_table(table_ref)
        return True
    except Exception:
        return False


def parse_french_date(date_text):
    """Parse French date like 'Juillet 2025' to just the year.
    
    Parameters:
    - date_text: French date string (e.g., "Juillet 2025", "Décembre 2024")
    
    Returns:
    - Integer year or None if not found
    """
    year_match = re.search(r'(\d{4})', date_text)
    if year_match:
        return int(year_match.group(1))
    return None

def get_project_number(project_id):
    from google.cloud import resourcemanager_v3

    client = resourcemanager_v3.ProjectsClient()
    project = client.get_project(name=f"projects/{project_id}")
    return project.name.split("/")[1]  # Format is "projects/{project_number}"

def cloud_project(configuration=None):
    """Return credentials plus the validated explicit project target."""
    from google.auth import default

    credentials, project_id = default()
    if hasattr(configuration, "validate_application_default_project"):
        configuration.validate_application_default_project(project_id)
        return credentials, configuration.project_id
    if not project_id:
        raise RuntimeError("cloud ingestion requires an application-default project")
    return credentials, project_id


def save_dataframe_as_csv(df, fin_asset, configuration):
    """Write staged source rows to the configured GCS data bucket."""
    from datetime import datetime

    from google.cloud import storage

    credentials, project_id = cloud_project(configuration)
    filename = f"{fin_asset.lower()}-{datetime.now().strftime('%Y-%m-%d')}.csv"
    bucket_url = (
        configuration.data_bucket
        if configuration is not None
        else f"data-{get_project_number(project_id)}"
    )
    storage.Client(credentials=credentials, project=project_id).bucket(bucket_url).blob(
        filename
    ).upload_from_string(df.to_csv(index=False, sep="|"))
    return f"File saved to GCS bucket '{bucket_url}' as '{filename}'.\n"

def scrape(url):
    import requests
    from bs4 import BeautifulSoup

    params = {
        "hl": "en"  # language
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }
    page = requests.get(url=url, params=params, headers=headers,
                        timeout=30)
    soup = BeautifulSoup(page.content, 'html.parser')
    # Find the table in the HTML (assuming there's only one table)
    table = soup.find('table', {"class": "table table-hover table-striped sticky-enabled"})
    # Extract the headers from the table
    # Extract the header
    headers = []
    header_row = table.find('thead').find_all('th')
    for th in header_row:
        headers.append(th.get_text().strip().replace(' ', "_").upper())
    # Extract the rows from the table
    rows = []
    for tr in table.find('tbody').find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        row = [cell.text.strip() for cell in cells]
        rows.append(row)
    return headers, rows

def move_csv_files_gcp(source_bucket_name, destination_bucket_name, pattern):
    from google.cloud import storage

    # Initialize the storage client
    storage_client = storage.Client()
    # Get the source and destination buckets
    source_bucket = storage_client.bucket(source_bucket_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)

    # List all blobs (files) in the source bucket
    blobs = [blob for blob in source_bucket.list_blobs() if blob.name.startswith(pattern)]

    for blob in blobs:
        # Get the source blob
        source_blob = source_bucket.blob(blob.name)

        # Copy the blob to the destination bucket
        # destination_blob = destination_bucket.blob(blob.name)
        source_bucket.copy_blob(source_blob, destination_bucket, blob.name)

        # Delete the blob from the source bucket
        source_blob.delete()

        print(f'Moved {blob.name} from {source_bucket_name} to {destination_bucket_name}')

def move_csv_file_gcp(source_bucket_name, destination_bucket_name, filename):
    from google.cloud import storage

    storage_client = storage.Client()
    source_bucket = storage_client.bucket(source_bucket_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)
    source_blob = source_bucket.blob(filename)
    source_bucket.copy_blob(source_blob, destination_bucket, filename)
    source_blob.delete()
    print(f'Moved {filename} from {source_bucket_name} to {destination_bucket_name}')

# Define a function to insert data into BigQuery
def insert_into_bigquery(df, project_id, dataset, table):
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    job = client.load_table_from_dataframe(df, table_id)
    job.result()  # Wait for the job to complete


def _load_identity(
    df,
    project_id: str,
    dataset: str,
    table: str,
    source_keys: Sequence[str],
    snapshot_manifest: object | None = None,
) -> str:
    """Return a stable committed identity, anchored to a snapshot when supplied."""

    columns = sorted(str(column) for column in df.columns)
    canonical = df.reindex(columns=columns).drop_duplicates()
    rows = json.loads(
        canonical.to_json(
            orient="records",
            date_format="iso",
            date_unit="us",
            double_precision=15,
            force_ascii=True,
        )
    )
    rows = sorted(_canonical_json(row).decode("utf-8") for row in rows)
    manifest_identity = None
    if snapshot_manifest is not None:
        if isinstance(snapshot_manifest, Mapping):
            source = snapshot_manifest.get("source")
            run_id = snapshot_manifest.get("run_id")
            payload_hash = snapshot_manifest.get("payload_sha256")
            parser_manifest = snapshot_manifest.get("parser_manifest", {})
            parser_name = (
                parser_manifest.get("parser_name")
                if isinstance(parser_manifest, Mapping)
                else getattr(parser_manifest, "parser_name", None)
            )
            parser_version = (
                parser_manifest.get("parser_version")
                if isinstance(parser_manifest, Mapping)
                else getattr(parser_manifest, "parser_version", None)
            )
            parser_hash = (
                parser_manifest.get("configuration_sha256")
                if isinstance(parser_manifest, Mapping)
                else getattr(parser_manifest, "configuration_sha256", None)
            )
        else:
            source = snapshot_manifest.source
            run_id = snapshot_manifest.run_id
            payload_hash = snapshot_manifest.payload_sha256
            parser_name = snapshot_manifest.parser_manifest.parser_name
            parser_version = snapshot_manifest.parser_manifest.parser_version
            parser_hash = snapshot_manifest.parser_manifest.configuration_sha256
        if not all((source, run_id, payload_hash, parser_name, parser_version, parser_hash)):
            raise ValueError("snapshot manifest lacks committed source identity fields")
        manifest_identity = {
            "source": source,
            "run_id": run_id,
            "payload_sha256": payload_hash,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "parser_configuration_sha256": parser_hash,
        }

    identity = {
        "target": f"{project_id}.{dataset}.{table}",
        "source_keys": sorted(source_keys),
        "snapshot": manifest_identity,
        "columns": columns,
        "rows": rows,
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def _sql_identifier(value: str, field: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"{field} contains an invalid BigQuery identifier: {value!r}")
    return f"`{value}`"


# Define a function to upsert data into BigQuery (INSERT OR UPDATE)
def upsert_into_bigquery(
    df,
    project_id,
    dataset,
    table,
    primary_keys,
    *,
    run_id: str | None = None,
    snapshot_manifest: object | None = None,
    update_matched: bool = True,
):
    """Idempotently merge source rows using explicit keys and an isolated stage.
    
    Parameters:
    - df: DataFrame with data to upsert
    - project_id: GCP project ID
    - dataset: BigQuery dataset name
    - table: BigQuery table name
    - primary_keys: Explicit source identity columns for this adapter
    - run_id: Optional unique staging identity, primarily for retry orchestration
    - snapshot_manifest: Immutable acquisition manifest anchoring committed-load identity
    - update_matched: Whether an existing source identity may be updated

    Preconditions: workflow orchestration must allow at most one active writer
    per BigQuery target. This helper provides no distributed lock and is not
    safe for simultaneous insert-first MERGE jobs. Under that serialization,
    rows with the same source keys are updated in place unless
    ``update_matched`` is false. Revision adapters must include their revision
    identity in ``primary_keys`` and disable matched updates.
    """
    from google.cloud import bigquery

    if not primary_keys:
        raise ValueError("primary_keys must contain at least one explicit source key")
    if len(set(primary_keys)) != len(primary_keys):
        raise ValueError("primary_keys must not contain duplicates")
    columns = [str(column) for column in df.columns]
    if len(columns) != len(set(columns)):
        raise ValueError("DataFrame columns must be unique")
    for column in columns:
        _sql_identifier(column, "column")
    for key in primary_keys:
        if key not in columns:
            raise ValueError(f"source key {key!r} is missing from the DataFrame")

    if df.empty:
        return _load_identity(
            df, project_id, dataset, table, primary_keys, snapshot_manifest
        )

    if df[list(primary_keys)].isna().any(axis=None):
        raise ValueError("source keys must not contain null values")
    duplicated_keys = df.duplicated(subset=list(primary_keys), keep=False)
    if duplicated_keys.any():
        conflicting = df.loc[duplicated_keys].duplicated(keep=False)
        if not conflicting.all():
            raise ValueError("staging rows contain conflicting values for the same source key")
    staged_df = df.drop_duplicates(subset=list(primary_keys)).copy()
    committed_load_id = _load_identity(
        staged_df,
        project_id,
        dataset,
        table,
        primary_keys,
        snapshot_manifest,
    )
    run_id = _safe_identifier(run_id or uuid4().hex, "run_id")
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    staging_table_id = f"{table_id}__stage_{run_id}"
    run_label = re.sub(r"[^a-z0-9_-]", "_", run_id.lower())[:63]
    labels = {
        "tradvisor_load_id": committed_load_id[:63],
        "tradvisor_run_id": run_label,
    }
    load_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels=labels,
    )
    try:
        job = client.load_table_from_dataframe(
            staged_df, staging_table_id, job_config=load_config
        )
        job.result()

        # For columns that might be dates, cast them properly
        def get_cast_expression(col):
            col_lower = col.lower()
            
            # Check if column is a datetime (using more specific suffixes/names instead of a broad 'at' check)
            if col_lower.endswith('_at') or 'time' in col_lower:
                # collected_at is in format 'YYYY-MM-DD HH:MM:SS' - use PARSE_TIMESTAMP
                return (
                    "PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', "
                    f"CAST(source.{_sql_identifier(col, 'column')} AS STRING))"
                )
            # Check if column is a date (announcement_date, payment_date)
            elif 'date' in col_lower:
                return (
                    "PARSE_DATE('%Y-%m-%d', "
                    f"CAST(source.{_sql_identifier(col, 'column')} AS STRING))"
                )
            return f"source.{_sql_identifier(col, 'column')}"

        # Source identity is explicit; include revision fields when the source
        # contract requires corrected observations to coexist.
        key_conditions = " AND ".join(
            f"target.{_sql_identifier(key, 'key')} = {get_cast_expression(key)}"
            for key in primary_keys
        )
        update_columns = [column for column in columns if column not in primary_keys]
        update_clause = ""
        if update_matched and update_columns:
            update_clause = "WHEN MATCHED THEN UPDATE SET " + ", ".join(
                f"target.{_sql_identifier(column, 'column')} = {get_cast_expression(column)}"
                for column in update_columns
            )
        insert_columns = ", ".join(_sql_identifier(col, "column") for col in columns)
        insert_values = ", ".join(get_cast_expression(col) for col in columns)
        
        merge_query = f"""
        MERGE `{table_id}` target
        USING `{staging_table_id}` source
        ON {key_conditions}
        {update_clause}
        WHEN NOT MATCHED THEN
          INSERT ({insert_columns})
          VALUES ({insert_values})
        """
        
        # Execute the merge
        merge_config = bigquery.QueryJobConfig(labels=labels)
        client.query(merge_query, job_config=merge_config).result()
        return committed_load_id
        
    finally:
        # Staging is disposable; committed analytical rows are never cleaned up here.
        try:
            client.delete_table(staging_table_id, not_found_ok=True)
        except Exception as e:
            emit_event("ingestion.staging_cleanup", "failed", error_class=type(e).__name__)


def upsert_and_archive(
    df,
    project_id,
    dataset,
    table,
    primary_keys,
    archive: Callable[[], Any],
    *,
    run_id: str | None = None,
    snapshot_manifest: object | None = None,
):
    """Commit an idempotent load before archiving its source evidence."""

    committed_load_id = upsert_into_bigquery(
        df,
        project_id,
        dataset,
        table,
        primary_keys,
        run_id=run_id,
        snapshot_manifest=snapshot_manifest,
    )
    archive()
    return committed_load_id


def upsert_shares_and_archive(
    df,
    project_id: str,
    dataset: str,
    archive: Callable[[], Any],
    *,
    run_id: str | None = None,
):
    """Append one serialized share run to managed staging before merging it."""
    from google.cloud import bigquery

    columns = [str(column) for column in df.columns]
    expected_columns = [
        "symbol",
        "name",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "date",
    ]
    if columns != expected_columns:
        raise ValueError("share rows must match the managed shares staging schema")
    if df.empty:
        archive()
        return _load_identity(df, project_id, dataset, "shares", ["symbol", "date"])
    if df[["symbol", "date"]].isna().any(axis=None):
        raise ValueError("share source keys must not contain null values")

    staged_rows = df.drop_duplicates(subset=["symbol", "date"]).copy()
    committed_load_id = _load_identity(
        staged_rows, project_id, dataset, "shares", ["symbol", "date"]
    )
    resolved_run_id = _safe_identifier(run_id or uuid4().hex, "run_id")
    staging_table_id = f"{project_id}.{dataset}.shares_staging"
    table_id = f"{project_id}.{dataset}.shares"
    labels = {
        "tradvisor_load_id": committed_load_id[:63],
        "tradvisor_run_id": re.sub(r"[^a-z0-9_-]", "_", resolved_run_id.lower())[:63],
    }
    query_parameters = [
        bigquery.ScalarQueryParameter("run_id", "STRING", resolved_run_id)
    ]
    scoped_config = bigquery.QueryJobConfig(
        labels=labels, query_parameters=query_parameters
    )
    cleanup_query = f"DELETE FROM `{staging_table_id}` WHERE `run_id` = @run_id"

    # The shares writer queue serializes this cleanup with its append/merge run.
    client = bigquery.Client(project=project_id)
    client.query(cleanup_query, job_config=scoped_config).result()
    staged_rows.insert(0, "run_id", resolved_run_id)
    load_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        labels=labels,
    )
    try:
        client.load_table_from_dataframe(
            staged_rows, staging_table_id, job_config=load_config
        ).result()
        assignments = ", ".join(
            f"target.{_sql_identifier(column, 'column')} = source.{_sql_identifier(column, 'column')}"
            for column in expected_columns
            if column not in {"symbol", "date"}
        )
        insert_columns = ", ".join(
            _sql_identifier(column, "column") for column in expected_columns
        )
        insert_values = ", ".join(
            f"source.{_sql_identifier(column, 'column')}" for column in expected_columns
        )
        merge_query = f"""
        MERGE `{table_id}` target
        USING (
          SELECT {insert_columns}
          FROM `{staging_table_id}`
          WHERE `run_id` = @run_id
        ) source
        ON target.`symbol` = source.`symbol` AND target.`date` = source.`date`
        WHEN MATCHED THEN UPDATE SET {assignments}
        WHEN NOT MATCHED THEN
          INSERT ({insert_columns})
          VALUES ({insert_values})
        """
        client.query(merge_query, job_config=scoped_config).result()
    finally:
        client.query(cleanup_query, job_config=scoped_config).result()

    archive()
    return committed_load_id


def upsert_financials_and_archive(
    df,
    revision_df,
    project_id: str,
    dataset: str,
    archive: Callable[[], Any],
    *,
    run_id: str | None = None,
):
    """Append one serialized financial run to managed staging before merging it."""
    from google.cloud import bigquery

    columns = [str(column) for column in df.columns]
    expected_columns = [
        "symbol",
        "fiscal_year",
        "revenue",
        "net_income",
        "total_debt",
        "cash_and_cash_equivalents",
        "total_equity",
        "document_link",
        "collected_at",
    ]
    if columns != expected_columns:
        raise ValueError("financial rows must match the managed financials staging schema")
    if df.empty:
        archive()
        return _load_identity(df, project_id, dataset, "financials", ["symbol", "fiscal_year"])
    if df[["symbol", "fiscal_year"]].isna().any(axis=None):
        raise ValueError("financial source keys must not contain null values")

    staged_rows = df.drop_duplicates(subset=["symbol", "fiscal_year"]).copy()
    committed_load_id = _load_identity(
        staged_rows, project_id, dataset, "financials", ["symbol", "fiscal_year"]
    )
    resolved_run_id = _safe_identifier(run_id or uuid4().hex, "run_id")
    staging_table_id = f"{project_id}.{dataset}.financials_staging"
    table_id = f"{project_id}.{dataset}.financials"
    labels = {
        "tradvisor_load_id": committed_load_id[:63],
        "tradvisor_run_id": re.sub(r"[^a-z0-9_-]", "_", resolved_run_id.lower())[:63],
    }
    query_parameters = [
        bigquery.ScalarQueryParameter("run_id", "STRING", resolved_run_id)
    ]
    scoped_config = bigquery.QueryJobConfig(
        labels=labels, query_parameters=query_parameters
    )
    cleanup_query = f"DELETE FROM `{staging_table_id}` WHERE `run_id` = @run_id"

    client = bigquery.Client(project=project_id)
    client.query(cleanup_query, job_config=scoped_config).result()
    staged_rows.insert(0, "run_id", resolved_run_id)
    load_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        labels=labels,
    )
    try:
        client.load_table_from_dataframe(
            staged_rows, staging_table_id, job_config=load_config
        ).result()
        assignments = ", ".join(
            f"target.{_sql_identifier(column, 'column')} = source.{_sql_identifier(column, 'column')}"
            for column in expected_columns
            if column not in {"symbol", "fiscal_year"}
        )
        insert_columns = ", ".join(
            _sql_identifier(column, "column") for column in expected_columns
        )
        insert_values = ", ".join(
            f"source.{_sql_identifier(column, 'column')}" for column in expected_columns
        )
        merge_query = f"""
        MERGE `{table_id}` target
        USING (
          SELECT {insert_columns}
          FROM `{staging_table_id}`
          WHERE `run_id` = @run_id
        ) source
        ON target.`symbol` = source.`symbol`
           AND target.`fiscal_year` = source.`fiscal_year`
        WHEN MATCHED THEN UPDATE SET {assignments}
        WHEN NOT MATCHED THEN
          INSERT ({insert_columns})
          VALUES ({insert_values})
        """
        client.query(merge_query, job_config=scoped_config).result()
    finally:
        client.query(cleanup_query, job_config=scoped_config).result()

    if revision_df is not None:
        upsert_financial_report_revision(revision_df, project_id, dataset)
    archive()
    return committed_load_id


def upsert_financial_report_revision(df, project_id, dataset="stocks"):
    """Insert an immutable report revision into the provisioned history table.

    The ``financial_report_revisions`` schema is provisioned outside runtime by
    the approved infrastructure path. A retry of the same revision is a no-op,
    even if a later parser invocation produces different values.
    """

    revision_rows = df.copy()
    if "document_revision" not in revision_rows.columns:
        raise ValueError("financial report revision requires document_revision")
    return upsert_into_bigquery(
        revision_rows,
        project_id,
        dataset,
        "financial_report_revisions",
        ["symbol", "fiscal_year", "document_link", "document_revision"],
        update_matched=False,
    )


def get_financial_report_revision(
    symbol,
    fiscal_year,
    document_link,
    document_revision,
    project_id,
    dataset="stocks",
):
    """Return a committed extraction; an unprovisioned history table fails closed."""
    from google.cloud import bigquery

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", project_id):
        raise ValueError("project_id contains an invalid BigQuery project identifier")
    dataset_id = _sql_identifier(dataset, "dataset").strip("`")
    table_name = _sql_identifier("financial_report_revisions", "table").strip("`")
    table_id = f"`{project_id}.{dataset_id}.{table_name}`"
    revision_clause = (
        "AND document_revision = @document_revision"
        if document_revision is not None
        else ""
    )
    query = f"""
    SELECT revenue, net_income, total_debt, cash_and_cash_equivalents, total_equity
    FROM {table_id}
    WHERE symbol = @symbol
      AND fiscal_year = @fiscal_year
      AND document_link = @document_link
      {revision_clause}
    LIMIT 1
    """
    client = bigquery.Client(project=project_id)
    parameters = [
        bigquery.ScalarQueryParameter("symbol", "STRING", symbol),
        bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
        bigquery.ScalarQueryParameter("document_link", "STRING", document_link),
    ]
    if document_revision is not None:
        parameters.append(
            bigquery.ScalarQueryParameter(
                "document_revision", "STRING", document_revision
            )
        )
    config = bigquery.QueryJobConfig(query_parameters=parameters)
    rows = list(client.query(query, job_config=config).result())
    if not rows:
        return None
    row = rows[0]
    return dict(row.items()) if hasattr(row, "items") else dict(row)


def upsert_financial_report_current_and_revision(df, project_id, dataset="stocks"):
    """Write the current projection before its immutable source revision."""
    if "document_revision" not in df.columns:
        raise ValueError("financial report revision requires document_revision")
    current_rows = df.drop(columns=["document_revision"])
    upsert_into_bigquery(
        current_rows,
        project_id,
        dataset,
        "financials",
        ["symbol", "fiscal_year"],
    )
    return upsert_financial_report_revision(df, project_id, dataset)


def upsert_financial_report_and_archive(
    current_df, revision_df, project_id, archive, *, dataset="stocks"
):
    """Commit current and immutable revision rows before archiving the PDF."""

    def commit_revision_and_archive():
        upsert_financial_report_revision(revision_df, project_id, dataset)
        archive()

    return upsert_and_archive(
        current_df,
        project_id,
        dataset,
        "financials",
        ["symbol", "fiscal_year"],
        commit_revision_and_archive,
    )

def process_files(configuration, files, asset):
    import pandas as pd
    credentials, project_id = cloud_project(configuration)
    source_bucket = (
        configuration.data_bucket
        if configuration is not None
        else f"data-{get_project_number(project_id)}"
    )
    archive_bucket = (
        configuration.archive_bucket
        if configuration is not None
        else f"archive-{get_project_number(project_id)}"
    )
    for file in files:
        df = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
        df["date"] = pd.to_datetime(df["date"]).dt.date
        insert_into_bigquery(df, project_id, "stocks", asset)
        move_csv_file_gcp(source_bucket, archive_bucket, file.name)


def load_files(configuration, asset):
    """Return GCS source objects for an asset; local staging is unsupported."""
    from google.cloud import storage

    credentials, project_id = cloud_project(configuration)
    bucket = (
        configuration.data_bucket
        if configuration is not None
        else f"data-{get_project_number(project_id)}"
    )
    return storage.Client(credentials=credentials, project=project_id).bucket(
        bucket
    ).list_blobs(prefix=asset)
