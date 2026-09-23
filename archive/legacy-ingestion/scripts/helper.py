"""Shared legacy-ingestion helpers and immutable acquisition evidence.

The module intentionally has no client construction or filesystem activity at
import time.  Entry points that need cloud or parsing libraries import them at
call time so a scheduler, test runner, or parser manifest inspection is safe.
"""

from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import re
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class AcquisitionNotCommittable(ValueError):
    """Raised when acquisition evidence cannot truthfully be committed."""


@dataclass(frozen=True)
class ParserManifest:
    """Versioned, content-addressed description of the parser that ran."""

    parser_name: str
    parser_version: str
    configuration: dict[str, Any]
    configuration_sha256: str


@dataclass(frozen=True)
class SourceSnapshot:
    """Immutable evidence created only after a complete successful acquisition."""

    source: str
    run_id: str
    acquired_at: str
    http_status: int
    payload_sha256: str
    payload_bytes: int
    parser_manifest: ParserManifest
    directory: str


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _safe_identifier(value: str, field: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"{field} must use only letters, digits, '.', '_' or '-'")
    return value


def build_parser_manifest(
    parser_name: str,
    parser_version: str,
    configuration: Mapping[str, Any] | None = None,
) -> ParserManifest:
    """Return a deterministic parser manifest without invoking a parser."""

    _safe_identifier(parser_name, "parser_name")
    _safe_identifier(parser_version, "parser_version")
    normalized_configuration = dict(configuration or {})
    return ParserManifest(
        parser_name=parser_name,
        parser_version=parser_version,
        configuration=normalized_configuration,
        configuration_sha256=hashlib.sha256(
            _canonical_json(normalized_configuration)
        ).hexdigest(),
    )


def new_acquisition_run_id(now: datetime | None = None) -> str:
    """Create a sortable, collision-resistant run identifier for retry evidence."""

    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return f"{instant.astimezone(timezone.utc):%Y%m%dT%H%M%S%fZ}-{os.urandom(6).hex()}"


def commit_source_snapshot(
    snapshot_root: str | Path,
    *,
    source: str,
    run_id: str,
    payload: bytes,
    parser_manifest: ParserManifest,
    http_status: int,
    acquisition_complete: bool,
    acquired_at: datetime | None = None,
) -> SourceSnapshot:
    """Persist one immutable snapshot directory for a complete HTTP acquisition.

    ``run_id`` is part of the path, so retries retain evidence even where the
    source, calendar date, and payload are identical.  A completed marker is
    written last and no pre-existing run directory is ever reused.
    """

    source = _safe_identifier(source, "source")
    run_id = _safe_identifier(run_id, "run_id")
    if not 200 <= http_status < 300:
        raise AcquisitionNotCommittable(
            f"HTTP status {http_status} cannot be committed as a successful acquisition"
        )
    if not acquisition_complete:
        raise AcquisitionNotCommittable("incomplete acquisition cannot be committed")

    instant = acquired_at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("acquired_at must be timezone-aware")
    acquired_at_text = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    root = Path(snapshot_root)
    run_directory = root / source / run_id

    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(
            f"snapshot evidence already exists for source={source!r}, run_id={run_id!r}"
        ) from error

    snapshot = SourceSnapshot(
        source=source,
        run_id=run_id,
        acquired_at=acquired_at_text,
        http_status=http_status,
        payload_sha256=payload_sha256,
        payload_bytes=len(payload),
        parser_manifest=parser_manifest,
        directory=str(run_directory),
    )
    try:
        (run_directory / "payload.bin").write_bytes(payload)
        (run_directory / "manifest.json").write_bytes(
            _canonical_json(asdict(snapshot))
        )
        # This marker is deliberately last: callers may only treat its presence
        # as committed success after both evidence files are durable.
        (run_directory / "COMMITTED").write_text("\n", encoding="ascii")
    except Exception:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise

    return snapshot


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

def save_dataframe_as_csv(df, fin_asset, conf):
    """
    Save a Pandas DataFrame as a CSV file either locally or to Google Cloud Storage (GCS).

    Parameters:
    - df (pd.DataFrame): The DataFrame to save.
    - filename (str): The name of the file to save as.
    - gcs_bucket_name (str, optional): The name of the GCS bucket. If provided, the file will be saved to GCS.
      If None, the file will be saved locally.
    """
    from google.auth import default
    from google.cloud import storage

    today = datetime.now().strftime('%Y-%m-%d')
    filename = f'{fin_asset.lower()}-{today}.csv'
    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
        # Save the file to a temporary location
        csv_string = df.to_csv(index=False, sep="|")
        credentials, project_id = default()
        project_number = get_project_number(project_id)
        # Upload the file to GCS
        client = storage.Client()
        bucket_url = f"data-{project_number}"
        bucket = client.bucket(bucket_url)
        blob = bucket.blob(filename)
        blob.upload_from_string(csv_string)

        return f"File saved to GCS bucket '{bucket_url}' as '{filename}'.\n"
    else:
        # Save the file locally
        file = os.path.join(os.path.dirname(__file__), '..','data', filename)
        df.to_csv(file, index=False, sep="|")
        return(f"File saved locally as '{filename}'.\n")

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

