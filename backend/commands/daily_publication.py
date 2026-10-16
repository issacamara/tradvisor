"""Executable Cloud Run Job entrypoint for one analytical publication."""

import logging

from backend.observability import SanitizedLogger, configure_json_stdout
from backend.jobs.runtime import run_from_environment


EVENTS = SanitizedLogger(configure_json_stdout(logging.getLogger(__name__)))


if __name__ == "__main__":
    try:
        run_from_environment()
    except Exception as error:
        EVENTS.event("command.daily_publication", "failed", attributes={"error_class": type(error).__name__})
        raise
