"""Validated, explicit configuration for V1 backend runtime targets.

Configuration is read from process environment only. Secret values are supplied
by the runtime's secret manager integration and are never included in errors or
the representation of this object.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
import re
from typing import Literal
from urllib.parse import urlsplit


RuntimeTarget = Literal["api", "daily_job", "admin"]
Environment = Literal["development", "production"]
MAX_PUBLICATION_DEBOUNCE_SECONDS = 300

_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_DATASET_ID = re.compile(r"^[A-Za-z0-9_]+$")
_TABLE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_FIRESTORE_DATABASE = re.compile(r"^(?:\(default\)|[a-z][a-z0-9-]{3,62})$")


class RuntimeConfigurationError(ValueError):
    """A safe-to-report configuration error that never includes values."""


@dataclass(frozen=True, slots=True)
class PublicationControlConfiguration:
    """Release configuration for the serialized publication-control process."""

    debounce_seconds: int

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "PublicationControlConfiguration":
        values = os.environ if environ is None else environ
        raw_value = values.get("TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS", "").strip()
        if not raw_value:
            raise RuntimeConfigurationError("TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS is required")
        if not raw_value.isdecimal():
            raise RuntimeConfigurationError("TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS must be a whole number")
        debounce_seconds = int(raw_value)
        if not 1 <= debounce_seconds <= MAX_PUBLICATION_DEBOUNCE_SECONDS:
            raise RuntimeConfigurationError(
                "TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS must be positive and bounded"
            )
        return cls(debounce_seconds=debounce_seconds)


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    """Explicit service targets shared by API, batch, and admin entry points."""

    target: RuntimeTarget
    environment: Environment
    project_id: str
    target_project_id: str
    environment_project_id: str
    firestore_database: str
    serving_target: Literal["firestore"]
    cursor_secret: str = field(repr=False)
    cors_origins: tuple[str, ...] = ()
    market_data_table: str | None = None
    financials_table: str | None = None
    recovery_bucket: str | None = None

    @classmethod
    def from_environment(
        cls,
        target: RuntimeTarget,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeConfiguration:
        """Read and validate one runtime target before constructing clients."""
        values = os.environ if environ is None else environ

        required = [
            "TRADVISOR_RUNTIME_TARGET",
            "TRADVISOR_ENVIRONMENT",
            "GOOGLE_CLOUD_PROJECT",
            "TRADVISOR_TARGET_PROJECT_ID",
            "TRADVISOR_ENVIRONMENT_PROJECT_ID",
            "GOOGLE_CLOUD_FIRESTORE_DATABASE",
            "TRADVISOR_SERVING_TARGET",
            "FIRESTORE_CURSOR_SECRET",
        ]
        if target == "api":
            required += [
                "TRADVISOR_CORS_ORIGINS",
                "MARKET_DATA_TABLE",
                "TRADVISOR_RECOVERY_BUCKET",
            ]
        elif target == "daily_job":
            required += ["MARKET_DATA_TABLE", "FINANCIALS_TABLE"]
        elif target == "admin":
            required += ["TRADVISOR_RECOVERY_BUCKET"]
        else:
            raise RuntimeConfigurationError("runtime target is unsupported")

        missing = [
            name for name in required
            if name not in values
            or (name != "TRADVISOR_CORS_ORIGINS" and not values[name].strip())
        ]
        if missing:
            raise RuntimeConfigurationError(
                "required runtime configuration is missing: " + ", ".join(missing)
            )

        if values["TRADVISOR_RUNTIME_TARGET"].strip() != target:
            raise RuntimeConfigurationError(
                "TRADVISOR_RUNTIME_TARGET does not match the requested runtime target"
            )

        environment = values["TRADVISOR_ENVIRONMENT"].strip()
        if environment not in {"development", "production"}:
            raise RuntimeConfigurationError(
                "TRADVISOR_ENVIRONMENT must be development or production"
            )

        project_id = values["GOOGLE_CLOUD_PROJECT"].strip()
        target_project_id = values["TRADVISOR_TARGET_PROJECT_ID"].strip()
        environment_project_id = values["TRADVISOR_ENVIRONMENT_PROJECT_ID"].strip()
        if not _PROJECT_ID.fullmatch(project_id):
            raise RuntimeConfigurationError("GOOGLE_CLOUD_PROJECT is invalid")
        if not _PROJECT_ID.fullmatch(target_project_id):
            raise RuntimeConfigurationError("TRADVISOR_TARGET_PROJECT_ID is invalid")
        if not _PROJECT_ID.fullmatch(environment_project_id):
            raise RuntimeConfigurationError("TRADVISOR_ENVIRONMENT_PROJECT_ID is invalid")
        if project_id != target_project_id or project_id != environment_project_id:
            raise RuntimeConfigurationError(
                "configured project does not match the explicit environment target"
            )

        firestore_database = values["GOOGLE_CLOUD_FIRESTORE_DATABASE"].strip()
        if not _FIRESTORE_DATABASE.fullmatch(firestore_database):
            raise RuntimeConfigurationError(
                "GOOGLE_CLOUD_FIRESTORE_DATABASE is invalid"
            )

        serving_target = values["TRADVISOR_SERVING_TARGET"].strip().lower()
        if serving_target != "firestore":
            raise RuntimeConfigurationError(
                "TRADVISOR_SERVING_TARGET must be firestore"
            )

        market_data_table = _table_id(
            "MARKET_DATA_TABLE", values.get("MARKET_DATA_TABLE"), project_id
        ) if "MARKET_DATA_TABLE" in required else None
        financials_table = _table_id(
            "FINANCIALS_TABLE", values.get("FINANCIALS_TABLE"), project_id
        ) if "FINANCIALS_TABLE" in required else None

        cors_origins: tuple[str, ...] = ()
        if target == "api":
            cors_origins = _cors_origins(
                values["TRADVISOR_CORS_ORIGINS"], environment=environment
            )

        recovery_bucket: str | None = None
        if "TRADVISOR_RECOVERY_BUCKET" in required:
            recovery_bucket = values["TRADVISOR_RECOVERY_BUCKET"].strip()
            if not _BUCKET.fullmatch(recovery_bucket):
                raise RuntimeConfigurationError(
                    "TRADVISOR_RECOVERY_BUCKET is invalid"
                )

        return cls(
            target=target,
            environment=environment,  # type: ignore[arg-type]
            project_id=project_id,
            target_project_id=target_project_id,
            environment_project_id=environment_project_id,
            firestore_database=firestore_database,
            serving_target="firestore",
            cursor_secret=values["FIRESTORE_CURSOR_SECRET"],
            cors_origins=cors_origins,
            market_data_table=market_data_table,
            financials_table=financials_table,
            recovery_bucket=recovery_bucket,
        )


def _table_id(name: str, raw_value: str | None, project_id: str) -> str:
    value = (raw_value or "").strip()
    parts = value.split(".")
    if (
        len(parts) != 3
        or parts[0] != project_id
        or not _DATASET_ID.fullmatch(parts[1])
        or not _TABLE_ID.fullmatch(parts[2])
    ):
        raise RuntimeConfigurationError(
            f"{name} must be a fully qualified table in the configured project"
        )
    return value


def _cors_origins(raw_value: str, *, environment: str) -> tuple[str, ...]:
    origins = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    if "*" in origins:
        raise RuntimeConfigurationError("TRADVISOR_CORS_ORIGINS cannot contain wildcard origins")
    for origin in origins:
        parsed = urlsplit(origin)
        allowed_scheme = parsed.scheme == "https" or (
            environment == "development"
            and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1"}
        )
        if (
            not allowed_scheme
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "?" in origin
            or "#" in origin
        ):
            raise RuntimeConfigurationError(
                "TRADVISOR_CORS_ORIGINS must contain valid HTTPS origins"
            )
    return origins


__all__ = [
    "RuntimeConfiguration",
    "RuntimeConfigurationError",
    "RuntimeTarget",
    "PublicationControlConfiguration",
]
