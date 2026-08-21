"""BRVM Long-Term Stock Checklist Analyzer.

Implements the 9-category scoring system from the BRVM investment checklist:
1. Business Quality (1-5)
2. Revenue Trend (1-5)
3. Profitability (1-5)
4. Balance Sheet (1-5)
5. Dividend Quality (1-5)
6. Valuation (1-5)
7. Liquidity (1-5)
8. Risk Factors (1-5)
9. Long-Term Fit (1-5)

Total: 45 points max
- 40-45: Very strong candidate
- 30-39: Interesting, needs caution
- 20-29: Weak or average
- Below 20: Avoid
"""
import pandas as pd
import numpy as np


def analyze_checklist(
    df_fin: pd.DataFrame,
    df_div: pd.DataFrame,
    df_price: pd.DataFrame,
    latest_price: float | None = None,
    sector: str | None = None,
) -> dict:
    """
    Analyzes a stock against the 9-category BRVM checklist.

    Args:
        df_fin: Financial statements DataFrame
        df_div: Dividend history DataFrame
        df_price: Price history DataFrame
        latest_price: Current/latest stock price
        sector: Company sector (optional)

    Returns:
        Dictionary with scores for each category and total score
    """
    scores = {
        "business_quality": _score_business_quality(sector),
        "revenue_trend": _score_revenue_trend(df_fin),
        "profitability": _score_profitability(df_fin),
        "balance_sheet": _score_balance_sheet(df_fin),
        "dividend_quality": _score_dividend_quality(df_div, df_fin),
        "valuation": _score_valuation(df_fin, latest_price),
        "liquidity": _score_liquidity(df_price),
        "risk_factors": _score_risk_factors(df_fin, sector),
        "long_term_fit": _score_long_term_fit(df_fin, df_div, latest_price),
    }

    total_score = sum(scores.values())

    # Determine rating category
    if total_score >= 40:
        rating = "Very Strong Candidate"
    elif total_score >= 30:
        rating = "Interesting - Use Caution"
    elif total_score >= 20:
        rating = "Weak / Average"
    else:
        rating = "Avoid"

    return {
        "scores": scores,
        "total_score": total_score,
        "max_score": 45,
        "rating": rating,
    }


def _score_business_quality(sector: str | None) -> int:
    """Score business quality based on sector (defensive vs cyclical)."""
    if sector is None:
        return 3  # Neutral if unknown

    # Defensive sectors get higher scores
    defensive_sectors = ["Banking", "Telecom", "Utilities", "Food", "Pharmaceuticals"]
    cyclical_sectors = ["Industry", "Mining", "Construction", "Transport", "Energy"]

    if sector in defensive_sectors:
        return 5
    elif sector in cyclical_sectors:
        return 3
    else:
        return 4


def _score_revenue_trend(df_fin: pd.DataFrame) -> int:
    """Score revenue growth trend over 3-5 years."""
    if df_fin.empty or "revenue" not in df_fin.columns:
        return 1

    df = df_fin.sort_values("fiscal_year", ascending=True).dropna(subset=["revenue"])

    if len(df) < 2:
        return 2

    revenues = df["revenue"].values
    if len(revenues) >= 3:
        # Check 3-year CAGR
        cagr = (revenues[-1] / revenues[0]) ** (1 / (len(revenues) - 1)) - 1
        if cagr > 0.10:  # >10% CAGR
            return 5
        elif cagr > 0.05:  # >5% CAGR
            return 4
        elif cagr > 0:
            return 3
        elif cagr > -0.05:
            return 2
        else:
            return 1

    # Simple year-over-year growth
    growth_years = sum(1 for i in range(1, len(revenues)) if revenues[i] > revenues[i - 1])
    growth_pct = growth_years / (len(revenues) - 1)

    if growth_pct >= 0.8:
        return 5
    elif growth_pct >= 0.6:
        return 4
    elif growth_pct >= 0.4:
        return 3
    elif growth_pct >= 0.2:
        return 2
    else:
        return 1


def _score_profitability(df_fin: pd.DataFrame) -> int:
    """Score profitability based on net income and profit margins."""
    if df_fin.empty or "net_income" not in df_fin.columns:
        return 1

    df = df_fin.sort_values("fiscal_year", ascending=True).dropna(subset=["net_income"])

    if df.empty:
        return 1

    latest = df.iloc[-1]
    net_income = latest.get("net_income")
    revenue = latest.get("revenue")

    # Check if profitable
    if net_income is None or net_income <= 0:
        return 1

    # Calculate profit margin
    if revenue and revenue > 0:
        margin = (net_income / revenue) * 100
    else:
        margin = 0

    # Check trend
    if len(df) >= 3:
        recent_avg = df["net_income"].tail(3).mean()
        older_avg = df["net_income"].head(3).mean()
        improving = recent_avg > older_avg
    else:
        improving = True

    # Scoring
    score = 0

    # Profitability level
    if margin >= 15:
        score += 3
    elif margin >= 10:
        score += 2
    elif margin >= 5:
        score += 1
    else:
        score += 0

    # Trend
    if improving:
        score += 2
    else:
        score += 1

    return min(score, 5)


def _score_balance_sheet(df_fin: pd.DataFrame) -> int:
    """Score balance sheet health (debt, equity, cash)."""
    if df_fin.empty:
        return 1

    latest = df_fin.iloc[0]
    debt = latest.get("total_debt")
    equity = latest.get("total_equity")
    cash = latest.get("cash_and_cash_equivalents")

    score = 0

    # Debt to equity ratio
    if debt is not None and equity and equity > 0:
        de_ratio = debt / equity
        if de_ratio <= 0.5:
            score += 2
        elif de_ratio <= 1.0:
            score += 1
        elif de_ratio > 1.5:
            score -= 1

    # Cash to debt coverage
    if cash is not None and debt and debt > 0:
        cash_debt = cash / debt
        if cash_debt >= 0.5:
            score += 2
        elif cash_debt >= 0.2:
            score += 1
        elif cash_debt < 0.1:
            score -= 1

    # Positive equity
    if equity and equity > 0:
        score += 1

    return max(1, min(score, 5))


