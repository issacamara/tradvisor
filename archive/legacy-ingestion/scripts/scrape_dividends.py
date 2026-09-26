import json
import hashlib
import os
import re
from bs4 import BeautifulSoup
from curl_cffi import requests
import functions_framework
import pandas as pd
import yaml
from helper import save_dataframe_as_csv


PAYMENT_COLUMNS = (
    "payment_id",
    "symbol",
    "amount",
    "payment_date",
    "fiscal_year",
    "payment_status",
    "amount_unit",
    "amount_basis",
    "distribution_type",
    "coverage_start_date",
    "coverage_end_date",
    "coverage_status",
    "source_record",
)


def _first_value(record, *names):
    for name in names:
        value = record.get(name)
        if value is not None and value != "":
            return value
    return None


def _payment_id(record, duplicate_index=0):
    source_id = _first_value(record, "payment_id", "distribution_id", "id", "uid")
    if source_id is not None:
        identity = {"source_id": str(source_id)}
    else:
        identity = {
            "symbol": _first_value(record, "symbol", "s"),
            "amount": _first_value(record, "amount", "dividend", "m"),
            "payment_date": _first_value(record, "payment_date", "date", "p"),
            "fiscal_year": _first_value(record, "fiscal_year", "exercise_year", "exercice", "e"),
            "source_record": record,
            "duplicate_index": duplicate_index,
        }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_payment(record, duplicate_index=0):
    """Keep unsupported source semantics explicit instead of interpreting them."""
    return {
        "payment_id": _payment_id(record, duplicate_index),
        "symbol": _first_value(record, "symbol", "SYMBOL", "s"),
        "amount": _first_value(record, "amount", "dividend", "DIVIDEND", "m"),
        "payment_date": _first_value(record, "payment_date", "PAYMENT_DATE", "date", "p"),
        "fiscal_year": _first_value(record, "fiscal_year", "FISCAL_YEAR", "exercise_year", "exercice", "e"),
        "payment_status": _first_value(record, "payment_status", "status", "state"),
        "amount_unit": _first_value(record, "amount_unit", "unit", "currency_unit"),
        "amount_basis": _first_value(record, "amount_basis", "basis", "gross_net"),
        "distribution_type": _first_value(record, "distribution_type", "dividend_type", "type"),
        "coverage_start_date": _first_value(record, "coverage_start_date", "coverage_start"),
        "coverage_end_date": _first_value(record, "coverage_end_date", "coverage_end"),
        "coverage_status": _first_value(record, "coverage_status", "coverage_complete"),
        "source_record": json.dumps(record, sort_keys=True, ensure_ascii=False, default=str),
    }


def _rows_to_frame(records):
    occurrences = {}
    rows = []
    for record in records:
        fingerprint = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
        duplicate_index = occurrences.get(fingerprint, 0)
        occurrences[fingerprint] = duplicate_index + 1
        rows.append(_normalized_payment(record, duplicate_index))
    return pd.DataFrame(rows, columns=PAYMENT_COLUMNS)


def scrape_dividends(url):
    """Scrape dividend data from BRVM website (Richbourse).

    Returns normalized payment facts using lowercase contract field names.
    """
    params = {"hl": "en"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.richbourse.com/common/dividende",
    }

    session = requests.Session()
    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
        impersonate="chrome",
        allow_redirects=True,
    )

    if response.status_code != 200:
        raise ValueError(
            f"Failed to fetch page. HTTP status code: {response.status_code}"
        )

    all_data = []

    # --- Method 1: Extract direct JS data array (window.rbSimData) ---
    # Richbourse embeds complete dividend JSON data on page load
    match = re.search(r"window\.rbSimData\s*=\s*(\[.*?\]);", response.text)
    if match:
        try:
            raw_json = match.group(1)
            json_data = json.loads(raw_json)

            for item in json_data:
                if _first_value(item, "s", "symbol"):
                    all_data.append(item)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"Error parsing rbSimData JSON: {e}")

    # --- Method 2: Fallback to HTML table parsing ---
    if not all_data:
        soup = BeautifulSoup(response.content, "html.parser")

        # Locate dividend table
        table = (
            soup.find("table", {"class": "table table-striped table-bordered"})
            or soup.find("table", {"class": "table table-striped"})
            or soup.find("table", {"class": "tablesorter"})
        )

        if not table:
            for t in soup.find_all("table"):
                headers_text = [
                    h.get_text().strip().upper() for h in t.find_all("th")
                ]
                if any("DIVIDENDE" in h or "SOCIÉTÉ" in h for h in headers_text):
                    table = t
                    break

        if table and table.find("tbody"):
            for row in table.find("tbody").find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 6:
                    continue

                try:
                    # Column 1: Symbol in link
                    symbol_link = cells[1].find("a", href=True)
                    if symbol_link:
                        symbol = symbol_link["href"].split("/")[-1]
                    else:
                        continue

                    # Column 2: Dividend amount
                    dividend_text = cells[2].get_text(strip=True)
                    dividend_text = re.sub(r"[^\d.,]", "", dividend_text)
                    dividend_text = (
                        dividend_text.replace(" ", "")
                        .replace("\xa0", "")
                        .replace(",", ".")
                    )
                    amount = float(dividend_text) if dividend_text else None

                    # Column 5: Payment Date
                    payment_date = cells[5].get_text(strip=True)
                    if (
                        "inconnue" in payment_date.lower()
                        or not payment_date
                    ):
                        payment_date = None
                    else:
                        parts = payment_date.split("/")
                        if len(parts) == 3:
                            day, month, year = parts
                            payment_date = (
                                f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            )
                        else:
                            payment_date = None

                    all_data.append(
                        {
                            "symbol": symbol,
                            "amount": amount,
                            "payment_date": payment_date,
                            "source_table_row": [cell.get_text(" ", strip=True) for cell in cells],
                        }
                    )
                except Exception:
                    continue

    if not all_data:
        raise ValueError("No dividend data could be extracted.")

    return _rows_to_frame(all_data)


@functions_framework.http
def entry_point(request=None):
    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)

    df = scrape_dividends(config["url"]["dividends"])
    return save_dataframe_as_csv(df, "dividends", config)


# Local testing
if __name__ == "__main__":
    if not (os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET")):
        print(entry_point())
