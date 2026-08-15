"""View 3: Technical Analysis & 10 TA Indicator Deep Dive."""
import streamlit as st
import pandas as pd
from app.data.repository import get_all_symbols, get_stock_price_history
from app.core.signals.technical import calculate_technical_indicators, generate_technical_signal_consensus
from app.components.charts import render_candlestick_chart, render_rsi_macd_chart

def show():
    st.title("📊 Technical Analysis Deep-Dive")

    symbols = get_all_symbols()
    if not symbols:
        st.warning("No stock symbols found.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_symbol = st.selectbox("Select Stock for TA", options=symbols, index=0)
    with col2:
        days = st.slider("Historical Days", min_value=60, max_value=1800, value=365, step=30)

    price_df = get_stock_price_history(selected_symbol, days=days)

    if price_df.empty:
        st.warning(f"No price history found for {selected_symbol}.")
        return

    ta_df = calculate_technical_indicators(price_df)
    consensus = generate_technical_signal_consensus(ta_df)

    st.subheader(f"Signal Consensus: :{ 'green' if 'BUY' in consensus['signal'] else 'red' if 'SELL' in consensus['signal'] else 'orange' }[{consensus['signal']}]")

    st.plotly_chart(render_candlestick_chart(ta_df, selected_symbol), use_container_width=True)
    st.plotly_chart(render_rsi_macd_chart(ta_df), use_container_width=True)

    with st.expander("Indicator Data Table"):
        st.dataframe(ta_df.tail(30), use_container_width=True)

if __name__ == "__main__":
    show()
