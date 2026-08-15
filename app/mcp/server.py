"""FastMCP Protocol Server exposing TRADVISOR financial tools to AI Agents."""
from fastmcp import FastMCP
from app.data.repository import get_stock_financials, get_stock_dividends, get_stock_price_history
from app.core.fundamental.analyzer import calculate_fundamental_ratios
from app.core.signals.passive_income import calculate_passive_income_score
from app.core.signals.technical import calculate_technical_indicators, generate_technical_signal_consensus

mcp = FastMCP("TRADVISOR Financial Assistant")

@mcp.tool()
def get_stock_passive_income_score(symbol: str) -> dict:
    """
    Tool for AI Agents to calculate passive income score (0-100) and dividend ratios for a BRVM stock.
    
    Args:
        symbol: BRVM Stock Symbol (e.g. 'NTLC', 'ORGT')
    """
    fin_df = get_stock_financials(symbol)
    div_df = get_stock_dividends(symbol)
    
    latest_div = float(div_df.iloc[0]['dividend']) if not div_df.empty and 'dividend' in div_df.columns else None
    ratios = calculate_fundamental_ratios(fin_df, latest_close=None, latest_dividend=latest_div)
    score_data = calculate_passive_income_score(
        div_yield=ratios.get('dividend_yield'),
        payout_ratio=ratios.get('payout_ratio'),
        debt_to_equity=ratios.get('debt_to_equity'),
        roe=ratios.get('roe'),
        years_with_div=len(div_df)
    )
    return {
        "symbol": symbol,
        "score": score_data['total_score'],
        "rating": score_data['rating_category'],
        "ratios": ratios
    }

@mcp.tool()
def analyze_technical_indicators(symbol: str, days: int = 365) -> dict:
    """
    Tool for AI Agents to run 10 TA indicators and return signal consensus for a stock.
    
    Args:
        symbol: BRVM Stock Symbol (e.g. 'NTLC', 'ORGT')
        days: Number of trading days history to evaluate
    """
    price_df = get_stock_price_history(symbol, days=days)
    if price_df.empty:
        return {"error": f"No price data found for {symbol}"}
    
    ta_df = calculate_technical_indicators(price_df)
    consensus = generate_technical_signal_consensus(ta_df)
    return {
        "symbol": symbol,
        "consensus": consensus
    }

if __name__ == "__main__":
    mcp.run()
