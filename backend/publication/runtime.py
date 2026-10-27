"""Production adapters for the completion-driven publication controller."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Callable
from urllib.parse import urljoin

from backend.configuration import PublicationControlRuntimeConfiguration
from backend.contracts.publication_control import ManagedImportCompletion, SourceInputIdentity
from backend.publication.control import PublicationControlState, PublicationRequestController


class GcsPublicationControlStore:
    """Small generation-checked store for the single control-plane document."""

    def __init__(self, bucket: Any, *, blob_name: str = "state.json") -> None:
        self._blob = bucket.blob(blob_name)

    def transact(self, transition: Callable[[PublicationControlState], Any]) -> Any:
        from google.api_core.exceptions import PreconditionFailed

        for _ in range(5):
            if self._blob.exists():
                self._blob.reload()
                generation = self._blob.generation
                state = PublicationControlState.from_record(json.loads(self._blob.download_as_text()))
            else:
                generation = None
                state = PublicationControlState()
            candidate = deepcopy(state)
            result = transition(candidate)
            try:
                self._blob.upload_from_string(
                    json.dumps(candidate.to_record(), separators=(",", ":"), sort_keys=True),
                    content_type="application/json",
                    if_generation_match=0 if generation is None else generation,
                )
            except PreconditionFailed:
                continue
            return result
        raise RuntimeError("publication-control state transaction retries exhausted")


class CloudTasksPublicationScheduler:
    def __init__(self, configuration: PublicationControlRuntimeConfiguration) -> None:
        self._configuration = configuration

    def schedule(self, completion: ManagedImportCompletion) -> None:
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
        queue = (
            f"projects/{self._configuration.project_id}/locations/"
            f"{self._configuration.region}/queues/{self._configuration.queue_name}"
        )
        payload = json.dumps({"completion": completion.model_dump(mode="json")}).encode()
        request = {
            "task": {
                "httpRequest": {
                    "httpMethod": "POST",
                    "url": urljoin(self._configuration.service_url, "/internal/publication-control/dispatch"),
                    "headers": {"Content-Type": "application/json"},
                    "body": base64.b64encode(b"{}").decode(),
                    "oidcToken": {"serviceAccountEmail": self._configuration.service_account},
                },
                "scheduleTime": (datetime.now(timezone.utc) + timedelta(seconds=self._configuration.control_configuration.debounce_seconds)).isoformat().replace("+00:00", "Z"),
            }
        }
        # The completion is durable in GCS; the task only wakes the controller.
        response = session.post(
            f"https://cloudtasks.googleapis.com/v2/{queue}/tasks",
            json=request,  # type: ignore[arg-type]
            timeout=30,
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError("publication-control task could not be scheduled")


class CloudRunJobInvoker:
    """Invoke and wait for the existing analytical Cloud Run Job."""

    def __init__(self, configuration: PublicationControlRuntimeConfiguration) -> None:
        self._configuration = configuration

    def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
        del input_identity
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
        url = (
            f"https://run.googleapis.com/v2/projects/{self._configuration.project_id}"
            f"/locations/{self._configuration.region}/jobs/{self._configuration.job_name}:run"
        )
        response = session.post(url, json={}, timeout=30)
        if response.status_code not in {200, 201}:
            raise RuntimeError("analytical job invocation failed")
        operation = response.json().get("name")
        if not isinstance(operation, str) or not operation:
            raise RuntimeError("analytical job invocation returned no operation")
        for _ in range(180):
            status = session.get(f"https://run.googleapis.com/v2/{operation}", timeout=30)
            if status.status_code != 200:
                raise RuntimeError("analytical job operation could not be read")
            body = status.json()
            if body.get("done"):
                if body.get("error"):
                    raise RuntimeError("analytical job failed")
                return
            import time
            time.sleep(5)
        raise RuntimeError("analytical job operation exceeded its bounded wait")


def build_controller() -> PublicationRequestController:
    configuration = PublicationControlRuntimeConfiguration.from_environment()
    from google.cloud import storage  # type: ignore[import-untyped]

    bucket = storage.Client(project=configuration.project_id).bucket(configuration.state_bucket)
    return PublicationRequestController(
        GcsPublicationControlStore(bucket),
        CloudRunJobInvoker(configuration),
        configuration.control_configuration,
        _PublicationEvents(),
    )


class _PublicationEvents:
    def completion(self, *, source: str, outcome: str, now: datetime) -> None:
        from backend.observability import SanitizedLogger, configure_json_stdout
        import logging
        SanitizedLogger(configure_json_stdout(logging.getLogger("publication"))).event(
            "publication.completion", outcome, attributes={"source": source}, now=now
        )

    def control(self, *, outcome: str, sources: str, attempts: int = 0, now: datetime, duration_ms: int | None = None) -> None:
        from backend.observability import SanitizedLogger, configure_json_stdout
        import logging
        SanitizedLogger(configure_json_stdout(logging.getLogger("publication"))).event(
            "publication.control", outcome, duration_ms=duration_ms,
            attributes={"control_outcome": outcome, "sources": sources, "attempt": attempts}, now=now
        )


def completion_identity(completion: ManagedImportCompletion) -> str:
    return hashlib.sha256(completion.model_dump_json().encode()).hexdigest()
