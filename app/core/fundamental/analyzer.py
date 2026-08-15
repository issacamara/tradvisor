"""Fundamental ratio analytics module deriving metrics directly from financial statements."""
import pandas as pd

def calculate_fundamental_ratios(df_fin: pd.DataFrame, latest_close: float | None = None, latest_dividend: float | None = None) -> dict:
    """Calculates fundamental ratios (ROE, D/E, Profit Margin, Dividend Yield, Payout Ratio) for the latest available year."""
    if df_fin.empty:
        return {}
    
    latest = df_fin.iloc[0]
    net_income = float(latest['net_income']) if pd.notnull(latest.get('net_income')) else None
    equity = float(latest['total_equity']) if pd.notnull(latest.get('total_equity')) else None
    debt = float(latest['total_debt']) if pd.notnull(latest.get('total_debt')) else None
    revenue = float(latest['revenue']) if pd.notnull(latest.get('revenue')) else None
    cash = float(latest['cash_and_cash_equivalents']) if pd.notnull(latest.get('cash_and_cash_equivalents')) else None

    roe = (net_income / equity * 100) if (net_income is not None and equity and equity != 0) else None
    debt_to_equity = (debt / equity) if (debt is not None and equity and equity != 0) else None
    profit_margin = (net_income / revenue * 100) if (net_income is not None and revenue and revenue != 0) else None
    cash_to_debt = (cash / debt) if (cash is not None and debt and debt != 0) else None

    div_yield = (latest_dividend / latest_close * 100) if (latest_dividend and latest_close and latest_close != 0) else None
    payout_ratio = (latest_dividend / net_income * 100) if (latest_dividend and net_income and net_income > 0) else None

    return {
        "fiscal_year": latest.get('fiscal_year'),
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "profit_margin": profit_margin,
        "cash_to_debt": cash_to_debt,
        "dividend_yield": div_yield,
        "payout_ratio": payout_ratio,
        "net_income": net_income,
        "total_equity": equity,
        "total_debt": debt,
        "revenue": revenue
    }
