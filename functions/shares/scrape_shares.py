from __future__ import annotations

import hashlib
import io
import json
import random
import re
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from ingestion_observability import observed_entrypoint

RAW_COLUMNS = (
    "symbol",
    "name",
    "open",
    "high",
    "low",
    "volume",
    "close",
)

SOURCE_ID = "sikafinance-shares"
PARSER_VERSION = "shares-parser-v2"
PRICE_BASIS_REF = "raw-v1"
BRVM_SESSION_URL = "https://www.brvm.org/fr/jours-feries"
REQUEST_TIMEOUT_SECONDS = 20
RETRY_BUDGET_SECONDS = 120
MAX_RETRY_ATTEMPTS = 4
RETRIABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

FRENCH_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}


class SourceRequestRetryExhausted(RuntimeError):
    """A transient source failure outlasted the bounded scrape retry budget."""


def _retry_after_seconds(headers: object) -> float | None:
    if not hasattr(headers, "get"):
        return None
    try:
        value = headers.get("Retry-After")
        delay = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
    return delay if delay >= 0 else None


def _is_retryable_transport_error(error: Exception) -> bool:
    return isinstance(error, (ConnectionError, TimeoutError, OSError)) or (
        error.__class__.__module__.startswith("curl_cffi")
        and error.__class__.__name__ in {"RequestException", "RequestsError", "Timeout"}
    )


