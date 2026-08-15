"""Passive income scoring engine evaluating BRVM dividend stocks (0-100 scale)."""
import pandas as pd

def calculate_passive_income_score(div_yield: float | None, payout_ratio: float | None, debt_to_equity: float | None, roe: float | None, years_with_div: int = 0) -> dict:
    """
    Computes a 0-100 quantitative passive income score.
    Yield (40 pts) + Sustainability (30 pts) + Consistency (20 pts) + Profitability (10 pts).
    """
    yield_score = 0
    if div_yield is not None:
        if div_yield >= 8.0:
            yield_score = 40
        elif div_yield >= 5.0:
            yield_score = 25
        elif div_yield >= 3.0:
            yield_score = 10

    sustainability_score = 0
    if payout_ratio is not None and payout_ratio > 0:
        if payout_ratio <= 70.0:
            sustainability_score += 15
        elif payout_ratio <= 90.0:
            sustainability_score += 8
    
    if debt_to_equity is not None and debt_to_equity <= 1.5:
        sustainability_score += 10
    
    if roe is not None and roe > 0:
        sustainability_score += 5

    consistency_score = 0
    if years_with_div >= 5:
        consistency_score = 20
    elif years_with_div >= 3:
        consistency_score = 12
    elif years_with_div >= 1:
        consistency_score = 5

    profitability_score = 0
    if roe is not None:
        if roe >= 15.0:
            profitability_score = 10
        elif roe >= 10.0:
            profitability_score = 5

    total_score = yield_score + sustainability_score + consistency_score + profitability_score
    
    rating_category = "Weak"
    if total_score >= 80:
        rating_category = "Strong Buy (Top Tier)"
    elif total_score >= 60:
        rating_category = "Moderate Buy"
    elif total_score >= 40:
        rating_category = "Neutral / Hold"

    return {
        "total_score": total_score,
        "yield_score": yield_score,
        "sustainability_score": sustainability_score,
        "consistency_score": consistency_score,
        "profitability_score": profitability_score,
        "rating_category": rating_category
    }
