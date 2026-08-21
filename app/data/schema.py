"""Data schemas and table definitions for TRADVISOR BigQuery tables."""
from dataclasses import dataclass

PROJECT_ID = "prod-tradvisor"
DATASET_ID = "stocks"

SHARES_TABLE = f"{PROJECT_ID}.{DATASET_ID}.shares"
DIVIDENDS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.dividends"
FINANCIALS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.financials"
RATINGS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.ratings"
COMPANIES_TABLE = f"{PROJECT_ID}.{DATASET_ID}.brvm_companies"

@dataclass
class StockFinancial:
    symbol: str
    fiscal_year: int
    revenue: float | None
    net_income: float | None
    total_debt: float | None
    cash_and_cash_equivalents: float | None
    total_equity: float | None
    document_link: str | None

@dataclass
class StockRating:
    symbol: str
    rating_year: int
    rating_short_term: str | None
    rating_long_term: str | None
