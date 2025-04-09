import duckdb as db
import pandas as pd
import streamlit as st
import yaml
import numpy as np
from streamlit import columns
import plotly.graph_objects as go
import altair as alt
import os
import trading as tr
from google.cloud import bigquery
from google.oauth2 import service_account
# Load configuration from YAML file

def initialize_bigquery():
    """Initialize BigQuery client with credentials"""
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials)


def create_stock_chart(data, symbol):
    """Create an interactive stock price chart using Plotly"""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data['CLOSE'],
            mode='lines',
            name='Close Price',
            line=dict(color='#1f77b4', width=2)
        )
    )

    fig.update_layout(
        title=f"{symbol} Stock Price History",
        xaxis_title="Date",
        yaxis_title="Price (XOF)",
        template="plotly_white",
        height=400
    )
    return fig


def display_recommendation_metrics(stock_data):
    """Display recommendation metrics in a visually appealing way"""
    cols = st.columns(3)
    metrics = [
        ("Buy", "Buy", "green"),
        ("Keep", "Keep", "blue"),
        ("Sell", "Sell", "red")
    ]

    for (label, col_name, color) in metrics:
        with cols[metrics.index((label, col_name, color))]:
            st.markdown(f"""
                <div class="metric-card">
                    <h3 style="color: {color};">{label}</h3>
                    <h2 style="color: {color};">{stock_data[col_name.capitalize()]:.0%}</h2>
                </div>
            """, unsafe_allow_html=True)
# Cache data for 1 day (86400 seconds)
# @st.cache_data(ttl=86400)
def load_data(environment):
    shares = None
    dividends = None
    bq_dataset = ""
    query1 = f"""
                WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM shares)               
                SELECT * FROM {bq_dataset}shares
                WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                    AND (SELECT max_date FROM latest_date)
                ORDER BY date DESC
            """
    if environment=='on-premise':
        shares = conn.execute(query1).df()
    else:
        project_id = os.environ.get('GCP_PROJECT')
        bq_dataset = f"{project_id}.stocks."
        shares = pd.read_gbq(query1, credentials=client.credentials)

    # query2 = f"SELECT * FROM bonds"
    # query3 = f"SELECT * FROM indices"
    query4 = f"SELECT * FROM dividends WHERE date = (SELECT MAX(CAST(date AS DATE)) FROM dividends)"
    # query5 = f"SELECT * FROM capitalizations"
    #
    # bonds = conn.execute(query2).df()
    # indices = conn.execute(query3).df()
    if environment=='on-premise':
        dividends = conn.execute(query4).df()
    else:
        dividends = pd.read_gbq(query4, credentials=client.credentials)

    # capitalizations = conn.execute(query5).df()

    result = shares.merge(dividends[["SYMBOL","DIVIDEND","PAYMENT_DATE"]], on='SYMBOL', how='left')
    result = tr.get_trading_decisions(result)
    result['ROI'] = result['DIVIDEND'] / result['CLOSE']

    # return shares, bonds, indices, dividends, capitalizations
    return result


env = 'gcp'
if os.environ.get("GOOGLE_CLOUD_PROJECT"):
    client = initialize_bigquery()
else:
    env = 'on-premise'
    conn = db.connect('database/financial_assets.db')

# Streamlit app
st.title("Tradvisor")
# Custom CSS for styling
st.markdown("""
    <style>
    .stTab {background-color: #f0f2f6;padding: 20px;border-radius: 10px;}
    .metric-card {background-color: white;padding: 20px;border-radius: 10px;box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;}
    </style>
""", unsafe_allow_html=True)
# Load and display stock data
shares = load_data(env)

main_container = st.container()
topn = 10
mt1, mt2 = main_container.tabs([f"Stocks Analysis", "Portfolio"])
with (mt1):
    col1, col2 = mt1.columns([2, 1])
    selected_symbol = col2.selectbox(
        "Select Stock Symbol",
        options=shares['SYMBOL'].unique()
    )
    historical_data = shares[shares['SYMBOL']==selected_symbol]
    line_chart = alt.Chart(historical_data.reset_index()).mark_line().encode(
        x=alt.X('DATE:T', title='Date', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('CLOSE:Q', title='Close Price'),
        tooltip=['DATE:T', 'CLOSE:Q']
    ).properties(height=500,width='container',title=f"Price History for {selected_symbol}"
                 ).configure_mark(color='#1f77b4'
                                  ).configure_axis(labelFontSize=12,titleFontSize=14)
    mt1.altair_chart(line_chart, use_container_width=True)

    latest_data = historical_data[historical_data.index == historical_data.index.max()].iloc[0]
    with(col2):
        st.markdown(f"""
                                <div class="metric-card">
                                    <h4>{latest_data['NAME']}</h4>
                                    <h4>Price: {latest_data['CLOSE']:.0f} XOF</h4>
                                    <h4>Dividend: {latest_data['DIVIDEND']:.0f} XOF</h4>
                                    <h4>ROI: {latest_data['ROI']:.2%}</h4>
                                </div>
                            """, unsafe_allow_html=True)
    with col1:
        st.subheader("Latest Recommendations")
        display_recommendation_metrics(latest_data)

    latest = shares[shares.index == shares.index.max()]
    mt1.dataframe(latest.sort_index(ascending=True),use_container_width=True)


