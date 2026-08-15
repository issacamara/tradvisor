"""Main entrypoint for TRADVISOR Streamlit app using st.navigation layout."""
import streamlit as st

st.set_page_config(
    page_title="TRADVISOR - BRVM Dashboard",
    page_icon="📈",
    layout="wide"
)

# Load modern st.navigation multi-page setup
dashboard_page = st.Page("views/1_dashboard.py", title="Dashboard", icon="📈", default=True)
stock_page = st.Page("views/2_stock_analysis.py", title="Stock Analysis", icon="🔎")
technical_page = st.Page("views/3_technical_analysis.py", title="Technical Analysis", icon="📊")
risk_page = st.Page("views/4_risk_management.py", title="Risk Management", icon="💰")
settings_page = st.Page("views/5_settings.py", title="Settings & Diagnostics", icon="⚙️")

pg = st.navigation({
    "Analytics": [dashboard_page, stock_page, technical_page],
    "Portfolio & Config": [risk_page, settings_page]
})

pg.run()
