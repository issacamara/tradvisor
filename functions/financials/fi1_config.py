"""Validated runtime settings and limits for the FI-1 job."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping


MAX_RUNTIME_SECONDS = 60 * 60
MAX_PAGE_CONCURRENCY = 4
MAX_ANNUAL_CANDIDATES = 5
SOURCE_PACING_SECONDS = 1
RUNTIME_TARGET = "financial_ingestion_job"


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Validated non-secret settings supplied by the Terraform-managed job."""

    project_id: str
    environment: str
    dataset: str
    financials_table: str
    staging_table: str
    model_order: tuple[str, ...]
    max_concurrent_requests: int
    max_reports_per_symbol: int
    selection_mode: str

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "RuntimeConfiguration":
        values = os.environ if environ is None else environ
        selection_mode = values.get("TRADVISOR_FINANCIALS_SELECTION_MODE", "historical")
        if not isinstance(selection_mode, str) or selection_mode not in {
            "historical", "previous_year", "publication_year"
        }:
            raise ValueError(
                "TRADVISOR_FINANCIALS_SELECTION_MODE must be historical, previous_year, or publication_year"
            )
        if values.get("TRADVISOR_RUNTIME_TARGET") != RUNTIME_TARGET:
            raise ValueError("TRADVISOR_RUNTIME_TARGET must select the FI-1 job")
        environment = values.get("TRADVISOR_ENVIRONMENT", "")
        if environment not in {"development", "production"}:
            raise ValueError("TRADVISOR_ENVIRONMENT must be development or production")
        project_id = values.get("TRADVISOR_TARGET_PROJECT_ID", "")
        if not project_id or values.get("TRADVISOR_ENVIRONMENT_PROJECT_ID") != project_id:
            raise ValueError("FI-1 target and environment projects must match")
        if values.get("GOOGLE_CLOUD_PROJECT") != project_id:
            raise ValueError("Google Cloud project must match the FI-1 target project")
        dataset = values.get("TRADVISOR_INGESTION_DATASET", "")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset) is None:
            raise ValueError("invalid financial dataset configuration")

        prefix = f"{project_id}.{dataset}."
        if values.get("TRADVISOR_INGESTION_COMPANIES_TABLE") != prefix + "brvm_companies":
            raise ValueError("FI-1 company table does not match its managed dataset")
        financials_table = values.get("TRADVISOR_INGESTION_FINANCIALS_TABLE", "")
        staging_table = values.get("TRADVISOR_INGESTION_FINANCIALS_STAGING_TABLE", "")
        if financials_table != prefix + "financials":
            raise ValueError("FI-1 financial table does not match its managed dataset")
        if staging_table != prefix + "financials_staging":
            raise ValueError("FI-1 staging table does not match its managed dataset")

        primary = values.get("TRADVISOR_FINANCIALS_MODEL_PRIMARY", "")
        fallbacks = tuple(
            item.strip()
            for item in values.get("TRADVISOR_FINANCIALS_MODEL_FALLBACKS", "").split(",")
            if item.strip()
        )
        model_order = (primary, *fallbacks)
        if not primary or len(set(model_order)) != len(model_order):
            raise ValueError("FI-1 model configuration must contain unique ordered models")

        def bounded_integer(name: str, *, minimum: int, maximum: int) -> int:
            value = values.get(name, "")
            if not value.isdecimal():
                raise ValueError(f"{name} must be an integer")
            parsed = int(value)
            if not minimum <= parsed <= maximum:
                raise ValueError(f"{name} is outside its approved bounds")
            return parsed

        bounded_integer("TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL", minimum=1, maximum=1)
        return cls(
            project_id=project_id,
            environment=environment,
            dataset=dataset,
            financials_table=financials_table,
            staging_table=staging_table,
            model_order=model_order,
            max_concurrent_requests=bounded_integer(
                "TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS",
                minimum=1,
                maximum=MAX_PAGE_CONCURRENCY,
            ),
            max_reports_per_symbol=bounded_integer(
                "TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL",
                minimum=1,
                maximum=MAX_ANNUAL_CANDIDATES,
            ),
            selection_mode=selection_mode,
        )

    def public_summary(self) -> dict[str, Any]:
        """Return non-secret settings for container configuration smoke checks."""
        return {
            "runtime_target": RUNTIME_TARGET,
            "environment": self.environment,
            "project_id": self.project_id,
            "dataset": self.dataset,
            "financials_table": self.financials_table,
            "staging_table": self.staging_table,
            "model_order": list(self.model_order),
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_reports_per_symbol": self.max_reports_per_symbol,
            "selection_mode": self.selection_mode,
        }
