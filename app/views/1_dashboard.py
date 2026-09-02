"""View 1: Dashboard overview of BRVM stock signals and passive income opportunities."""
import streamlit as st
import pandas as pd
from app.data.repository import (
    get_all_symbols,
    get_all_companies,
    get_latest_prices,
    get_stock_financials,
    get_stock_dividends,
    get_stock_price_history,
    get_all_companies_with_sector,
)
from app.core.fundamental.analyzer import calculate_fundamental_ratios
from app.core.signals.passive_income import calculate_passive_income_score
from app.core.signals.checklist import analyze_checklist, render_checklist_results
from app.components.metrics import render_score_badge


def show():
    st.title("📈 TRADVISOR Dashboard")
    st.caption("BRVM Dividend Ranking & Market Signals Overview")

    # Toggle between Passive Income and Checklist views
    view_mode = st.radio(
        "Select View:",
        ["Passive Income Ranking", "Long-Term Checklist"],
        horizontal=True,
    )

    if view_mode == "Passive Income Ranking":
        _render_passive_income_view()
    else:
        _render_checklist_view()


def _render_passive_income_view():
    """Render the passive income ranking view."""
    st.subheader("💰 Top Passive Income Opportunities (BRVM)")

    symbols = get_all_symbols()
    prices_df = (
        get_latest_prices().set_index("symbol")
        if not get_latest_prices().empty
        else pd.DataFrame()
    )
    
    # Get company names
    companies_dict = get_all_companies()

    results = []
    with st.spinner("Analyzing stocks for passive income signals..."):
        for sym in symbols:
            fin_df = get_stock_financials(sym)
            div_df = get_stock_dividends(sym)

            latest_price = (
                float(prices_df.loc[sym, "close"])
                if (not prices_df.empty and sym in prices_df.index)
                else None
            )
            latest_div = (
                float(div_df.iloc[0]["dividend"])
                if not div_df.empty and "dividend" in div_df.columns
                else None
            )
            years_div = len(div_df) if not div_df.empty else 0

            ratios = calculate_fundamental_ratios(
                fin_df, latest_close=latest_price, latest_dividend=latest_div
            )
            score_data = calculate_passive_income_score(
                div_yield=ratios.get("dividend_yield"),
                payout_ratio=ratios.get("payout_ratio"),
                debt_to_equity=ratios.get("debt_to_equity"),
                roe=ratios.get("roe"),
                years_with_div=years_div,
            )

            results.append(
                {
                    "Symbol": sym,
                    "Company": companies_dict.get(sym, "N/A"),
                    "Close Price (XOF)": latest_price,
                    "Dividend Yield (%)": (
                        round(ratios.get("dividend_yield"), 2)
                        if ratios.get("dividend_yield")
                        else "N/A"
                    ),
                    "ROE (%)": (
                        round(ratios.get("roe"), 2) if ratios.get("roe") else "N/A"
                    ),
                    "Payout Ratio (%)": (
                        round(ratios.get("payout_ratio"), 2)
                        if ratios.get("payout_ratio")
                        else "N/A"
                    ),
                    "Passive Income Score": score_data["total_score"],
                    "Rating": score_data["rating_category"],
                }
            )

    if results:
        res_df = pd.DataFrame(results).sort_values(
            "Passive Income Score", ascending=False
        )
        # Reorder columns to put Company after Symbol
        cols = ["Symbol", "Company", "Close Price (XOF)", "Dividend Yield (%)", "ROE (%)", "Payout Ratio (%)", "Passive Income Score", "Rating"]
        res_df = res_df[cols]
        st.dataframe(res_df, use_container_width=True)


