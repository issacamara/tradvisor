from __future__ import annotations

from datetime import datetime, timezone

from backend.contracts.publication_control import ManagedImportCompletion, ManagedWriteReceipt
from backend.publication.runtime import GcsPublicationControlStore
from backend.publication.control import PublicationControlState
from backend.contracts.publication_control import ReadySourceInput, SourceInputIdentity


class Blob:
    def __init__(self) -> None:
        self.generation = None
        self.payload = None

    def exists(self) -> bool:
        return self.payload is not None

    def reload(self) -> None:
        return None

    def download_as_text(self) -> str:
        return self.payload

    def upload_from_string(self, payload: str, **kwargs: object) -> None:
        expected = kwargs["if_generation_match"]
        actual = 0 if self.generation is None else self.generation
        assert expected == actual
        self.payload = payload
        self.generation = 1 if self.generation is None else self.generation + 1


class Bucket:
    def __init__(self) -> None:
        self.blob_instance = Blob()

    def blob(self, _: str) -> Blob:
        return self.blob_instance


def test_control_state_store_persists_sanitized_controller_state() -> None:
    store = GcsPublicationControlStore(Bucket())
    completion = ManagedImportCompletion(
        source="shares",
        status="succeeded",
        managed_write=ManagedWriteReceipt(
            revision_fingerprint="a" * 64,
            completed_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        ),
    )

    result = store.transact(lambda state: state.to_record())
    assert result == PublicationControlState().to_record()
    store.transact(lambda state: setattr(state, "last_outcome", None))
    assert "a" * 64 not in store._blob.download_as_text()
    assert completion.source == "shares"


def test_control_state_round_trip_accepts_json_arrays_for_identity_inputs() -> None:
    identity = SourceInputIdentity.from_inputs((ReadySourceInput(source="shares", revision_fingerprint="a" * 64),))
    state = PublicationControlState(
        coalescing_started_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        ready_inputs=(ReadySourceInput(source="shares", revision_fingerprint="a" * 64),),
        last_requested_identity=identity,
        active_identity=identity,
        analytical_attempts=1,
    )

    restored = PublicationControlState.from_record(state.to_record())

    assert restored.active_identity == identity
