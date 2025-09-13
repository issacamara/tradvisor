import duckdb as db
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import os
import pandas as pd
import numpy as np
from streamlit import sidebar

from trading2 import TechnicalIndicatorTrading
from google.cloud import bigquery
from helper import create_gauge_chart, create_signal_pie_chart, create_stock_chart
import json
from google.oauth2 import service_account


# Load configuration from YAML file

def getBigQueryClient():
    """Initialize BigQuery client with credentials"""
    # credentials = service_account.Credentials.from_service_account_info(
    #     st.secrets["gcp_service_account"]
    # )
    # return bigquery.Client(credentials=credentials)
    if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
        creds_dict = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
        with open("key.json", "w") as f:
            json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

    return bigquery.Client()


# Cache data for 1 day (86400 seconds)
@st.cache_data(ttl=86400)
def load_data():
    shares = None
    dividends = None
    trading_system = TechnicalIndicatorTrading()
    # query1 = f"""
    #             WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM `{dataset_names[ENVIRONMENT]}SHARES`)
    #             SELECT * FROM `{dataset_names[ENVIRONMENT]}SHARES`
    #             WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
    #                 AND (SELECT max_date FROM latest_date)
    #             ORDER BY date DESC
    #         """

    query1onprem = f"""
                WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM {dataset_names[ENVIRONMENT]}SHARES)
                SELECT * FROM {dataset_names[ENVIRONMENT]}SHARES
                WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                    AND (SELECT max_date FROM latest_date)
                ORDER BY date DESC
            """
    query1 = query1onprem

    # query2 = f"SELECT * FROM bonds"
    # query3 = f"SELECT * FROM indices"
    # query4 = f"""
    #             SELECT * FROM `{dataset_names[ENVIRONMENT]}DIVIDENDS`
    #             WHERE DATE(date) = (SELECT MAX(DATE(date)) FROM `{dataset_names[ENVIRONMENT]}DIVIDENDS`)
    #         """
    query4onPrem = f"""
                SELECT * FROM {dataset_names[ENVIRONMENT]}DIVIDENDS
                WHERE CAST(date as DATE) = (SELECT MAX(CAST(date as DATE)) FROM {dataset_names[ENVIRONMENT]}DIVIDENDS)
            """
    query4 = query4onPrem
    # query5 = f"SELECT * FROM capitalizations"
    if ENVIRONMENT == 'on-premise':
        shares = conn.execute(query1).df()
        dividends = conn.execute(query4).df()
    else:
        # client = initialize_bigquery()

        shares = client.query(query1).to_dataframe()
        dividends = client.query(query4).to_dataframe()

    #
    # bonds = conn.execute(query2).df()
    # indices = conn.execute(query3).df()

    # capitalizations = conn.execute(query5).df()

    result = shares.merge(dividends[["SYMBOL", "DIVIDEND", "PAYMENT_DATE"]], on='SYMBOL', how='left')
    # result = tr.get_trading_decisions(result)
    result = trading_system.generate_signals(result, adaptive_weights=True)
    result['ROI'] = result['DIVIDEND'] / result['CLOSE']

    # return shares, bonds, indices, dividends, capitalizations
    return result


# Cache data for 1 day (86400 seconds)
@st.cache_data(ttl=86400)
def top10_by_roi(df):
    # Find max date using numpy for speed (avoid pandas max() overhead)
    dates = pd.to_datetime(df['DATE'].values)
    latest_date = dates.max()

    # Use boolean indexing with numpy comparison (faster than pandas query)
    mask = dates == latest_date
    latest = df[mask]

    # Use numpy argsort for faster sorting, then take top 10
    roi_values = latest['ROI'].values
    top_10_indices = np.argpartition(-roi_values, 10)[:10]  # Partial sort for top 10
    top_10_indices = top_10_indices[np.argsort(-roi_values[top_10_indices])]  # Sort the top 10

    result = latest.iloc[top_10_indices][['SYMBOL', 'NAME', 'ROI', 'CLOSE', 'VOLUME']].copy()

    return result.reset_index(drop=True)


