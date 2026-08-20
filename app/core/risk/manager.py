"""Risk management, ATR calculation, stop-loss rules, and position sizing."""
import pandas as pd

def calculate_atr(df_price: pd.DataFrame, period: int = 14) -> float | None:
    """Calculates Average True Range (ATR) over specified period."""
    if df_price.empty or len(df_price) < period + 1:
        return None
    
    df = df_price.copy().sort_values('date').reset_index(drop=True)
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)

    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    return float(atr) if pd.notnull(atr) else None

def calculate_position_size(portfolio_value_eur: float, risk_pct: float, entry_price_xof: float, stop_loss_xof: float, eur_xof_rate: float = 655.957) -> dict:
    """Calculates recommended position size, share count, and total capital risk."""
    if entry_price_xof <= stop_loss_xof or entry_price_xof <= 0:
        return {"error": "Entry price must be strictly greater than stop-loss price."}

    portfolio_xof = portfolio_value_eur * eur_xof_rate
    max_risk_amount_xof = portfolio_xof * (risk_pct / 100.0)
    risk_per_share_xof = entry_price_xof - stop_loss_xof

    shares_to_buy = int(max_risk_amount_xof // risk_per_share_xof)
    total_position_cost_xof = shares_to_buy * entry_price_xof
    total_position_cost_eur = total_position_cost_xof / eur_xof_rate

    return {
        "shares_to_buy": shares_to_buy,
        "total_cost_xof": total_position_cost_xof,
        "total_cost_eur": total_position_cost_eur,
        "max_risk_xof": max_risk_amount_xof,
        "max_risk_eur": max_risk_amount_xof / eur_xof_rate,
        "risk_per_share_xof": risk_per_share_xof,
        "portfolio_pct": (total_position_cost_xof / portfolio_xof * 100.0) if portfolio_xof else 0.0
    }
