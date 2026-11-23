"""Monthly RichBourse annual-financials job (#438).

Walks every listed symbol's statement pages for the current publication year,
keeps annual reports, extracts six figures through OpenRouter, and merges them
into the Terraform-managed ``stocks.financials`` table with one row per
``(symbol, fiscal_year)``. The newest publication wins.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from .fi1_job import OWNER_EXTRACTION_PROMPT as PROMPT

BASE = "https://www.richbourse.com"
LIST_URL = BASE + "/common/actualite-categorie/index/etats-financiers"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = ("google/gemma-4-31b-it:free", "openai/gpt-4o-mini")
FIELDS = ("revenue", "net_income", "total_debt", "cash_and_cash_equivalents", "total_equity")
COLUMNS = ("symbol", "fiscal_year", *FIELDS, "collected_at", "document_link")
ANNUAL = re.compile(r"exercice|annuel|etats? financiers?|comptes|provisoire")
INTERIM = re.compile(r"trimestr|semestr")
DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
# RichBourse answers 403 to ?page= requests unless they look like its own AJAX pagination.
LIST_HEADERS = {"Referer": LIST_URL, "X-Requested-With": "XMLHttpRequest"}
MAX_PAGES = 50
BATCH_SYMBOLS = 10


def log(message: str) -> None:
    print(message, flush=True)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[-_/]+", " ", text.lower())


# ---------------------------------------------------------------- discovery
def parse_symbols(html: str) -> list[str]:
    from bs4 import BeautifulSoup

    options = BeautifulSoup(html, "html.parser").select("div.col-xs-9.col-md-5 select option")
    return list(dict.fromkeys(o["value"].strip() for o in options if o.get("value", "").strip()))


def parse_rows(html: str) -> list[tuple[date, str, str]]:
    """Return (publication date, title, absolute RichBourse link) per listing row."""
    from bs4 import BeautifulSoup

    rows = []
    for cell in BeautifulSoup(html, "html.parser").select("div.col-xs-4.col-md-3.col-lg-2"):
        match = DATE.fullmatch(cell.get_text(strip=True))
        sibling = cell.find_next_sibling("div")
        link = sibling.find("a", href=True) if sibling else None
        if not match or link is None:
            continue
        url = urljoin(BASE, link["href"].strip())
        if not url.startswith(BASE + "/"):
            continue
        day, month, year = map(int, match.groups())
        rows.append((date(year, month, day), link.get_text(" ", strip=True), url))
    return rows


def _slug(url: str) -> str:
    """Last path segment without its leading publication date (dd-mm-yyyy-)."""
    return re.sub(r"^\d{1,2}-\d{1,2}-\d{4}-", "", urlparse(url).path.rsplit("/", 1)[-1])


def is_annual(title: str, url: str) -> bool:
    text = _plain(f"{title} {_slug(url)}")
    return bool(ANNUAL.search(text)) and not INTERIM.search(text)


def year_hint(title: str, url: str) -> int | None:
    """Fiscal year named by the document title (or slug), if any."""
    years = YEAR.findall(title) or YEAR.findall(_slug(url))
    return int(years[-1]) if years else None


def annual_documents(fetch: Callable[[str, dict], str], symbol: str, year: int) -> list[dict]:
    """Annual reports published in ``year``, newest first (listing order)."""
    docs, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        rows = parse_rows(fetch(LIST_URL, {"symbole": symbol, "page": page}))
        links = {url for _, _, url in rows}
        if not rows or links <= seen:  # empty page, or the site re-served the last one
            break
        seen |= links
        for published, title, url in rows:
            if published.year < year:
                return docs
            if published.year == year and is_annual(title, url):
                docs.append({"published": published, "title": title, "document_link": url})
    return docs


# ---------------------------------------------------------------- extraction
def parse_json(content: str) -> dict:
    match = re.search(r"\{.*\}", content or "", re.S)
    if match is None:
        raise ValueError("no JSON object in model output")
    return json.loads(match.group(0))


def validate(data: dict, expected_year: int | None, current_year: int) -> dict:
    year = data.get("fiscal_year")
    if isinstance(year, str) and year.strip().isdigit():
        year = int(year)
    if not isinstance(year, int) or isinstance(year, bool) or not 1990 <= year <= current_year:
        raise ValueError("invalid fiscal_year")
    if expected_year is not None and year != expected_year:
        raise ValueError("fiscal_year does not match the document")
    out: dict[str, Any] = {"fiscal_year": year}
    for field in FIELDS:  # extra keys such as pnb are ignored
        value = data.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        ):
            raise ValueError(f"invalid {field}")
        out[field] = None if value is None else float(value)
    return out


def extract(post: Callable[..., Any], text: str, api_key: str, models: Iterable[str],
            expected_year: int | None, current_year: int) -> dict | None:
    """Try each model in order; return the first validated result."""
    for model in models:
        try:
            response = post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": text},
                    ],
                },
                timeout=180,
            )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            content = response.json()["choices"][0]["message"]["content"]
            return validate(parse_json(content), expected_year, current_year)
        except Exception as error:  # fall through to the next model
            log(f"model {model} failed ({type(error).__name__})")
    return None


def pdf_text(pdf: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)[:200_000]


# ---------------------------------------------------------------- BigQuery
def dedupe(rows: list[dict]) -> list[dict]:
    """Keep the first row per (symbol, fiscal_year); callers pass newest first."""
    kept: dict[tuple, dict] = {}
    for row in rows:
        kept.setdefault((row["symbol"], row["fiscal_year"]), row)
    return list(kept.values())


def merge_sql(target: str, staging: str) -> str:
    updates = ", ".join(f"{c} = s.{c}" for c in COLUMNS[2:])
    columns = ", ".join(COLUMNS)
    values = ", ".join(f"s.{c}" for c in COLUMNS)
    return f"""BEGIN TRANSACTION;