def _render_checklist_view():
    """Render the long-term investment checklist view."""
    st.subheader("✅ BRVM Long-Term Stock Checklist")
    st.caption("9-category scoring system (45 points max)")

    symbols = get_all_symbols()
    if not symbols:
        st.warning("No stock symbols found in BigQuery.")
        return

    # Get company sector data
    companies_df = get_all_companies_with_sector()
    companies_sector = (
        companies_df.set_index("symbol")["sector"].to_dict()
        if not companies_df.empty
        else {}
    )
    
    # Get company names
    companies_dict = get_all_companies()

    # Get latest prices
    prices_df = (
        get_latest_prices().set_index("symbol")
        if not get_latest_prices().empty
        else pd.DataFrame()
    )

    # Analyze all stocks
    results = []
    with st.spinner("Analyzing stocks with BRVM checklist..."):
        for sym in symbols:
            fin_df = get_stock_financials(sym)
            div_df = get_stock_dividends(sym)
            price_df = get_stock_price_history(sym, days=180)

            latest_price = (
                float(prices_df.loc[sym, "close"])
                if (not prices_df.empty and sym in prices_df.index)
                else None
            )

            sector = companies_sector.get(sym)

            checklist_result = analyze_checklist(
                df_fin=fin_df,
                df_div=div_df,
                df_price=price_df,
                latest_price=latest_price,
                sector=sector,
            )

            results.append(
                {
                    "Symbol": sym,
                    "Company": companies_dict.get(sym, "N/A"),
                    "Sector": sector if sector else "Unknown",
                    "Close Price (XOF)": latest_price,
                    "Checklist Score": checklist_result["total_score"],
                    "Rating": checklist_result["rating"],
                    "_checklist_result": checklist_result,  # Store for detail view
                }
            )

    if not results:
        st.warning("No analysis results available.")
        return

    # Sort by checklist score
    res_df = pd.DataFrame(results).sort_values("Checklist Score", ascending=False)

    # Display summary table
    display_df = res_df[["Symbol", "Company", "Sector", "Close Price (XOF)", "Checklist Score", "Rating"]].copy()
    st.dataframe(display_df, use_container_width=True)

    # Allow user to select a stock for detailed checklist
    st.divider()
    st.subheader("🔍 Detailed Checklist Analysis")

    selected_symbol = st.selectbox(
        "Select a stock to view detailed checklist:",
        options=res_df["Symbol"].tolist(),
    )

    # Find the selected stock's result
    selected_result = next(
        (r for r in results if r["Symbol"] == selected_symbol), None
    )

    if selected_result:
        checklist = selected_result["_checklist_result"]

        # Display stock info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Symbol", selected_symbol)
        with col2:
            st.metric("Company", selected_result["Company"])
        with col3:
            st.metric("Sector", selected_result["Sector"])
        with col4:
            st.metric(
                "Price",
                f"{selected_result['Close Price (XOF)']:,.0f} XOF"
                if selected_result["Close Price (XOF)"]
                else "N/A",
            )

        # Render checklist results
        render_checklist_results(checklist)

        # Show score breakdown explanation
        with st.expander("📋 Score Breakdown Explanation"):
            st.markdown("""
            | Category | Score | Description |
            |----------|-------|-------------|
            | **Business Quality** | 1-5 | Based on sector (defensive vs cyclical) |
            | **Revenue Trend** | 1-5 | 3-5 year revenue CAGR and consistency |
            | **Profitability** | 1-5 | Net income level and margin trend |
            | **Balance Sheet** | 1-5 | Debt/equity ratio and cash coverage |
            | **Dividend Quality** | 1-5 | Years of dividends and payout ratio |
            | **Valuation** | 1-5 | Based on dividend yield (simplified) |
            | **Liquidity** | 1-5 | Average trading volume (90 days) |
            | **Risk Factors** | 1-5 | Debt levels and sector risk |
            | **Long-Term Fit** | 1-5 | Dividend history and fundamentals |

            **Rating Interpretation:**
            - **40-45**: Very Strong Candidate
            - **30-39**: Interesting - Use Caution
            - **20-29**: Weak / Average
            - **Below 20**: Avoid
            """)


if __name__ == "__main__":
    show()
