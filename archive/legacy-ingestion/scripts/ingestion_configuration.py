"""Validated, explicit configuration for packaged ingestion functions.

The module is deliberately dependency-free so it can be included in every
Cloud Function archive.  Entry points validate this contract before importing
or constructing a cloud client; source URLs remain in the checked-in,
secret-free ``config.yml`` asset.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit


_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_DATASET = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SERVICE_ACCOUNT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@")

_TABLE_FIELDS = {
    "shares": "TRADVISOR_INGESTION_SHARES_TABLE",
    "dividends": "TRADVISOR_INGESTION_DIVIDENDS_TABLE",
    "financials": "TRADVISOR_INGESTION_FINANCIALS_TABLE",
    "ratings": "TRADVISOR_INGESTION_RATINGS_TABLE",
}


class IngestionConfigurationError(ValueError):
    """A safe configuration failure that never includes configured values."""


@dataclass(frozen=True, slots=True)
class IngestionConfiguration:
    """Explicit targets used by the retained cloud-only ingestion adapters."""

    environment: str
    project_id: str
    service_account: str
    data_bucket: str
    archive_bucket: str
    dataset: str
    tables: Mapping[str, str]

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "IngestionConfiguration":
        values = os.environ if environ is None else environ
        required = (
            "TRADVISOR_RUNTIME_TARGET",
            "TRADVISOR_ENVIRONMENT",
            "GOOGLE_CLOUD_PROJECT",
            "TRADVISOR_TARGET_PROJECT_ID",
            "TRADVISOR_ENVIRONMENT_PROJECT_ID",
            "TRADVISOR_INGESTION_SERVICE_ACCOUNT",
            "TRADVISOR_INGESTION_DATA_BUCKET",
            "TRADVISOR_INGESTION_ARCHIVE_BUCKET",
            "TRADVISOR_INGESTION_DATASET",
            *_TABLE_FIELDS.values(),
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise IngestionConfigurationError(
                "required ingestion configuration is missing: " + ", ".join(missing)
            )

        if values["TRADVISOR_RUNTIME_TARGET"].strip() != "ingestion":
            raise IngestionConfigurationError(
                "TRADVISOR_RUNTIME_TARGET does not match ingestion"
            )
        environment = values["TRADVISOR_ENVIRONMENT"].strip()
        if environment not in {"development", "production"}:
            raise IngestionConfigurationError(
                "TRADVISOR_ENVIRONMENT must be development or production"
            )

        project_id = values["GOOGLE_CLOUD_PROJECT"].strip()
        target_project = values["TRADVISOR_TARGET_PROJECT_ID"].strip()
        environment_project = values["TRADVISOR_ENVIRONMENT_PROJECT_ID"].strip()
        if not all(_PROJECT_ID.fullmatch(value) for value in (project_id, target_project, environment_project)):
            raise IngestionConfigurationError("configured project identifier is invalid")
        if project_id != target_project or project_id != environment_project:
            raise IngestionConfigurationError(
                "configured project does not match the explicit environment target"
            )

        service_account = values["TRADVISOR_INGESTION_SERVICE_ACCOUNT"].strip()
        if not (
            _SERVICE_ACCOUNT.match(service_account)
            and service_account.endswith(f"@{project_id}.iam.gserviceaccount.com")
        ):
            raise IngestionConfigurationError(
                "TRADVISOR_INGESTION_SERVICE_ACCOUNT is not in the configured project"
            )

        data_bucket = values["TRADVISOR_INGESTION_DATA_BUCKET"].strip()
        archive_bucket = values["TRADVISOR_INGESTION_ARCHIVE_BUCKET"].strip()
        if not _BUCKET.fullmatch(data_bucket) or not _BUCKET.fullmatch(archive_bucket):
            raise IngestionConfigurationError("configured ingestion bucket is invalid")
        if data_bucket == archive_bucket:
            raise IngestionConfigurationError(
                "ingestion data and archive buckets must be distinct"
            )

        dataset = values["TRADVISOR_INGESTION_DATASET"].strip()
        if not _DATASET.fullmatch(dataset):
            raise IngestionConfigurationError("TRADVISOR_INGESTION_DATASET is invalid")
        tables = {
            asset: _table_id(values[field].strip(), project_id, dataset, field)
            for asset, field in _TABLE_FIELDS.items()
        }
        return cls(
            environment=environment,
            project_id=project_id,
            service_account=service_account,
            data_bucket=data_bucket,
            archive_bucket=archive_bucket,
            dataset=dataset,
            tables=tables,
        )

    def table_for(self, asset: str) -> str:
        try:
            return self.tables[asset]
        except KeyError as error:
            raise IngestionConfigurationError("ingestion table target is unsupported") from error

    def validate_application_default_project(self, actual_project: str | None) -> None:
        """Reject ADC project drift before a Storage or BigQuery client is built."""
        if not actual_project:
            raise IngestionConfigurationError(
                "cloud ingestion requires an application-default project"
            )
        if actual_project != self.project_id:
            raise IngestionConfigurationError(
                "application-default project does not match the configured target"
            )


def source_endpoints(config: Mapping[str, object]) -> Mapping[str, str]:
    """Validate the checked-in source endpoint map before any source request."""
    raw_urls = config.get("url")
    if not isinstance(raw_urls, Mapping):
        raise IngestionConfigurationError("source endpoint configuration is missing")
    required = (
        "shares",
        "brvm_session",
        "bonds",
        "capitalizations",
        "volumes",
        "indices",
        "dividends",
        "financials",
        "ratings",
    )
    endpoints: dict[str, str] = {}
    for name in required:
        value = raw_urls.get(name)
        if not isinstance(value, str) or not value.strip():
            raise IngestionConfigurationError(f"source endpoint is missing: {name}")
        endpoint = value.strip()
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise IngestionConfigurationError(f"source endpoint is invalid: {name}")
        endpoints[name] = endpoint
    return endpoints


def _table_id(value: str, project_id: str, dataset: str, field: str) -> str:
    parts = value.split(".")
    if (
        len(parts) != 3
        or parts[0] != project_id
        or parts[1] != dataset
        or not _TABLE.fullmatch(parts[2])
    ):
        raise IngestionConfigurationError(
            f"{field} must target the configured project and dataset"
        )
    return value


__all__ = [
    "IngestionConfiguration",
    "IngestionConfigurationError",
    "source_endpoints",
]
