"""FI-1 writer call shape and overlapping-run tests."""

from __future__ import annotations

from pathlib import Path
import threading
import importlib.util
import inspect
from types import ModuleType
from typing import Any
import pytest
from functions.financials.fi1_job import RuntimeAdapters, _default_adapters, run_batch

from fi1_support import (
    VALID,
    Harness,
    run,
    disable_source_pacing_in_offline_tests,  # noqa: F401
)


def test_default_writer_uses_legacy_managed_helper_call_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Frame:
        def __init__(self, rows: list[dict[str, Any]], *, columns: list[str]) -> None:
            self.rows = rows
            self.columns = columns

    pandas = ModuleType("pandas")
    pandas.DataFrame = Frame  # type: ignore[attr-defined]
    helper = ModuleType("helper")

    def managed_writer(
        frame: object,
        revision_frame: object,
        project_id: str,
        dataset: str,
        archive: object,
        *,
        run_id: str | None = None,
    ) -> str:
        calls.append(
            ((frame, revision_frame, project_id, dataset, archive), {"run_id": run_id})
        )
        return "b" * 64

    helper.upsert_financials_and_archive = managed_writer  # type: ignore[attr-defined]
    observability = ModuleType("ingestion_observability")
    observability.emit_event = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    observability.managed_import_completion = lambda *args, **kwargs: {}  # type: ignore[attr-defined]
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.Client = lambda **kwargs: object()  # type: ignore[attr-defined]
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setitem(sys.modules, "ingestion_observability", observability)
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)

    adapters = _default_adapters("dev-project", "stocks", "development")
    rows = [{"symbol": "ABC", "fiscal_year": 2024}]
    assert adapters.write_rows(rows, "fi1-run") == "b" * 64

    args, kwargs = calls[0]
    assert len(args) == 5
    assert isinstance(args[0], Frame)
    assert args[1] is None
    assert args[2:4] == ("dev-project", "stocks")
    assert callable(args[4])
    assert kwargs == {"run_id": "fi1-run"}

    writer_path = Path(__file__).parents[3] / "functions/ingestion/helper.py"
    spec = importlib.util.spec_from_file_location("fi1_managed_helper_contract", writer_path)
    assert spec is not None and spec.loader is not None
    helper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper_module)
    inspect.signature(helper_module.upsert_financials_and_archive).bind(*args, **kwargs)


@pytest.mark.parametrize(
    ("first_mode", "second_mode"),
    [("historical", "previous_year"), ("previous_year", "historical")],
)
def test_overlapping_fi1_modes_can_insert_duplicate_logical_keys(
    first_mode: str, second_mode: str
) -> None:
    # Both invocations snapshot absence before either write. The fake storage
    # appends rows, showing that a logical key is not a global uniqueness rule.
    fake = Harness(years=(2025,))
    read_barrier = threading.Barrier(2)
    stored_rows: list[dict[str, Any]] = []
    adapters = []
    for _mode in (first_mode, second_mode):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing
        write_rows = run_adapters.write_rows

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def append_rows(rows: list[dict[str, Any]], run_id: str, write=write_rows):
            receipt = write(rows, run_id)
            stored_rows.extend(dict(row) for row in rows)
            return receipt

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": append_rows,
                }
            )
        )

    results: list[object] = []
    threads = [
        threading.Thread(
            target=lambda a=a, m=m: results.append(
                run_batch(a, api_key="runtime-secret", selection_mode=m)
            )
        )
        for a, m in zip(adapters, (first_mode, second_mode))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert len(results) == 2
    assert len(fake.writes) == 2
    assert len({run_id for _, run_id in fake.writes}) == 2
    assert [(row["symbol"], row["fiscal_year"]) for row in stored_rows] == [
        ("ABC", 2025),
        ("ABC", 2025),
    ]
    assert len(fake.completion_batches) == 2


def test_overlapping_changed_links_can_overwrite_each_other() -> None:
    old_link = "https://www.richbourse.com/ABC-old-2025.pdf"
    fake = Harness(
        years=(2025,), existing={("ABC", 2025): old_link}
    )
    read_barrier = threading.Barrier(2)
    commits: list[dict[str, Any]] = []
    final_state: dict[tuple[str, int], dict[str, Any]] = {}
    adapters = []
    for revenue in (11, 22):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def last_write_wins(rows: list[dict[str, Any]], run_id: str):
            fake.writes.append((rows, run_id))
            for row in rows:
                committed = dict(row)
                commits.append(committed)
                final_state[(row["symbol"], row["fiscal_year"])] = committed
            return "a" * 64

        def extract(pdf: bytes, model: str, key: str, timeout: float, value=revenue):
            del model, key, timeout
            return {**VALID, "fiscal_year": int(pdf[-4:]), "revenue": value}

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": last_write_wins,
                    "provider_attempt": extract,
                }
            )
        )

    threads = [
        threading.Thread(
            target=lambda a=a: run_batch(
                a, api_key="runtime-secret", selection_mode="previous_year"
            )
        )
        for a in adapters
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert len(commits) == 2
    assert {row["revenue"] for row in commits} == {11, 22}
    # A same-key replacement can be overwritten by either run; no winner is
    # inferred from the run-scoped receipts.
    assert final_state[("ABC", 2025)]["revenue"] in {11, 22}
    assert len(fake.completion_batches) == 2


def test_overlapping_writer_failure_has_run_scoped_completion() -> None:
    fake = Harness(years=(2025,))
    read_barrier = threading.Barrier(2)
    adapters = []
    for should_fail in (True, False):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def write(rows: list[dict[str, Any]], run_id: str, fail=should_fail):
            if fail:
                raise RuntimeError("simulated run-local write failure")
            fake.writes.append((rows, run_id))
            return "a" * 64

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": write,
                }
            )
        )

    outcomes: list[object] = []

    def execute(run_adapters: RuntimeAdapters) -> None:
        try:
            outcomes.append(run_batch(run_adapters, api_key="runtime-secret"))
        except RuntimeError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=execute, args=(a,)) for a in adapters]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert sum(isinstance(outcome, RuntimeError) for outcome in outcomes) == 1
    assert sum(getattr(outcome, "completion", None) is not None for outcome in outcomes) == 1
    assert len(fake.completion_batches) == 1
    assert len(fake.writes) == 1


def test_new_retry_reads_committed_link_and_skips_completed_row() -> None:
    fake = Harness(years=(2025,))
    adapters = fake.adapters()
    write_rows = adapters.write_rows

    def commit_and_update_state(rows: list[dict[str, Any]], run_id: str) -> str:
        receipt = write_rows(rows, run_id)
        for row in rows:
            fake.existing[(row["symbol"], row["fiscal_year"])] = row["document_link"]
        return receipt

    adapters = RuntimeAdapters(**{**adapters.__dict__, "write_rows": commit_and_update_state})
    first = run_batch(adapters, api_key="runtime-secret")
    attempts_after_commit = len(fake.attempts)
    writes_after_commit = len(fake.writes)

    retry = run(fake)

    assert first.completion is not None
    assert retry.completion is None
    assert len(fake.attempts) == attempts_after_commit
    assert len(fake.writes) == writes_after_commit
    assert fake.state_reads == 2
