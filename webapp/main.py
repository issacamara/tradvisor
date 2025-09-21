"""
Main Trading Dashboard Application with Authentication
Combines technical analysis with user authentication system
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
from trading import TechnicalIndicatorTrading
from helper import create_gauge_chart, create_signal_pie_chart, create_stock_chart, getBigQueryClient
import os
import duckdb as db
import plotly.express as px
from data_manager import DataManager

from google.cloud import bigquery

# Import custom modules
from database import DatabaseManager
from email_manager import EmailManager
from auth_ui import AuthUI

# from data_manager import DataManager
# from tech_analysis import TechnicalAnalyzer
# from chart_components import ChartComponents

# Configure page
st.set_page_config(
    page_title="Technical Trading Dashboard",
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



# Initialize components
@st.cache_resource
def init_components():
    """Initialize all dashboard components"""
    db_manager = DatabaseManager()
    email_manager = EmailManager()
    auth_ui = AuthUI(db_manager, email_manager)
    # data_manager = DataManager()
    # tech_analyzer = TechnicalAnalyzer()
    # chart_components = ChartComponents()

    return {
        'db': db_manager,
        'email': email_manager,
        'auth_ui': auth_ui,
        # 'data': data_manager,
        # 'analyzer': tech_analyzer,
        # 'charts': chart_components
    }

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
    weekly_stats.columns = ['START_PRICE', 'PRICE', 'NAME', 'LATEST_VOLUME']
    weekly_stats = weekly_stats.reset_index()

    # Vectorized calculation of weekly returns
    with np.errstate(divide='ignore', invalid='ignore'):  # Handle potential division by zero
        weekly_returns = ((weekly_stats['PRICE'] - weekly_stats['START_PRICE']) /
                          weekly_stats['START_PRICE'])

    weekly_stats['GROWTH'] = weekly_returns

    # Remove invalid returns (inf, -inf, nan)
    weekly_stats = weekly_stats[np.isfinite(weekly_stats['GROWTH'])]

    if weekly_stats.empty:
        return pd.DataFrame(
            columns=['SYMBOL', 'NAME', 'PRICE', 'GROWTH', 'LATEST_VOLUME'])

    # Use numpy argsort for faster top-k selection
    returns = weekly_stats['GROWTH'].values
    if len(returns) <= 10:
        top_10_indices = np.argsort(-returns)
    else:
        top_10_indices = np.argpartition(-returns, 10)[:10]
        top_10_indices = top_10_indices[np.argsort(-returns[top_10_indices])]

    result = weekly_stats.iloc[top_10_indices][
        ['SYMBOL', 'NAME', 'PRICE', 'GROWTH', 'LATEST_VOLUME']].copy()

    return result.reset_index(drop=True)


def apply_custom_css():
    """Apply custom CSS styling"""
    st.markdown("""
    <style>
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Custom metric styling */
    div[data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e1e5e9;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* Success/Error message styling */
    .stAlert {
        border-radius: 10px;
        border-left: 4px solid;
        font-weight: 500;
    }

    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    /* Form styling */
    .stForm {
        border: 1px solid #e1e5e9;
        border-radius: 15px;
        padding: 2rem;
        background-color: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #2c3e50, #3498db);
        color: white;
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

def show_authentication_flow(components):
    """Handle authentication flow"""
    auth_ui = components['auth_ui']

    if st.session_state.get('show_register', False):
        auth_ui.show_register_page()
    else:
        auth_ui.show_login_page()

def show_main_dashboard(components, user):
    """Show the main trading dashboard"""
    auth_ui = components['auth_ui']
    # data_manager = components['data']
    # analyzer = components['analyzer']
    # chart_components = components['charts']

    # Show user profile in sidebar
    auth_ui.show_user_profile(user)

    # Main dashboard header
    st.markdown("""
    <div class="main-header">
        <h1 style="margin:0;">Trading Dashboard</h1>
    </div>
    """, unsafe_allow_html=True)

    # Main header
    st.markdown('<div class="main-header">Trading Advisor</div>', unsafe_allow_html=True)

    # Load and display stock data
    dm = DataManager()
    shares = dm.load_data()

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

        st.markdown(f"""<h3 style='text-align: center; color: black;'>{selected_symbol} Price </h4>""",
                    unsafe_allow_html=True)

        fig_price = px.line(
            historical_data,
            x='DATE',
            y='CLOSE',
            title=f' ',
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
        st.markdown("---")
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
            # st.markdown("### :green[Top 10 Profitable Stocks]")
            st.markdown("<h4 style='text-align: center; color: green;'>Top 10 Profitable Stocks</h4>",
                        unsafe_allow_html=True)
            top_roi = top10_by_roi(shares).style.format({'ROI': '{:.2%}', 'CLOSE': '{:.0f}', 'VOLUME': '{:.0f}'})

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
            st.markdown("<h4 style='text-align: center; color: green;'>Top 10 Weekly Performers</h4>",
                        unsafe_allow_html=True)

            # Apply percentage formatting using pandas styling
            top_weekly = top10_weekly_performers(shares).style.format({'GROWTH': '{:.2%}', 'PRICE': '{:.0f}',
                                                                       'LATEST_VOLUME': '{:.0f}'})

            st.dataframe(
                top_weekly,
                use_container_width=True,
                hide_index=True
            )

        # main_container.dataframe(top_roi)
        # main_container.dataframe(top_weekly)

        # main_container.dataframe(shares[shares['SYMBOL'] == selected_symbol])


def main():
    """Main application entry point"""

    apply_custom_css()
    components = init_components()

    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None

    if st.session_state.authenticated and st.session_state.user:
        show_main_dashboard(components, st.session_state.user)
    else:
        show_authentication_flow(components)

    if st.session_state.authenticated:
        st.markdown("---")
        st.markdown("Powered by:** Bayesian Ensemble Technical Analysis | **Data Source:** BRVM")

if __name__ == "__main__":
    main()