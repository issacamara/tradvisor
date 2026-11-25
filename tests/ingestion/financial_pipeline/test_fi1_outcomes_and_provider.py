"""FI-1 entrypoint, stdout outcome and provider-request tests."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from types import ModuleType, SimpleNamespace
import pytest
from functions.financials import fi1_job
from functions.financials.fi1_job import EXTRACTION_KEYS
from functions.financials.fi1_job import MODEL_ORDER, SELECTOR_URL, ProviderHTTPError, main, run_batch

from fi1_support import (
    runtime_environment,
    Harness,
    run,
    disable_source_pacing_in_offline_tests,
)  # noqa: F401 (imported fixtures)


def test_invalid_run_batch_mode_fails_before_adapter_access() -> None:
    fake = Harness()
    adapters = fake.adapters()

    with pytest.raises(ValueError, match="selection mode"):
        run_batch(adapters, api_key="runtime-secret", selection_mode="")

    assert fake.fetches == []
    assert fake.downloads == []
    assert fake.state_reads == 0


@pytest.mark.parametrize("selection_mode", ["", "unknown"])
def test_main_rejects_invalid_mode_before_constructing_backing_adapters(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)
    adapter_calls: list[bool] = []
    monkeypatch.setattr(
        fi1_job,
        "_default_adapters",
        lambda *args: adapter_calls.append(True),
    )

    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert output.startswith("FI-1 configuration failed: ")
    assert "TRADVISOR_FINANCIALS_SELECTION_MODE" in output
    assert adapter_calls == []


def test_main_suppresses_raw_runtime_exception_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENROUTER_API_KEY", "runtime-test-secret")
    monkeypatch.setattr(fi1_job, "_default_adapters", lambda *args: object())

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Bearer private-provider-body")

    monkeypatch.setattr(fi1_job, "run_batch", fail)
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 1
    assert capsys.readouterr().out == ""


def test_full_batch_uses_only_injected_offline_adapters() -> None:
    fake = Harness()

    outcome = run(fake)

    assert outcome.inserted == 1
    assert outcome.failed == 0
    assert fake.fetches.count(SELECTOR_URL) == 1
    assert fake.state_reads == 1
    assert fake.downloads == ["https://www.richbourse.com/ABC-2024.pdf"]
    assert fake.writes[0][0][0]["symbol"] == "ABC"
    collected_at = fake.writes[0][0][0]["collected_at"]
    assert isinstance(collected_at, datetime)
    assert collected_at.tzinfo is timezone.utc
    assert tuple(key for key in fake.writes[0][0][0] if key in EXTRACTION_KEYS) == EXTRACTION_KEYS
    assert fake.actions == ["state_read", "staging_load", "merge_commit", "completion"]
    assert outcome.completion is not None


def test_each_processed_symbol_prints_one_terminal_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()

    run(fake)

    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 batch committed: inserted=1 updated=0",
    ]


def test_unchanged_candidate_prints_success_without_pdf_or_provider(
    capsys: pytest.CaptureFixture[str],
) -> None:
    link = "https://www.richbourse.com/ABC-2024.pdf"
    fake = Harness(existing={("ABC", 2024): link})

    run(fake)

    assert capsys.readouterr().out.splitlines() == ["FI-1 symbol ABC: succeeded"]
    assert fake.downloads == []
    assert fake.attempts == []


def test_multiple_candidates_print_one_terminal_symbol_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness(years=(2025, 2024))

    run(fake)

    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 batch committed: inserted=2 updated=0",
    ]


def test_provider_http_status_is_sanitized_in_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*_args: object) -> object:
        raise ProviderHTTPError(503)

    fake = Harness(extract=fail)
    outcome = run(fake, model_order=(MODEL_ORDER[0],))
    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: failed (ProviderHTTP503)"
    ]
    assert outcome.failed == 1
    assert fake.completions == []


def test_provider_http_error_rejects_invalid_status_codes() -> None:
    with pytest.raises(ValueError, match="provider HTTP status is invalid"):
        ProviderHTTPError(600)


def test_provider_http_response_body_is_not_carried_into_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "PRIVATE_PROVIDER_RESPONSE_BODY"

    class Response:
        status_code = 503
        text = sentinel

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(post=lambda *_args, **_kwargs: Response())  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", curl_cffi)

    with pytest.raises(ProviderHTTPError) as caught:
        fi1_job._provider_attempt("private text", MODEL_ORDER[0], "secret", 1)

    assert caught.value.status_code == 503
    assert str(caught.value) == "ProviderHTTP503"
    assert sentinel not in repr(caught.value)


def test_provider_sends_owner_prompt_and_document_separately_for_every_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"fiscal_year": 2024}'}}]}

    def post(*_args: object, **kwargs: object) -> Response:
        captured.append(kwargs)
        return Response()

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(post=post)  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", curl_cffi)

    for model in MODEL_ORDER:
        fi1_job._provider_attempt("synthetic document text", model, "secret", 1)

    assert [request["json"]["model"] for request in captured] == list(MODEL_ORDER)  # type: ignore[index]
    for request in captured:
        messages = request["json"]["messages"]  # type: ignore[index]
        assert messages == [
            {"role": "system", "content": fi1_job.OWNER_EXTRACTION_PROMPT},
            {"role": "user", "content": "synthetic document text"},
        ]
        assert sha256(messages[0]["content"].encode()).hexdigest() == (
            "dd961426d36af4c219e8aae0fca92264cc0869e777f21b17767b2879ed51185c"
        )
