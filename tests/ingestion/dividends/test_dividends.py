from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts" / "scrape_dividends.py"

# The pure normalization helpers are tested without installing the legacy
# scraper's network/runtime dependencies.
bs4 = types.ModuleType("bs4")
bs4.BeautifulSoup = object
sys.modules["bs4"] = bs4
curl_cffi = types.ModuleType("curl_cffi")
curl_cffi.requests = types.SimpleNamespace(Session=object)
sys.modules["curl_cffi"] = curl_cffi
framework = types.ModuleType("functions_framework")
framework.http = lambda function: function
sys.modules["functions_framework"] = framework
sys.modules["yaml"] = types.ModuleType("yaml")
helper = types.ModuleType("helper")
helper.save_dataframe_as_csv = lambda dataframe, asset, config: dataframe
sys.modules["helper"] = helper
SPEC = importlib.util.spec_from_file_location("scrape_dividends", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_normalized_payment_preserves_explicit_facts_without_inference() -> None:
    frame = module._rows_to_frame([
        {
            "symbol": "ABC",
            "amount": "125.50",
            "payment_date": "2025-06-10",
            "fiscal_year": None,
            "payment_status": "paid",
            "amount_unit": "XOF/share",
            "amount_basis": "gross",
            "distribution_type": "ordinary",
            "coverage_status": "unknown",
        }
    ])

    row = frame.iloc[0]
    assert row["symbol"] == "ABC"
    assert row["amount"] == "125.50"
    assert row["payment_date"] == "2025-06-10"
    assert row["fiscal_year"] is None
    assert row["payment_status"] == "paid"
    assert row["amount_unit"] == "XOF/share"
    assert row["amount_basis"] == "gross"
    assert row["distribution_type"] == "ordinary"
    assert row["coverage_status"] == "unknown"


def test_explicit_source_identity_is_stable_and_duplicate_installments_remain_distinct() -> None:
    payment = {
        "payment_id": "issuer-2024-1",
        "symbol": "ABC",
        "amount": 50,
        "payment_date": "2025-05-01",
        "fiscal_year": 2024,
    }
    first = module._rows_to_frame([payment, payment])
    retry = module._rows_to_frame([payment])

    assert first.loc[0, "payment_id"] == first.loc[1, "payment_id"]
    assert retry.loc[0, "payment_id"] == first.loc[0, "payment_id"]
    assert first.loc[0, "source_record"] == first.loc[1, "source_record"]


def test_legacy_source_names_are_mapped_without_claiming_coverage() -> None:
    frame = module._rows_to_frame([
        {
            "SYMBOL": "ABC",
            "DIVIDEND": 75,
            "PAYMENT_DATE": "2025-05-01",
            "FISCAL_YEAR": 2024,
        }
    ])

    row = frame.iloc[0]
    assert row["symbol"] == "ABC"
    assert row["amount"] == 75
    assert row["fiscal_year"] == 2024
    assert row["coverage_status"] is None
