import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
import functions_framework
import pandas as pd
import yaml
from helper import save_dataframe_as_csv


def scrape_dividends(url):
    """Scrape dividend data from BRVM website (Richbourse).

    Returns DataFrame with columns: SYMBOL, DIVIDEND, PAYMENT_DATE, DATE
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
                symbol = item.get("s")
                dividend = round(float(item.get("m", 0)), 4)
                payment_date = item.get("p")

                # Validate date string or handle unknown/missing
                if not payment_date or "inconnue" in str(payment_date).lower():
                    payment_date = None

                if symbol:
                    all_data.append(
                        {
                            "SYMBOL": symbol,
                            "DIVIDEND": dividend,
                            "PAYMENT_DATE": payment_date,
                        }
                    )
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
                    dividend = (
                        float(dividend_text) if dividend_text else 0.0
                    )

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
                            "SYMBOL": symbol,
                            "DIVIDEND": dividend,
                            "PAYMENT_DATE": payment_date,
                        }
                    )
                except Exception:
                    continue

    if not all_data:
        raise ValueError("No dividend data could be extracted.")

    df = pd.DataFrame(all_data)
    df["DATE"] = datetime.now().strftime("%Y-%m-%d")

    return df


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