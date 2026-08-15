"""View 4: Risk Management, Stop-loss & Position Sizing Calculator."""
import streamlit as st
from app.data.repository import get_all_symbols, get_stock_price_history
from app.core.risk.manager import calculate_atr, calculate_position_size

def show():
    st.title("💰 Risk Management & Position Calculator")

    symbols = get_all_symbols()
    col1, col2 = st.columns(2)

    with col1:
        portfolio_eur = st.number_input("Portfolio Size (EUR)", min_value=1000.0, value=100000.0, step=5000.0)
        risk_pct = st.slider("Max Risk per Trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.5)

    with col2:
        selected_symbol = st.selectbox("Target Stock Symbol", options=symbols) if symbols else "NTLC"
        entry_price = st.number_input("Entry Price (XOF)", min_value=100.0, value=5000.0, step=100.0)

    price_df = get_stock_price_history(selected_symbol, days=90) if symbols else None
    atr_val = calculate_atr(price_df) if price_df is not None and not price_df.empty else None

    st.subheader("🛡️ Stop-Loss Strategy")
    st_col1, st_col2 = st.columns(2)

    with st_col1:
        if atr_val:
            st.info(f"14-Day ATR for {selected_symbol}: **{atr_val:.2f} XOF**")
            multiplier = st.slider("ATR Multiplier (k)", min_value=1.0, max_value=3.0, value=2.0, step=0.5)
            atr_stop_loss = entry_price - (multiplier * atr_val)
            st.write(f"Recommended ATR Stop-Loss: **{atr_stop_loss:.2f} XOF**")
        else:
            atr_stop_loss = entry_price * 0.95

    with st_col2:
        stop_loss_choice = st.number_input("Selected Stop-Loss Price (XOF)", min_value=50.0, value=float(atr_stop_loss), step=50.0)

    res = calculate_position_size(portfolio_value_eur=portfolio_eur, risk_pct=risk_pct, entry_price_xof=entry_price, stop_loss_xof=stop_loss_choice)

    if "error" in res:
        st.error(res["error"])
    else:
        st.subheader("📊 Position Sizing Recommendation")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Shares to Buy", f"{res['shares_to_buy']:,} units")
        r2.metric("Total Position (EUR)", f"€{res['total_cost_eur']:,.2f}")
        r3.metric("Max Capital at Risk", f"€{res['max_risk_eur']:,.2f}")
        r4.metric("Portfolio Allocation", f"{res['portfolio_pct']:.2f}%")

if __name__ == "__main__":
    show()
