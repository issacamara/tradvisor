"""View 2: Fundamental Stock Analysis and 5-Year Financial Trends."""
import streamlit as st
import pandas as pd
from app.data.repository import get_all_symbols, get_latest_prices, get_stock_financials, get_stock_dividends, get_stock_ratings, get_all_companies
from app.core.fundamental.analyzer import calculate_fundamental_ratios
from app.core.signals.passive_income import calculate_passive_income_score
from app.components.charts import render_financial_bar_chart
from app.components.metrics import render_score_badge

# def show():
#     st.title("🔎 Stock Fundamental Analysis")
    
#     symbols = get_all_symbols()
#     if not symbols:
#         st.warning("No stock symbols found in BigQuery database.")
#         return

#     selected_symbol = st.selectbox("Select BRVM Stock Symbol", options=symbols, index=0)

#     prices_df = get_latest_prices().set_index('SYMBOL') if not get_latest_prices().empty else pd.DataFrame()
#     latest_close = float(prices_df.loc[selected_symbol, 'CLOSE']) if (not prices_df.empty and selected_symbol in prices_df.index) else None

#     fin_df = get_stock_financials(selected_symbol)
#     div_df = get_stock_dividends(selected_symbol)
#     ratings_df = get_stock_ratings(selected_symbol)

#     latest_div = float(div_df.iloc[0]['dividend']) if not div_df.empty and 'dividend' in div_df.columns else None
#     ratios = calculate_fundamental_ratios(fin_df, latest_close=latest_close, latest_dividend=latest_div)
#     score_data = calculate_passive_income_score(
#         div_yield=ratios.get('dividend_yield'),
#         payout_ratio=ratios.get('payout_ratio'),
#         debt_to_equity=ratios.get('debt_to_equity'),
#         roe=ratios.get('roe'),
#         years_with_div=len(div_df)
#     )

#     c1, c2, c3 = st.columns([1, 1, 1])
#     with c1:
#         st.metric("Latest Close Price", f"{latest_close:,.0f} XOF" if latest_close else "N/A")
#     with c2:
#         st.metric("Dividend Yield", f"{ratios.get('dividend_yield'):.2f}%" if ratios.get('dividend_yield') else "N/A")
#     with c3:
#         render_score_badge(score_data['total_score'], score_data['rating_category'])

#     st.subheader("📊 5-Year Financial Performance")
#     if not fin_df.empty:
#         st.plotly_chart(render_financial_bar_chart(fin_df, selected_symbol), use_container_width=True)
#         st.dataframe(fin_df, use_container_width=True)
#     else:
#         st.info("No financial statements available for this symbol.")

#     if not ratings_df.empty:
#         st.subheader("⭐ Credit Ratings")
#         st.table(ratings_df)

def show():
  symbols = get_all_symbols()  #[cite: 30, 32]
  if not symbols:
    st.error('No stock symbols found in BigQuery.')
    return

  company_names = get_all_companies()

  selected_symbol = st.selectbox('Select Stock Symbol', options=symbols)

  # 5. Retrieve and Display Company Name
  company_name = company_names.get(selected_symbol, '')

  if company_name:
    st.title(f'🔎 {company_name} ({selected_symbol})')
  else:
    st.title(f'🔎 {selected_symbol} - Stock Analysis')

  # Fetch Data from Repository
  df_fin = get_stock_financials(selected_symbol)  #[cite: 30, 32]
  df_price = get_stock_price_history(selected_symbol)  #[cite: 30]
  df_div = get_stock_dividends(selected_symbol)  #[cite: 30, 32]

  # Key Financial Metrics Summary Cards (FCFA / XOF Standardized)
  if not df_fin.empty:
    latest = df_fin.iloc[0]
    col1, col2, col3, col4 = st.columns(4)

    net_inc = latest.get('net_income')
    debt = latest.get('total_debt')
    cash = latest.get('cash_and_cash_equivalents')
    equity = latest.get('total_equity')

    col1.metric(
        'Net Income',
        f"{net_inc:,.0f} FCFA" if pd.notnull(net_inc) else 'N/A',
    )
    col2.metric(
        'Total Debt', f"{debt:,.0f} FCFA" if pd.notnull(debt) else 'N/A'
    )
    col3.metric(
        'Cash & Cash Eq.', f"{cash:,.0f} FCFA" if pd.notnull(cash) else 'N/A'
    )
    col4.metric(
        'Total Equity',
        f"{equity:,.0f} FCFA" if pd.notnull(equity) else 'N/A',
    )

  st.divider()

  # 1, 2, 3. Render Updated Grouped Financial Bar Chart
  st.subheader('📊 Financial Statement Trends')
  if not df_fin.empty:
    fig_fin = render_financial_bar_chart(
        df_fin, selected_symbol, company_name=company_name
    )
    st.plotly_chart(fig_fin, use_container_width=True)
  else:
    st.info('No financial statement history available for this symbol.')

if __name__ == "__main__":
    show()
