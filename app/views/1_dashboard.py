"""View 1: Dashboard overview of BRVM stock signals and passive income opportunities."""
import streamlit as st
import pandas as pd
from app.data.repository import get_all_symbols, get_latest_prices, get_stock_financials, get_stock_dividends
from app.core.fundamental.analyzer import calculate_fundamental_ratios
from app.core.signals.passive_income import calculate_passive_income_score
from app.components.metrics import render_score_badge

def show():
    st.title("📈 TRADVISOR Dashboard")
    st.caption("BRVM Dividend Ranking & Market Signals Overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Target Passive Income", "2,000 EUR/mo", "1,311,914 XOF")
    col2.metric("Target Capital", "100,000 EUR", "5,000 EUR/yr contribution")
    col3.metric("Target Market", "BRVM", "West Africa")
    col4.metric("Data Cache TTL", "24 Hours", "BigQuery")

    st.subheader("💰 Top Passive Income Opportunities (BRVM)")

    symbols = get_all_symbols()
    prices_df = get_latest_prices().set_index('SYMBOL') if not get_latest_prices().empty else pd.DataFrame()

    results = []
    with st.spinner("Analyzing stocks for passive income signals..."):
        for sym in symbols[:15]:
            fin_df = get_stock_financials(sym)
            div_df = get_stock_dividends(sym)
            
            latest_price = float(prices_df.loc[sym, 'CLOSE']) if (not prices_df.empty and sym in prices_df.index) else None
            latest_div = float(div_df.iloc[0]['dividend']) if not div_df.empty and 'dividend' in div_df.columns else None
            years_div = len(div_df) if not div_df.empty else 0

            ratios = calculate_fundamental_ratios(fin_df, latest_close=latest_price, latest_dividend=latest_div)
            score_data = calculate_passive_income_score(
                div_yield=ratios.get('dividend_yield'),
                payout_ratio=ratios.get('payout_ratio'),
                debt_to_equity=ratios.get('debt_to_equity'),
                roe=ratios.get('roe'),
                years_with_div=years_div
            )

            results.append({
                "Symbol": sym,
                "Close Price (XOF)": latest_price,
                "Dividend Yield (%)": round(ratios.get('dividend_yield'), 2) if ratios.get('dividend_yield') else "N/A",
                "ROE (%)": round(ratios.get('roe'), 2) if ratios.get('roe') else "N/A",
                "Payout Ratio (%)": round(ratios.get('payout_ratio'), 2) if ratios.get('payout_ratio') else "N/A",
                "Passive Income Score": score_data['total_score'],
                "Rating": score_data['rating_category']
            })

    if results:
        res_df = pd.DataFrame(results).sort_values('Passive Income Score', ascending=False)
        st.dataframe(res_df, use_container_width=True)

if __name__ == "__main__":
    show()
