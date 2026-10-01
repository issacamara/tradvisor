"""Daily BigQuery preparation for the Long-Term financial input slice."""

from __future__ import annotations

from typing import Final

FINANCIAL_COLUMNS: Final = (
    "symbol", "fiscal_year", "revenue", "net_income", "total_debt",
    "cash_and_cash_equivalents", "total_equity", "collected_at", "document_link",
)


def build_financial_precompute_sql(source_table: str, destination_table: str) -> str:
    """Build the bounded daily query used by the analytical preparation job."""
    for label, table in (("source", source_table), ("destination", destination_table)):
        if not table or "`" in table or ";" in table or any(char.isspace() for char in table):
            raise ValueError(f"{label} table must be a plain project.dataset.table identifier")
    return f"""
CREATE OR REPLACE TABLE `{destination_table}`
PARTITION BY DATE(fiscal_year, 12, 31)
CLUSTER BY symbol AS
SELECT {', '.join(FINANCIAL_COLUMNS)}
FROM `{source_table}`
WHERE fiscal_year IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) <= 3
""".strip()
