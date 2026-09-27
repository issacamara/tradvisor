"""Executable Cloud Run Job entrypoint for one analytical publication."""

from backend.jobs.runtime import run_from_environment


if __name__ == "__main__":
    run_from_environment()