def move_csv_files(source_dir, destination_dir, pattern):
    # List all files in the source directory
    files = [f for f in os.path.join(os.path.dirname(__file__), '..', source_dir) if f.startswith(pattern)]
    csv_files = glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '..', source_dir), f"{pattern}*.csv"))

    # Loop through the files and move the CSV files to the destination directory
    for file in csv_files:
        file_name = file.split("/")[-1]
        source_file = os.path.join(os.path.dirname(__file__), '..', source_dir, file_name)
        destination_file = os.path.join(os.path.dirname(__file__), '..', destination_dir, file_name)
        # source_file = os.path.join(f"../{source_dir}", file)
        # destination_file = os.path.join(f"../{destination_dir}", file)
        shutil.move(source_file, destination_file)
        print(f'Moved: {file_name}\n')

def move_csv_file(source_dir, destination_dir, file):

    filename = file.split("/")[-1]
    source_file = os.path.join(os.path.dirname(__file__), '..', source_dir, filename)
    destination_file = os.path.join(os.path.dirname(__file__), '..', destination_dir, filename)
    shutil.move(source_file, destination_file)
    print(f'File {filename} moved to {destination_dir}\n')


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
    snapshot_manifest: SourceSnapshot | Mapping[str, Any] | None = None,
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
    snapshot_manifest: SourceSnapshot | Mapping[str, Any] | None = None,
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

    Rows with the same source keys are updated in place. To preserve multiple
    observations as revisions, the adapter must include the revision or
    observation identity in ``primary_keys``. Callers must serialize commits
    for a target/key set: BigQuery MERGE does not enforce unique keys across
    simultaneous insert-first jobs.
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
    run_id = _safe_identifier(run_id or new_acquisition_run_id(), "run_id")
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
        if update_columns:
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
            print(f"Warning: Failed to delete staging table {staging_table_id}: {e}")


def upsert_and_archive(
    df,
    project_id,
    dataset,
    table,
    primary_keys,
    archive: Callable[[], Any],
    *,
    run_id: str | None = None,
    snapshot_manifest: SourceSnapshot | Mapping[str, Any] | None = None,
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


def upsert_financial_report_revision(df, project_id, dataset="stocks"):
    """Persist a report revision separately from the canonical current result."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    current = client.get_table(f"{project_id}.{dataset}.financials")
    revision_id = f"{project_id}.{dataset}.financial_report_revisions"
    revision_schema = list(current.schema)
    current_names = {field.name for field in revision_schema}
    if "document_revision" not in current_names:
        revision_schema.append(bigquery.SchemaField("document_revision", "STRING"))
    client.create_table(
        bigquery.Table(revision_id, schema=revision_schema), exists_ok=True
    )
    revision_rows = df.copy()
    if "document_revision" not in revision_rows.columns:
        raise ValueError("financial report revision requires document_revision")
    return upsert_into_bigquery(
        revision_rows,
        project_id,
        dataset,
        "financial_report_revisions",
        ["symbol", "fiscal_year", "document_link", "document_revision"],
    )


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

# Define a function to insert data into DuckDB
def insert_into_duckdb(df, db_path, table):
    import duckdb

    with duckdb.connect(os.path.join(os.path.dirname(__file__), '..', db_path)) as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df where FALSE")  # Create table if not exists
        con.execute(f"INSERT INTO {table} SELECT * FROM df")

def process_files(conf, files, asset):
    import pandas as pd
    from google.auth import default

    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):  # GCP cloud function environment
        for f in files:
            content = f.download_as_text()
            df = pd.read_csv(io.StringIO(content), sep='|')
            df['date'] = pd.to_datetime(df['date']).dt.date
            credentials, project_id = default()
            project_number = get_project_number(project_id)
            bucket_url1 = f"data-{project_number}"
            bucket_url2 = f"archive-{project_number}"
            insert_into_bigquery(df, project_id, 'stocks', asset)
            move_csv_file_gcp(bucket_url1, bucket_url2, f.name)

    else:
        for f in files:
            df = pd.read_csv(f, sep='|')
            insert_into_duckdb(df, conf['duckdb']['database'], asset)
            move_csv_file(conf["csv_directory"], conf["archive"], f)

# Define a function to load CSV files based on today's date
def load_files(config, asset):

    if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
        from google.auth import default
        from google.cloud import storage

        credentials, project_id = default()
        project_number = get_project_number(project_id)
        bucket_uri = f"data-{project_number}"
        bucket = storage.Client().bucket(bucket_uri)
        return bucket.list_blobs(prefix=asset)

    else:
        return glob.glob(os.path.join(os.path.join(os.path.dirname(__file__), '', config['csv_directory']), f"{asset}*.csv"))
