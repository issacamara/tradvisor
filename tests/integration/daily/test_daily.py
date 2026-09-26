from dataclasses import dataclass

from backend.jobs.daily import run_daily


@dataclass(frozen=True)
class Batch:
    batch_id: str


class Factory:
    def build(self, *, run_id: str) -> Batch | None:
        return None if run_id == "unchanged" else Batch(run_id)


class Publisher:
    def publish(self, batch: Batch) -> str:
        return f"published:{batch.batch_id}"


def test_daily_run_skips_unchanged_inputs_and_publishes_once() -> None:
    assert run_daily(run_id="unchanged", factory=Factory(), publisher=Publisher()).status == "unchanged"
    result = run_daily(run_id="run-1", factory=Factory(), publisher=Publisher())
    assert result.status == "published"
    assert result.batch_id == "run-1"