# Cache data for 1 day (86400 seconds)
@st.cache_data(ttl=86400)
def top10_weekly_performers(df):
    # Convert dates once and find date range
    dates = pd.to_datetime(df['DATE'].values)
    latest_date = dates.max()
    week_ago = latest_date - pd.Timedelta(days=7)

    # Filter for weekly data using boolean indexing
    weekly_mask = dates >= week_ago
    weekly_data = df[weekly_mask].copy()
    weekly_data['DATE'] = dates[weekly_mask]

    # Sort by SYMBOL and DATE for efficient groupby operations
    weekly_data = weekly_data.sort_values(['SYMBOL', 'DATE'])

    # Use groupby with agg for vectorized operations
    weekly_stats = weekly_data.groupby('SYMBOL').agg({
        'CLOSE': ['first', 'last'],
        'NAME': 'last',
        'VOLUME': 'last'
    })

    # Flatten column names
    weekly_stats.columns = ['START_PRICE', 'END_PRICE', 'NAME', 'LATEST_VOLUME']
    weekly_stats = weekly_stats.reset_index()

    # Vectorized calculation of weekly returns
    with np.errstate(divide='ignore', invalid='ignore'):  # Handle potential division by zero
        weekly_returns = ((weekly_stats['END_PRICE'] - weekly_stats['START_PRICE']) /
                          weekly_stats['START_PRICE'])

    weekly_stats['WEEKLY_VARIATION'] = weekly_returns

    # Remove invalid returns (inf, -inf, nan)
    weekly_stats = weekly_stats[np.isfinite(weekly_stats['WEEKLY_VARIATION'])]

    if weekly_stats.empty:
        return pd.DataFrame(
            columns=['SYMBOL', 'NAME', 'START_PRICE', 'END_PRICE', 'WEEKLY_VARIATION', 'LATEST_VOLUME'])

    # Use numpy argsort for faster top-k selection
    returns = weekly_stats['WEEKLY_VARIATION'].values
    if len(returns) <= 10:
        top_10_indices = np.argsort(-returns)
    else:
        top_10_indices = np.argpartition(-returns, 10)[:10]
        top_10_indices = top_10_indices[np.argsort(-returns[top_10_indices])]

    result = weekly_stats.iloc[top_10_indices][
        ['SYMBOL', 'NAME', 'START_PRICE', 'END_PRICE', 'WEEKLY_VARIATION', 'LATEST_VOLUME']].copy()

    return result.reset_index(drop=True)

# Page config
st.set_page_config(
    page_title="TRADVISOR",
    page_icon="ðŸ“ˆ",
    layout="wide",
    initial_sidebar_state="expanded"
)

ENVIRONMENT = 'gcp'
project_id = os.environ.get('PROJECT_ID')
# project_id = "dev-tradvisor"

client = None
if project_id:
    client = getBigQueryClient()
else:
    ENVIRONMENT = 'on-premise'
    conn = db.connect('database/financial_assets.db')

dataset_names = {"on-premise": "", "gcp": f"{project_id}.stocks."}

