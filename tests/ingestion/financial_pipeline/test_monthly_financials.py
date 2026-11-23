"""Offline tests for the monthly financials job (#438)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from functions.financials import monthly_financials as mf

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 11, 23, 6, tzinfo=timezone.utc)
DOC = "/common/actualite/afficher-fichier/"


def selector(*symbols: str) -> str:
    options = "".join(f'<option value="{s}">{s} NAME ({s})</option>' for s in symbols)
    return (
        '<div class="col-xs-9 col-md-5"><select id="symbole" name="symbole">'
        f'<option value=""> -- Choisissez --</option><optgroup label="x">{options}</optgroup>'
        "</select></div>"
    )


def listing(*rows: tuple[str, str, str]) -> str:
    """rows: (dd/mm/yyyy, title, href)."""
    body = "".join(
        '<div class="col-xs-12 ligne_paire">'
        f'<div class="col-xs-4 col-md-3 col-lg-2">{day}</div>'
        f'<div class="col-xs-8 col-md-9 col-lg-10"><a href="{href}">{title}</a></div></div>'
        for day, title, href in rows
    )
    return f'<div class="row">{body}</div>'


def pager(pages: dict[tuple[str, int], str], symbols: tuple[str, ...] = ("ABC",)):
    calls = []

    def fetch(url: str, params: dict) -> str:
        calls.append(params)
        if not params:
            return selector(*symbols)
        return pages.get((params["symbole"], params["page"]), "")

    return fetch, calls


class Response:
    def __init__(self, status: int = 200, content: object = None) -> None:
        self.status_code = status
        self._content = content

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


def result(year: int = 2025, **extra) -> str:
    data = {"fiscal_year": year, "revenue": 10, "net_income": 1, "total_debt": 2,
            "cash_and_cash_equivalents": 3, "total_equity": 4, **extra}
    return "```json\n" + json.dumps(data) + "\n```"


def poster(*responses):
    calls, queue = [], list(responses)

    def post(url, headers, json, timeout):
        calls.append(json["model"])
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return post, calls


# ---------------------------------------------------------------- discovery
def test_symbols_come_from_the_selector_in_order() -> None:
    assert mf.parse_symbols(selector("NTLC", "PALC", "NTLC")) == ["NTLC", "PALC"]


def test_annual_filter_rejects_interim_and_keeps_provisional() -> None:
    assert mf.is_annual("SAPH : Etats financiers - Exercice 2025", f"{DOC}x")
    assert mf.is_annual("VIVO : États financiers provisoires 2025", f"{DOC}x")
    assert not mf.is_annual("ORANGE CI : Rapport d'activités - 1er semestre 2026", f"{DOC}x")
    assert not mf.is_annual("SGBCI : Etats financiers 1er trimestre 2026", f"{DOC}x")


def test_year_hint_ignores_the_publication_date_in_the_slug() -> None:
    url = mf.BASE + DOC + "03-06-2026-vivo-energy-etats-financiers-exercice-2025"
    assert mf.year_hint("VIVO ENERGY : Etats financiers", url) == 2025
    assert mf.year_hint("Etats financiers", mf.BASE + DOC + "03-06-2026-vivo") is None


def test_pages_are_walked_until_a_prior_year_row() -> None:
    fetch, calls = pager({
        ("ABC", 1): listing(("08/10/2026", "ABC : 1er semestre 2026", f"{DOC}a"),
                            ("01/06/2026", "ABC : Etats financiers exercice 2025", f"{DOC}b")),
        ("ABC", 2): listing(("02/04/2026", "ABC : Etats financiers provisoires 2025", f"{DOC}c"),
                            ("20/12/2025", "ABC : Etats financiers exercice 2024", f"{DOC}d")),
        ("ABC", 3): listing(("01/06/2025", "never read", f"{DOC}e")),
    })
    docs = mf.annual_documents(fetch, "ABC", 2026)
    assert [d["document_link"] for d in docs] == [mf.BASE + DOC + "b", mf.BASE + DOC + "c"]
    assert docs[0]["published"] == date(2026, 6, 1)
    assert [c["page"] for c in calls] == [1, 2]


def test_pagination_stops_on_empty_and_repeated_pages() -> None:
    page = listing(("01/06/2026", "ABC : Etats financiers exercice 2025", f"{DOC}b"))
    fetch, calls = pager({("ABC", 1): page, ("ABC", 2): page})
    assert len(mf.annual_documents(fetch, "ABC", 2026)) == 1
    assert [c["page"] for c in calls] == [1, 2]
    fetch, calls = pager({("ABC", 1): page})
    mf.annual_documents(fetch, "ABC", 2026)
    assert [c["page"] for c in calls] == [1, 2]


def test_january_run_excludes_previous_december() -> None:
    fetch, _ = pager({("ABC", 1): listing(
        ("31/12/2026", "ABC : Etats financiers exercice 2025", f"{DOC}b"))})
    assert mf.annual_documents(fetch, "ABC", 2027) == []


def test_foreign_links_are_ignored() -> None:
    rows = mf.parse_rows(listing(("01/06/2026", "Etats financiers 2025", "https://evil.example/x")))
    assert rows == []


# ---------------------------------------------------------------- extraction
def test_gemma_success_never_calls_the_fallback() -> None:
    post, calls = poster(Response(content=result(pnb=99)))
    out = mf.extract(post, "text", "key", mf.MODELS, 2025, 2026)
    assert calls == ["google/gemma-4-31b-it:free"]
    assert out == {"fiscal_year": 2025, "revenue": 10.0, "net_income": 1.0, "total_debt": 2.0,
                   "cash_and_cash_equivalents": 3.0, "total_equity": 4.0}


@pytest.mark.parametrize("first", [
    Response(status=429),
    TimeoutError("slow"),
    Response(content="not json"),
    Response(content=result(revenue="12 345")),
    Response(content=result(year=2024)),
])
def test_any_primary_failure_falls_back_to_gpt(first) -> None:
    post, calls = poster(first, Response(content=result()))
    assert mf.extract(post, "text", "key", mf.MODELS, 2025, 2026)["fiscal_year"] == 2025
    assert calls == list(mf.MODELS)


def test_all_models_failing_returns_none() -> None:
    post, _ = poster(Response(status=500), Response(status=500))
    assert mf.extract(post, "text", "key", mf.MODELS, None, 2026) is None


def test_prompt_is_the_owner_prompt() -> None:
    assert mf.PROMPT.startswith("You are a financial data extraction expert.")
    assert "CRITICAL — UNIT NORMALIZATION" in mf.PROMPT


# ---------------------------------------------------------------- writer
def test_dedupe_keeps_the_newest_publication() -> None:
    rows = [{"symbol": "A", "fiscal_year": 2025, "document_link": "new"},
            {"symbol": "A", "fiscal_year": 2025, "document_link": "old"},
            {"symbol": "A", "fiscal_year": 2024, "document_link": "x"}]
    assert [r["document_link"] for r in mf.dedupe(rows)] == ["new", "x"]


def test_merge_runs_in_a_transaction_on_symbol_and_year() -> None:
    sql = mf.merge_sql("p.stocks.financials", "p.stocks.financials_staging")
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert "ON t.symbol = s.symbol AND t.fiscal_year = s.fiscal_year" in sql
    assert "PARTITION BY symbol, fiscal_year" in sql and "WHERE run_id = @run_id" in sql


class FakeClient:
    def __init__(self, duplicates=()) -> None:
        self.duplicates, self.queries, self.loads = list(duplicates), [], []

    def load_table_from_json(self, rows, table, job_config):
        self.loads.append((table, rows))
        return SimpleNamespace(result=lambda: None)

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        rows = self.duplicates if "HAVING COUNT(*) > 1" in sql else []
        return SimpleNamespace(result=lambda: rows)


@pytest.fixture
def fake_bigquery(monkeypatch):
    stub = ModuleType("google.cloud.bigquery")
    stub.QueryJobConfig = lambda **kw: kw
    stub.ScalarQueryParameter = lambda *a: a
    stub.LoadJobConfig = lambda **kw: kw
    try:
        import google.cloud  # noqa: F401
    except ImportError:
        google, cloud = ModuleType("google"), ModuleType("google.cloud")
        google.cloud = cloud
        monkeypatch.setitem(sys.modules, "google", google)
        monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", stub)
    monkeypatch.setattr(sys.modules["google.cloud"], "bigquery", stub, raising=False)


def test_write_stages_merges_cleans_and_checks(fake_bigquery) -> None:
    client = FakeClient()
    receipt = mf.Store(client, "proj", "stocks").write(
        [{"symbol": "A", "fiscal_year": 2025}, {"symbol": "A", "fiscal_year": 2025}])
    assert len(receipt) == 64
    table, staged = client.loads[0]
    assert table == "proj.stocks.financials_staging" and len(staged) == 1
    assert staged[0]["run_id"].startswith("monthly_")
    assert [q.split()[0] for q in client.queries] == ["BEGIN", "DELETE", "SELECT"]


def test_post_commit_duplicate_fails_the_write(fake_bigquery) -> None:
    with pytest.raises(RuntimeError, match="duplicate"):
        mf.Store(FakeClient(duplicates=[("A", 2025)]), "proj", "stocks").write(
            [{"symbol": "A", "fiscal_year": 2025}])


# ---------------------------------------------------------------- job
class FakeStore:
    def __init__(self, known=None, fail=False):
        self.known, self.fail, self.writes = known or {}, fail, []

    def existing(self):
        return self.known

    def write(self, rows):
        if self.fail:
            raise RuntimeError("financials holds duplicate (symbol, fiscal_year) rows")
        self.writes.append(rows)
        return "a" * 64


@pytest.fixture
def observability(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "archive/legacy-ingestion/scripts"))


PAGES = {("ABC", 1): listing(
    ("01/10/2026", "ABC : Rapport annuel 2025", f"{DOC}new"),
    ("01/06/2026", "ABC : Etats financiers exercice 2025", f"{DOC}final"),
    ("02/04/2026", "ABC : Etats financiers provisoires 2025", f"{DOC}prov"),
    ("01/12/2025", "ABC : Etats financiers exercice 2024", f"{DOC}old"),
)}


def run(store, *responses):
    fetch, _ = pager(PAGES)
    post, calls = poster(*responses)
    stats = mf.run(fetch, lambda url: b"%PDF", post, store, "key", now=NOW, to_text=lambda b: "t")
    return stats, calls


def test_newest_valid_document_wins_and_older_ones_are_skipped(observability, capsys) -> None:
    store = FakeStore()
    stats, calls = run(store, Response(content=result()))
    assert calls == ["google/gemma-4-31b-it:free"]
    assert [(r["fiscal_year"], r["document_link"]) for r in store.writes[0]] == [
        (2025, mf.BASE + DOC + "new")]
    assert stats["skipped"] == 2 and stats["written"] == 1
    assert '"source": "financials"' in capsys.readouterr().out


def test_rerun_skips_known_links_and_never_overwrites_with_older(observability) -> None:
    store = FakeStore(known={mf.BASE + DOC + "final": ("ABC", 2025)})
    stats, calls = run(store, Response(status=500), Response(status=500))
    assert store.writes == [] and stats["failed"] == 1 and stats["skipped"] == 2
    assert calls == list(mf.MODELS)  # only the newer, unknown document was tried


def test_failed_write_suppresses_completion(observability, capsys) -> None:
    with pytest.raises(RuntimeError, match="duplicate"):
        run(FakeStore(fail=True), Response(content=result()))
    assert '"source"' not in capsys.readouterr().out


def test_config_defaults_and_check_config(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TRADVISOR_TARGET_PROJECT_ID", "fixture-project")
    for name in ("TRADVISOR_FINANCIALS_MODEL_PRIMARY", "TRADVISOR_FINANCIALS_MODEL_FALLBACKS"):
        monkeypatch.delenv(name, raising=False)
    mf.main(["--check-config"])
    out = json.loads(capsys.readouterr().out)
    assert out == {"dataset": "stocks", "models": list(mf.MODELS), "project": "fixture-project"}
    monkeypatch.setenv("TRADVISOR_TARGET_PROJECT_ID", "Bad Project")
    with pytest.raises(SystemExit):
        mf.main(["--check-config"])