MERGE `{target}` t
USING (
  SELECT {columns} FROM `{staging}` WHERE run_id = @run_id
  QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, fiscal_year ORDER BY collected_at DESC) = 1
) s
ON t.symbol = s.symbol AND t.fiscal_year = s.fiscal_year
WHEN MATCHED THEN UPDATE SET {updates}
WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values});
COMMIT TRANSACTION;"""


def duplicate_sql(target: str) -> str:
    return (f"SELECT symbol, fiscal_year FROM `{target}` "
            "GROUP BY symbol, fiscal_year HAVING COUNT(*) > 1 LIMIT 1")


class Store:
    """Reads existing rows and merges new ones through managed staging."""

    def __init__(self, client: Any, project: str, dataset: str) -> None:
        self.client = client
        self.target = f"{project}.{dataset}.financials"
        self.staging = f"{project}.{dataset}.financials_staging"

    def existing(self) -> dict[str, tuple[str, int]]:
        """document_link -> (symbol, fiscal_year) for rows already loaded."""
        query = f"SELECT symbol, fiscal_year, document_link FROM `{self.target}`"
        return {r.document_link: (r.symbol, r.fiscal_year)
                for r in self.client.query(query).result() if r.document_link}

    def write(self, rows: list[dict]) -> str:
        from google.cloud import bigquery

        rows = dedupe(rows)
        run_id = "monthly_" + uuid4().hex
        params = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)])
        staged = [{**row, "run_id": run_id} for row in rows]
        self.client.load_table_from_json(
            staged, self.staging,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")).result()
        try:
            self.client.query(merge_sql(self.target, self.staging), job_config=params).result()
        finally:
            self.client.query(f"DELETE FROM `{self.staging}` WHERE run_id = @run_id",
                              job_config=params).result()
        if list(self.client.query(duplicate_sql(self.target)).result()):
            raise RuntimeError("financials holds duplicate (symbol, fiscal_year) rows")
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- job
def run(fetch, get_pdf, post, store, api_key: str, models=MODELS,
        now: datetime | None = None, to_text=pdf_text) -> dict:
    now = now or datetime.now(timezone.utc)
    year = now.year
    known = store.existing()
    stats = {"symbols": 0, "documents": 0, "skipped": 0, "written": 0, "failed": 0}
    receipts, pending = [], []
    symbols = parse_symbols(fetch(LIST_URL, {}))
    if not symbols:
        raise RuntimeError("no symbols found on the listing page")
    for index, symbol in enumerate(symbols, 1):
        stats["symbols"] += 1
        done: set[int] = set()  # fiscal years settled by a newer document
        try:
            docs = annual_documents(fetch, symbol, year)
        except Exception as error:
            stats["failed"] += 1
            log(f"{symbol}: listing failed ({type(error).__name__}: {error})")
            docs = []
        for doc in docs:
            stats["documents"] += 1
            link, hint = doc["document_link"], year_hint(doc["title"], doc["document_link"])
            if link in known:
                done.add(known[link][1])
                stats["skipped"] += 1
                continue
            if hint in done:
                stats["skipped"] += 1
                continue
            try:
                result = extract(post, to_text(get_pdf(link)), api_key, models, hint, year)
            except Exception as error:
                result = None
                log(f"{symbol}: document failed ({type(error).__name__})")
            if result is None:
                stats["failed"] += 1
                continue
            if result["fiscal_year"] in done:
                stats["skipped"] += 1
                continue
            done.add(result["fiscal_year"])
            pending.append({"symbol": symbol, **result, "document_link": link,
                            "collected_at": now.isoformat()})
            log(f"{symbol}: FY{result['fiscal_year']} extracted")
        if pending and (index % BATCH_SYMBOLS == 0 or index == len(symbols)):
            receipts.append(store.write(pending))
            stats["written"] += len(dedupe(pending))
            pending = []
    log("summary " + json.dumps(stats, sort_keys=True))
    if receipts:
        from ingestion_observability import managed_import_completion

        log(json.dumps(managed_import_completion("financials", receipts), sort_keys=True))
    return stats


def config(env: dict) -> dict:
    project = env.get("TRADVISOR_TARGET_PROJECT_ID") or env.get("GOOGLE_CLOUD_PROJECT", "")
    dataset = env.get("TRADVISOR_INGESTION_DATASET", "stocks")
    primary = env.get("TRADVISOR_FINANCIALS_MODEL_PRIMARY") or MODELS[0]
    fallbacks = env.get("TRADVISOR_FINANCIALS_MODEL_FALLBACKS", ",".join(MODELS[1:]))
    models = tuple(dict.fromkeys([primary, *(m.strip() for m in fallbacks.split(",") if m.strip())]))
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("invalid project")
    if not re.fullmatch(r"[A-Za-z_]\w*", dataset):
        raise ValueError("invalid dataset")
    return {"project": project, "dataset": dataset, "models": list(models)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = config(dict(os.environ))
    except ValueError as error:
        log(f"configuration failed: {error}")
        raise SystemExit(1) from None
    if args.check_config:
        log(json.dumps(cfg, sort_keys=True))
        return
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        log("configuration failed: OPENROUTER_API_KEY missing")
        raise SystemExit(1)

    from curl_cffi import requests as http
    from google.cloud import bigquery

    session = http.Session(impersonate="chrome", timeout=60)

    def get(url: str, params: dict | None = None, headers: dict | None = None):
        reason = "unknown"
        for attempt in range(3):
            time.sleep(0.5 * (attempt + 1))
            try:
                response = session.get(url, params=params, headers=headers)
                if response.status_code == 200 and response.url.startswith(BASE + "/"):
                    return response
                reason = f"HTTP {response.status_code} at {urlparse(response.url).netloc}"
            except Exception as error:
                reason = type(error).__name__
        raise RuntimeError(f"RichBourse request failed ({reason})")

    try:
        run(fetch=lambda url, params: get(url, params, LIST_HEADERS).text,
            get_pdf=lambda url: get(url).content,
            post=session.post,
            store=Store(bigquery.Client(project=cfg["project"]), cfg["project"], cfg["dataset"]),
            api_key=api_key, models=cfg["models"])
    except Exception as error:
        log(f"job failed ({type(error).__name__})")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])