def _request_with_retry(
    request: Callable[[float], object],
    *,
    deadline: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
):
    """Make a source request without exceeding the scrape's shared deadline."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            response = request(min(REQUEST_TIMEOUT_SECONDS, remaining))
        except Exception as error:
            if not _is_retryable_transport_error(error):
                raise
            last_error = error
            retry_after = None
        else:
            status_code = getattr(response, "status_code", None)
            if status_code not in RETRIABLE_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = RuntimeError(f"transient source response: {status_code}")
            retry_after = _retry_after_seconds(getattr(response, "headers", None))

        if attempt == MAX_RETRY_ATTEMPTS - 1:
            break
        delay = (
            retry_after
            if retry_after is not None
            else uniform(1, min(2 ** (attempt + 1), 30))
        )
        remaining = deadline - monotonic()
        if delay >= remaining:
            break
        sleep(delay)

    raise SourceRequestRetryExhausted("source retry budget exhausted") from last_error


def parse_localized_decimal(value: str) -> Decimal | None:
    """Parse French or English decimal/grouping separators without float loss."""
    text = value.strip().replace("\xa0", " ").replace("\u202f", " ")
    if not text or text in {"-", "—"}:
        return None

    # Spaces are accepted only as conventional three-digit grouping marks.
    if " " in text:
        match = re.fullmatch(r"(\d{1,3}(?: \d{3})+)([.,]\d+)?", text)
        if match is None:
            raise ValueError(f"invalid localized decimal: {value!r}")
        text = match.group(1).replace(" ", "") + (match.group(2) or "")

    if "," in text and "." in text:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        integer, fraction = text.rsplit(decimal_separator, 1)
        if not fraction.isdigit() or decimal_separator in integer:
            raise ValueError(f"invalid localized decimal: {value!r}")
        if grouping_separator in integer:
            groups = integer.split(grouping_separator)
            if not (1 <= len(groups[0]) <= 3 and groups[0].isdigit()) or any(
                len(group) != 3 or not group.isdigit() for group in groups[1:]
            ):
                raise ValueError(f"invalid localized decimal: {value!r}")
            integer = "".join(groups)
        elif not integer.isdigit():
            raise ValueError(f"invalid localized decimal: {value!r}")
        text = integer + "." + fraction
    elif "," in text:
        text = _normalize_single_separator(text, ",", value)
    elif "." in text:
        text = _normalize_single_separator(text, ".", value)
    elif not text.isdigit():
        raise ValueError(f"invalid localized decimal: {value!r}")

    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"invalid localized decimal: {value!r}") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"share observation must be a finite nonnegative decimal: {value!r}")
    return result


def _normalize_single_separator(text: str, separator: str, original: str) -> str:
    if text.count(separator) == 1:
        integer, fraction = text.split(separator)
        if not integer.isdigit() or not fraction.isdigit():
            raise ValueError(f"invalid localized decimal: {original!r}")
        return integer + "." + fraction

    groups = text.split(separator)
    if not (1 <= len(groups[0]) <= 3 and groups[0].isdigit()) or any(
        len(group) != 3 or not group.isdigit() for group in groups[1:]
    ):
        raise ValueError(f"invalid localized decimal: {original!r}")
    return "".join(groups)


def _normalize_french_text(value: str) -> str:
    return (
        value.lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("ô", "o")
        .replace("ï", "i")
        .replace("î", "i")
        .replace("ç", "c")
    )


def _parse_brvm_display_date(page_text: str) -> date | None:
    normalized = _normalize_french_text(page_text)
    match = re.search(
        r"\b\w+\s*,\s*(\d{1,2})\s+([a-z]+),\s*(\d{4})\s*-\s*\d{1,2}:\d{2}",
        normalized,
    )
    if match is None:
        return None
    month = FRENCH_MONTHS.get(match.group(2))
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def _parse_brvm_holidays(page_text: str) -> set[date]:
    holidays: set[date] = set()
    for day, month, year in re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", page_text):
        try:
            holidays.add(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return holidays


def resolve_brvm_session(page_text: str) -> tuple[date | None, str]:
    """Return a verified closed BRVM session date, or preserve uncertainty.

    The official page is a session-evidence source, while Sika Finance remains
    the price observation source. A displayed calendar date alone is not enough:
    it must be a weekday, absent from BRVM's published holidays, and explicitly
    report a closed session before the prices are attributed to that date.
    """
    session_date = _parse_brvm_display_date(page_text)
    if session_date is None:
        return None, "unknown"
    normalized = _normalize_french_text(page_text)
    if session_date.weekday() >= 5 or session_date in _parse_brvm_holidays(page_text):
        return None, "unknown"
    if "seance fermee" not in normalized:
        return None, "unknown"
    return session_date, "verified"


def scrape_brvm_session(
    url: str = BRVM_SESSION_URL, *, retry_deadline: float | None = None
) -> tuple[date | None, str]:
    from curl_cffi import requests

    deadline = retry_deadline or time.monotonic() + RETRY_BUDGET_SECONDS
    page = _request_with_retry(
        lambda timeout: requests.get(
            url=url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            impersonate="chrome",
            allow_redirects=True,
        ),
        deadline=deadline,
    )
    return resolve_brvm_session(page.text)


def _source_observation_id(row: dict[str, object], collected_at: str) -> str:
    identity = "|".join([build_source_revision_id(row), collected_at])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_source_revision_id(row: dict[str, object]) -> str:
    """Identify source content independently from a collection retry."""
    identity = json.dumps(
        {column: str(row[column]) for column in RAW_COLUMNS},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def scrape(url: str, *, retry_deadline: float | None = None):
    from bs4 import BeautifulSoup
    from curl_cffi import requests

    params = {"hl": "en"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    session = requests.Session()
    deadline = retry_deadline or time.monotonic() + RETRY_BUDGET_SECONDS
    page = _request_with_retry(
        lambda timeout: session.get(
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
            impersonate="chrome",
            allow_redirects=True,
        ),
        deadline=deadline,
    )
    soup = BeautifulSoup(page.content, "html.parser")
    table = soup.find("table", {"class": "tablesorter tbl100_6 tbl1"})
    if table is None or table.find("tbody") is None:
        raise ValueError("share table is missing")

    rows: list[dict[str, object]] = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 8:
            raise ValueError("share row does not contain the expected source columns")
        del cells[-1]
        del cells[-2]
        symbol_link = cells[0].find("a", href=True)
        if symbol_link is None:
            raise ValueError("share row is missing its source symbol link")
        symbol_parts = symbol_link["href"].split("_")
        if len(symbol_parts) < 2:
            raise ValueError("share row has an unrecognized source symbol link")
        symbol = symbol_parts[1].split(".")[0]
        source_values = [
            cell.get_text(separator=" ", strip=True).replace("\xa0", " ")
            for cell in cells[1:]
        ]
        rows.append(dict(zip(RAW_COLUMNS, [symbol, cells[0].get_text(strip=True), *source_values])))
    return rows


def scrape_brvm_shares(
    url: str,
    *,
    collected_at: datetime | None = None,
    session_evidence_url: str = BRVM_SESSION_URL,
) -> pd.DataFrame:
    import pandas as pd

    instant = collected_at or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    collected_text = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    retry_deadline = time.monotonic() + RETRY_BUDGET_SECONDS
    session_date, session_date_status = scrape_brvm_session(
        session_evidence_url, retry_deadline=retry_deadline
    )
    session_date_text = session_date.isoformat() if session_date else ""

    observations = []
    for source_row in scrape(url, retry_deadline=retry_deadline):
        row: dict[str, object] = {
            **source_row,
            "source_id": SOURCE_ID,
            "session_date": session_date_text,
            "session_date_status": session_date_status,
            "trade_status": "unknown",
            "collected_at": collected_text,
            "known_at": collected_text,
            "parser_version": PARSER_VERSION,
            "basis": "actual",
            "price_basis_ref": PRICE_BASIS_REF,
            "original_source_date": session_date_text,
            "suspension_status": "unknown",
        }
        parse_errors = []
        for column in ("open", "high", "low", "volume", "close"):
            try:
                parsed = parse_localized_decimal(str(source_row[column]))
            except ValueError:
                parsed = None
                parse_errors.append(column)
            row[f"parsed_{column}"] = "" if parsed is None else format(parsed, "f")
        row["numeric_parse_status"] = "invalid" if parse_errors else "valid"
        row["numeric_parse_errors"] = ",".join(parse_errors)
        try:
            volume = parse_localized_decimal(str(source_row["volume"]))
        except ValueError:
            volume = None
        if volume is not None and volume > 0 and volume == volume.to_integral_value():
            row["trade_status"] = "traded"
        row["source_revision_id"] = build_source_revision_id(source_row)
        row["observation_id"] = _source_observation_id(source_row, collected_text)
        observations.append(row)

    return pd.DataFrame(observations)


def _save_raw_observations(frame, collected_at: datetime, configuration=None) -> str:
    """Write each scrape as a new GCS object; a retry must never replace evidence."""
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    stamp = collected_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    csv_text = frame.to_csv(index=False, sep="|")
    from google.api_core.exceptions import PreconditionFailed
    from google.auth import default
    from google.cloud import storage
    from helper import get_project_number

    _, project_id = default()
    if configuration is not None:
        configuration.validate_application_default_project(project_id)
        bucket_name = configuration.data_bucket
    else:
        bucket_name = f"data-{get_project_number(project_id)}"
    client = storage.Client(project=project_id) if configuration is not None else storage.Client()
    bucket = client.bucket(bucket_name)
    for suffix in range(1000):
        suffix_text = "" if suffix == 0 else f"-{suffix}"
        filename = f"shares-{stamp}{suffix_text}.csv"
        try:
            bucket.blob(filename).upload_from_string(
                csv_text, content_type="text/csv", if_generation_match=0
            )
        except FileExistsError:
            continue
        except PreconditionFailed:
            continue
        return f"File saved to GCS bucket '{bucket.name}' as '{filename}'.\n"
    raise FileExistsError("could not allocate a unique share observation object")


@observed_entrypoint("ingestion.shares.scrape")
def entry_point(request=None):
    from ingestion_configuration import IngestionConfiguration

    configuration = IngestionConfiguration.from_environment()

    endpoints = configuration.endpoints
    collected_at = datetime.now(timezone.utc)
    df = scrape_brvm_shares(
        endpoints["shares"],
        collected_at=collected_at,
        session_evidence_url=endpoints["brvm_session"],
    )
    return _save_raw_observations(df, collected_at, configuration)


if __name__ == "__main__":
    entry_point()