# Streamlit app
# Custom CSS for styling
# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 2rem;
        padding: 1rem;
        background: linear-gradient(90deg, #f0f9ff, #e0f2fe);
        border-radius: 10px;
    }
    .metric-container {
        background-color: #f8fafc;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #3b82f6;
        margin: 0.5rem 0;
    }
    .sidebar-header {
        font-size: 1.2rem;
        font-weight: bold;
        color: #1f2937;
        margin-bottom: 1rem;
    }
    .confidence-high { color: #16a34a; font-weight: bold; }
    .confidence-medium { color: #f59e0b; font-weight: bold; }
    .confidence-low { color: #dc2626; font-weight: bold; }
</style>
""", unsafe_allow_html=True)
# Main header
st.markdown('<div class="main-header">Trading Advisor</div>', unsafe_allow_html=True)

# Load and display stock data
shares = load_data()

main_container = st.container()

st.sidebar.markdown('<div class="sidebar-header">Choose the stock</div>', unsafe_allow_html=True)
selected_symbol = st.sidebar.selectbox("",
                                       options=shares['SYMBOL'].unique())

historical_data = shares[shares['SYMBOL'] == selected_symbol].sort_index()
latest_data = historical_data[historical_data.index == historical_data.index.max()].iloc[0]

st.sidebar.markdown(f"""
                        <div class="metric-card">
                            <h4>{latest_data['NAME']}</h4>
                            <h4>Price: {latest_data['CLOSE']:.0f} XOF</h4>
                            <h4>Dividend: {latest_data['DIVIDEND']:.0f} XOF</h4>
                            <h4>ROI: {latest_data['ROI']:.2%}</h4>
                        </div>
                    """, unsafe_allow_html=True)

with (main_container):
    # Component - Stock chart

    st.markdown("### Stock Price History")

    fig_price = px.line(
        historical_data,
        x='DATE',
        y='CLOSE',
        title=f'{selected_symbol} Stock Price Over Time',
        template='plotly_white'
    )

    fig_price.update_layout(
        title_font_size=16,
        height=400,
        showlegend=False
    )

    fig_price.update_traces(
        line=dict(color='#3b82f6', width=2),
        hovertemplate='<b>Date:</b> %{x}<br><b>Price:</b> $%{y:.2f}<extra></extra>'
    )
    st.plotly_chart(fig_price, use_container_width=True)


    col2, col1 = main_container.columns([1, 1])

    with col1:
        # col1.subheader("Trading Signal")
        st.markdown("<h4 style='text-align: center;'>Trading Signal</h2>", unsafe_allow_html=True)
        # Component 2 - Stock Price Chart
        # st.markdown("### Trading Signal")
        # Signal probabilities
        pie_fig = create_signal_pie_chart(latest_data[['BUY', 'KEEP', 'SELL']].to_dict())
        col1.plotly_chart(pie_fig, use_container_width=True)
        # display_recommendation_metrics(latest_data)

    with(col2):

        # Component - Confidence Gauge
        st.markdown("<h4 style='text-align: center;'>Confidence Level</h2>", unsafe_allow_html=True)

        gauge_fig = create_gauge_chart(latest_data['CONFIDENCE'], "")

        # col_gauge1, col_gauge2, col_gauge3 = st.columns([1, 2, 1])
        # with col_gauge2:
        st.plotly_chart(gauge_fig, use_container_width=True)
        st.markdown(f'<div class="conf_class" style="text-align: center; font-size: 1.2rem;">conf_text</div>',
                        unsafe_allow_html=True)

    # Components - Performance Tables
    st.markdown("---")
    col_table1, col_table2 = st.columns(2)
    with col_table1:
        st.markdown("### Top 10 Profitable Stocks")
        top_roi = top10_by_roi(shares).style.format({'ROI': '{:.2%}'})

        st.dataframe(
            top_roi,
            use_container_width=True,
            hide_index=True,
            column_config={
                "SYMBOL": st.column_config.TextColumn("SYMBOL", width="small"),
                "CLOSE": st.column_config.TextColumn("PRICE", width="small"),
                "ROI": st.column_config.TextColumn("ROI", width="small"),
                "VOLUME": st.column_config.TextColumn("VOLUME", width="medium"),
            }
        )
    with col_table2:
        st.markdown("### Top 10 Weekly Performers")
        # Apply percentage formatting using pandas styling
        top_weekly = top10_weekly_performers(shares).style.format({'WEEKLY_VARIATION': '{:.2%}'})

        # Format the dataframe for display
        # top_roi_display = top_roi[['Symbol', 'Current Price', 'ROI (%)', 'YTD Return (%)', 'Market Cap']].copy()
        # top_roi_display['Current Price'] = top_roi_display['Current Price'].apply(lambda x: f"${x:.2f}")
        # top_roi_display['ROI (%)'] = top_roi_display['ROI (%)'].apply(lambda x: f"{x:.2f}%")
        # top_roi_display['YTD Return (%)'] = top_roi_display['YTD Return (%)'].apply(lambda x: f"{x:.2f}%")

        st.dataframe(
            top_weekly,
            use_container_width=True,
            hide_index=True
        )

    # main_container.dataframe(top_roi)
    # main_container.dataframe(top_weekly)

    # main_container.dataframe(shares[shares['SYMBOL'] == selected_symbol])