def _score_dividend_quality(df_div: pd.DataFrame, df_fin: pd.DataFrame) -> int:
    """Score dividend quality (consistency, coverage, yield)."""
    if df_div.empty:
        return 1

    score = 0

    # Consistency - years with dividends
    years_div = len(df_div)
    if years_div >= 5:
        score += 2
    elif years_div >= 3:
        score += 1
    elif years_div >= 1:
        score += 0

    # Yield (if we have price data, handled in valuation)
    # For now, check if dividends are present
    if not df_div.empty:
        score += 1

    # Payout ratio check
    if not df_fin.empty:
        latest_div = df_div.iloc[0].get("dividend")
        latest_net = df_fin.iloc[0].get("net_income")

        if latest_div and latest_net and latest_net > 0:
            payout = (latest_div / latest_net) * 100
            if payout <= 50:
                score += 2  # Well covered
            elif payout <= 70:
                score += 1  # Moderately covered
            elif payout > 90:
                score -= 1  # Overextended

    return max(1, min(score, 5))


def _score_valuation(df_fin: pd.DataFrame, latest_price: float | None) -> int:
    """Score valuation based on dividend yield."""
    if latest_price is None or latest_price <= 0:
        return 3  # Neutral if no price

    if df_fin.empty:
        return 3

    # Use dividend yield as proxy for valuation
    # (P/E would require EPS calculation)
    # This is simplified - in practice you'd want P/E

    # Check if we have dividend data to estimate yield
    # For now, return neutral score
    return 3


def _score_liquidity(df_price: pd.DataFrame) -> int:
    """Score liquidity based on trading volume."""
    if df_price.empty or "volume" not in df_price.columns:
        return 1

    # Check average volume over last 90 days
    recent = df_price.tail(90)
    if recent.empty:
        return 1

    avg_volume = recent["volume"].mean()

    # Arbitrary thresholds - should be calibrated to BRVM
    if avg_volume >= 100000:
        return 5
    elif avg_volume >= 50000:
        return 4
    elif avg_volume >= 20000:
        return 3
    elif avg_volume >= 10000:
        return 2
    else:
        return 1


def _score_risk_factors(df_fin: pd.DataFrame, sector: str | None) -> int:
    """Score risk factors (debt levels, currency exposure, etc.)."""
    score = 5  # Start with good score, deduct for risks

    if df_fin.empty:
        return 3

    latest = df_fin.iloc[0]
    debt = latest.get("total_debt")
    equity = latest.get("total_equity")

    # High debt is a risk
    if debt and equity and equity > 0:
        de_ratio = debt / equity
        if de_ratio > 2.0:
            score -= 2
        elif de_ratio > 1.5:
            score -= 1

    # Cyclical sectors have more risk
    if sector:
        high_risk_sectors = ["Mining", "Construction", "Transport", "Energy"]
        if sector in high_risk_sectors:
            score -= 1

    return max(1, min(score, 5))


def _score_long_term_fit(
    df_fin: pd.DataFrame, df_div: pd.DataFrame, latest_price: float | None
) -> int:
    """Score long-term fit based on dividend history and fundamentals."""
    score = 3  # Neutral start

    # Dividend payers are better for long-term
    if not df_div.empty:
        score += 1

    # Profitable companies
    if not df_fin.empty:
        net_income = df_fin.iloc[0].get("net_income")
        if net_income and net_income > 0:
            score += 1

    # Positive price (available)
    if latest_price and latest_price > 0:
        score += 1

    return max(1, min(score, 5))


def render_checklist_results(checklist_result: dict) -> None:
    """Render the checklist results as a formatted display."""
    import streamlit as st

    scores = checklist_result["scores"]
    total = checklist_result["total_score"]
    rating = checklist_result["rating"]

    # Color coding based on score
    if total >= 40:
        color = "green"
    elif total >= 30:
        color = "orange"
    elif total >= 20:
        color = "yellow"
    else:
        color = "red"

    # Display total score
    st.markdown(
        f"""
        <div style="background-color: {color}; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
            <h2 style="color: white; margin: 0;">{total} / 45</h2>
            <p style="color: white; margin: 0; font-weight: bold;">{rating}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Display individual scores
    col1, col2, col3 = st.columns(3)

    categories = [
        ("Business Quality", scores["business_quality"]),
        ("Revenue Trend", scores["revenue_trend"]),
        ("Profitability", scores["profitability"]),
        ("Balance Sheet", scores["balance_sheet"]),
        ("Dividend Quality", scores["dividend_quality"]),
        ("Valuation", scores["valuation"]),
        ("Liquidity", scores["liquidity"]),
        ("Risk Factors", scores["risk_factors"]),
        ("Long-Term Fit", scores["long_term_fit"]),
    ]

    for i, (name, score) in enumerate(categories):
        with [col1, col2, col3][i % 3]:
            # Color based on score
            if score >= 4:
                bar_color = "green"
            elif score >= 3:
                bar_color = "orange"
            else:
                bar_color = "red"

            st.markdown(
                f"""
                <div style="padding: 10px; margin: 5px 0; background-color: #f0f2f6; border-radius: 5px;">
                    <strong>{name}</strong><br>
                    <span style="color: {bar_color}; font-size: 20px;">{'●' * score}{'○' * (5 - score)}</span>
                    <span style="float: right;">{score}/5</span>
                </div>
                """,
                unsafe_allow_html=True,
            )