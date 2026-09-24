from __future__ import annotations

import hashlib
import io
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

RAW_COLUMNS = (
    "symbol",
    "name",
    "open",
    "high",
    "low",
    "volume",
    "close",
)


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


def _source_observation_id(row: dict[str, object], collected_at: str) -> str:
    identity = "|".join([str(row[column]) for column in RAW_COLUMNS] + [collected_at])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def scrape(url: str):
    from bs4 import BeautifulSoup
    from curl_cffi import requests

    params = {"hl": "en"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    session = requests.Session()
    page = session.get(
        url=url,
        params=params,
        headers=headers,
        timeout=30,
        impersonate="chrome",
        allow_redirects=True,
    )
    page.raise_for_status()
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


def scrape_brvm_shares(url: str, *, collected_at: datetime | None = None) -> pd.DataFrame:
    import pandas as pd

    instant = collected_at or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    collected_text = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    observations = []
    for source_row in scrape(url):
        row: dict[str, object] = {
            **source_row,
            "session_date": "",
            "session_date_status": "unknown",
            "trade_status": "unknown",
            "collected_at": collected_text,
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
        row["observation_id"] = _source_observation_id(row, collected_text)
        observations.append(row)

    return pd.DataFrame(observations)


def _save_raw_observations(frame, collected_at: datetime) -> str:
    """Write each scrape as a new object; a retry must never replace evidence."""
    import pandas as pd

    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    stamp = collected_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
    csv_text = frame.to_csv(index=False, sep="|")
    cloud_runtime = os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET")

    if cloud_runtime:
        from google.api_core.exceptions import PreconditionFailed
        from google.auth import default
        from google.cloud import storage
        from helper import get_project_number

        credentials, project_id = default()
        project_number = get_project_number(project_id)
        bucket = storage.Client().bucket(f"data-{project_number}")
        for suffix in range(1000):
            suffix_text = "" if suffix == 0 else f"-{suffix}"
            filename = f"shares-{stamp}{suffix_text}.csv"
            try:
                bucket.blob(filename).upload_from_string(
                    csv_text, content_type="text/csv", if_generation_match=0
                )
            except PreconditionFailed:
                continue
            return f"File saved to GCS bucket '{bucket.name}' as '{filename}'.\n"
        raise FileExistsError("could not allocate a unique share observation object")

    data_directory = os.path.join(os.path.dirname(__file__), "..", "data")
    for suffix in range(1000):
        suffix_text = "" if suffix == 0 else f"-{suffix}"
        filename = f"shares-{stamp}{suffix_text}.csv"
        path = os.path.join(data_directory, filename)
        try:
            with open(path, "x", encoding="utf-8", newline="") as raw_file:
                raw_file.write(csv_text)
        except FileExistsError:
            continue
        except Exception:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            raise
        return f"File saved locally as '{filename}'.\n"
    raise FileExistsError("could not allocate a unique share observation file")


def entry_point(request=None):
    import yaml

    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)
    collected_at = datetime.now(timezone.utc)
    df = scrape_brvm_shares(config["url"]["shares"], collected_at=collected_at)
    return _save_raw_observations(df, collected_at)


if __name__ == "__main__" and not (os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET")):
    print(entry_point())
