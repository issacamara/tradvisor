"""
Page 1: Dashboard Overview
Displays stock overview, trading signals, and top performers
"""

# DEBUG: Immediate import check - stderr for Cloud Run logs
import os
import sys
print(f"[DEBUG] 1_Dashboard.py loaded, PROJECT_ID={os.environ.get('PROJECT_ID', 'NOT SET')}", file=sys.stderr, flush=True)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

from data_manager import DataManager
from helper import create_gauge_chart, create_signal_pie_chart
from core.fundamental.analyzer import get_financial_summary, get_rating_summary


def apply_page_css():
    """Apply page-specific CSS"""
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #2c3e50, #3498db);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin-bottom: 1.5rem;
        text-align: center;
    }
    .metric-card {
        background-color: white;
        border: 1px solid #e1e5e9;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .sidebar-header {
        font-size: 1.2rem;
        font-weight: bold;
        color: #1f2937;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)


@st.cache_data(ttl=86400)
def top10_by_roi(df: pd.DataFrame) -> pd.DataFrame:
    """Get top 10 stocks by ROI (dividend yield)"""
    dates = pd.to_datetime(df['date'].values)
    latest_date = dates.max()
    mask = dates == latest_date
    latest = df[mask]
    
    roi_values = latest['roi'].values
    top_10_indices = np.argpartition(-roi_values, 10)[:10]
    top_10_indices = top_10_indices[np.argsort(-roi_values[top_10_indices])]
    
    return latest.iloc[top_10_indices][['symbol', 'name', 'roi', 'close', 'volume']].copy().reset_index(drop=True)


@st.cache_data(ttl=86400)
def top10_weekly_performers(df: pd.DataFrame) -> pd.DataFrame:
    """Get top 10 weekly performing stocks"""
    dates = pd.to_datetime(df['date'].values)
    latest_date = dates.max()
    week_ago = latest_date - pd.Timedelta(days=7)
    
    weekly_mask = dates >= week_ago
    weekly_data = df[weekly_mask].copy()
    weekly_data['date'] = dates[weekly_mask]
    weekly_data = weekly_data.sort_values(['symbol', 'date'])
    
    weekly_stats = weekly_data.groupby('symbol').agg({
        'close': ['first', 'last'],
        'name': 'last',
        'volume': 'last'
    })
    weekly_stats.columns = ['start_price', 'price', 'name', 'latest_volume']
    weekly_stats = weekly_stats.reset_index()
    
    with np.errstate(divide='ignore', invalid='ignore'):
        weekly_returns = ((weekly_stats['price'] - weekly_stats['start_price']) / weekly_stats['start_price'])
    
    weekly_stats['growth'] = weekly_returns
    weekly_stats = weekly_stats[np.isfinite(weekly_stats['growth'])]
    
    if weekly_stats.empty:
        return pd.DataFrame(columns=['symbol', 'name', 'price', 'growth', 'latest_volume'])
    
    returns = weekly_stats['growth'].values
    if len(returns) <= 10:
        top_10_indices = np.argsort(-returns)
    else:
        top_10_indices = np.argpartition(-returns, 10)[:10]
        top_10_indices = top_10_indices[np.argsort(-returns[top_10_indices])]
    
    return weekly_stats.iloc[top_10_indices][['symbol', 'name', 'price', 'growth', 'latest_volume']].copy().reset_index(drop=True)


@st.cache_data(ttl=86400)
def bottom10_weekly_performers(df: pd.DataFrame) -> pd.DataFrame:
    """Get bottom 10 weekly performing stocks"""
    dates = pd.to_datetime(df['date'].values)
    latest_date = dates.max()
    week_ago = latest_date - pd.Timedelta(days=7)
    
    weekly_mask = dates >= week_ago
    weekly_data = df[weekly_mask].copy()
    weekly_data['date'] = dates[weekly_mask]
    weekly_data = weekly_data.sort_values(['symbol', 'date'])
    
    weekly_stats = weekly_data.groupby('symbol').agg({
        'close': ['first', 'last'],
        'name': 'last',
        'volume': 'last'
    })
    weekly_stats.columns = ['start_price', 'price', 'name', 'latest_volume']
    weekly_stats = weekly_stats.reset_index()
    
    with np.errstate(divide='ignore', invalid='ignore'):
        weekly_returns = ((weekly_stats['price'] - weekly_stats['start_price']) / weekly_stats['start_price'])
    
    weekly_stats['growth'] = weekly_returns
    weekly_stats = weekly_stats[np.isfinite(weekly_stats['growth'])]
    
    if weekly_stats.empty:
        return pd.DataFrame(columns=['symbol', 'name', 'price', 'growth', 'latest_volume'])
    
    returns = weekly_stats['growth'].values
    if len(returns) <= 10:
        bottom_10_indices = np.argsort(returns)
    else:
        bottom_10_indices = np.argpartition(returns, 10)[:10]
        bottom_10_indices = bottom_10_indices[np.argsort(returns[bottom_10_indices])]
    
    return weekly_stats.iloc[bottom_10_indices][['symbol', 'name', 'price', 'growth', 'latest_volume']].copy().reset_index(drop=True)


def show():
    """Render the Dashboard page"""
    # ULTRA EARLY DEBUG - should show even if imports fail
    import os
    import sys
    print(f"[DEBUG] show() function called", file=sys.stderr, flush=True)
    
    st.markdown("### 🚨 DEBUG: Page loaded!")
    st.write(f"PROJECT_ID env: {os.environ.get('PROJECT_ID', 'NOT SET')}")
    st.write(f"Python path check...")
    
    apply_page_css()
    
    # Page header
    st.markdown('<div class="main-header">Trading Dashboard</div>', unsafe_allow_html=True)
    
    # DEBUG: Check environment
    import os
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Debug Info")
    st.sidebar.write(f"PROJECT_ID: {os.environ.get('PROJECT_ID', 'NOT SET')}")
    st.sidebar.write(f"Environment: {os.environ.get('ENVIRONMENT', 'NOT SET')}")
    
    # Load data
    try:
        st.sidebar.info("Loading DataManager...")
        dm = DataManager()
        st.sidebar.success("DataManager initialized")
        
        st.sidebar.info("Loading shares data...")
        shares = dm.load_data()
        st.sidebar.success(f"Shares loaded: {len(shares)} rows")
        
        st.sidebar.info("Loading financials...")
        financials_df = dm.load_financials()
        st.sidebar.success(f"Financials loaded: {len(financials_df)} rows")
        
        st.sidebar.info("Loading ratings...")
        ratings_df = dm.load_ratings()
        st.sidebar.success(f"Ratings loaded: {len(ratings_df)} rows")
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        import traceback
        st.error(traceback.format_exc())
        return
    
    # DEBUG: Show columns
    st.sidebar.markdown("### 📊 Data Columns")
    st.sidebar.write("Shares columns:", list(shares.columns))
    if not financials_df.empty:
        st.sidebar.write("Financials columns:", list(financials_df.columns))
    if not ratings_df.empty:
        st.sidebar.write("Ratings columns:", list(ratings_df.columns))
    
    # Handle empty data
    if shares.empty:
        st.warning("No stock data available. Please check BigQuery connection.")
        st.info("The dashboard requires data to be loaded from BigQuery. Make sure:")
        st.info("1. PROJECT_ID environment variable is set")
        st.info("2. BigQuery credentials are configured")
        st.info("3. The stocks.shares table has data")
        return
    
    # Sidebar - Stock selector
    st.sidebar.markdown('<div class="sidebar-header">Choose the stock</div>', unsafe_allow_html=True)
    
    # Check if symbol column exists
    if 'symbol' not in shares.columns:
        st.error("Data loaded but missing symbol column")
        st.write("Available columns:", list(shares.columns))
        return
    
    selected_symbol = st.sidebar.selectbox(
        "Select Stock",
        options=sorted(shares['symbol'].unique()),
        key="dashboard_symbol"
    )
    
    # Get stock data
    historical_data = shares[shares['symbol'] == selected_symbol].sort_values('date')
    latest_data = historical_data[historical_data.index == historical_data.index.max()].iloc[0]
    
    # Sidebar - Stock info
    st.sidebar.markdown(f"""
        <div class="metric-card">
            <h4>{latest_data['name']}</h4>
            <h4>Price: {latest_data['close']:.0f} XOF</h4>
            <h4>Dividend: {latest_data['dividend']:.0f} XOF</h4>
            <h4>ROI: {latest_data['roi']:.2%}</h4>
        </div>
    """, unsafe_allow_html=True)
    
    # Main content
    main_container = st.container()
    
    with main_container:
        # Price Chart
        st.markdown(f"### {selected_symbol} Price History", unsafe_allow_html=True)
        
        fig_price = px.line(
            historical_data,
            x='date',
            y='close',
            title='',
            template='plotly_white'
        )
        fig_price.update_layout(
            title_font_size=16,
            height=400,
            showlegend=False
        )
        fig_price.update_traces(
            line=dict(color='#3b82f6', width=2),
            hovertemplate='<b>Date:</b> %{x}<br><b>Price:</b> %{{y:.0f}} XOF<extra></extra>'
        )
        st.plotly_chart(fig_price, use_container_width=True)
        
        st.markdown("---")
        
        # Signals Section
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("<h4 style='text-align: center;'>Trading Signal</h4>", unsafe_allow_html=True)
            pie_fig = create_signal_pie_chart(latest_data[['buy', 'keep', 'sell']].to_dict())
            st.plotly_chart(pie_fig, use_container_width=True)
        
        with col2:
            st.markdown("<h4 style='text-align: center;'>Confidence Level</h4>", unsafe_allow_html=True)
            gauge_fig = create_gauge_chart(latest_data['confidence'], "")
            st.plotly_chart(gauge_fig, use_container_width=True)
        
        # Financial Summary (compact)
        st.markdown("---")
        st.markdown("### Financial Overview", unsafe_allow_html=True)
        
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        
        symbol_financials = get_financial_summary(financials_df, selected_symbol) if not financials_df.empty else {}
        symbol_ratings = get_rating_summary(ratings_df, selected_symbol) if not ratings_df.empty else {}
        
        with col_f1:
            revenue = symbol_financials.get('revenue')
            st.metric("Revenue", f"{revenue:,.0f} XOF" if revenue else "N/A")
        
        with col_f2:
            net_income = symbol_financials.get('net_income')
            st.metric("Net Income", f"{net_income:,.0f} XOF" if net_income else "N/A")
        
        with col_f3:
            lt_rating = symbol_ratings.get('long_term')
            st.metric("Long-Term Rating", lt_rating if lt_rating else "N/A")
        
        with col_f4:
            st.metric("Recommendation", latest_data.get('recommendation', 'N/A'))
        
        # Performance Tables
        st.markdown("---")
        col_table1, col_table2, col_table3 = st.columns(3)
        
        with col_table1:
            st.markdown("<h4 style='text-align: center; color: green;'>Top 10 by ROI</h4>", unsafe_allow_html=True)
            top_roi = top10_by_roi(shares).style.format({'roi': '{:.2%}', 'close': '{:.0f}', 'volume': '{:.0f}'})
            st.dataframe(top_roi, use_container_width=True, hide_index=True)
        
        with col_table2:
            st.markdown("<h4 style='text-align: center; color: green;'>Top Weekly</h4>", unsafe_allow_html=True)
            top_weekly = top10_weekly_performers(shares).style.format({'growth': '{:.2%}', 'price': '{:.0f}', 'latest_volume': '{:.0f}'})
            st.dataframe(top_weekly, use_container_width=True, hide_index=True)
        
        with col_table3:
            st.markdown("<h4 style='text-align: center; color: red;'>Bottom Weekly</h4>", unsafe_allow_html=True)
            bottom_weekly = bottom10_weekly_performers(shares).style.format({'growth': '{:.2%}', 'price': '{:.0f}', 'latest_volume': '{:.0f}'})
            st.dataframe(bottom_weekly, use_container_width=True, hide_index=True)
    
    # Footer
    st.markdown("---")
    st.markdown("**Data Source:** BRVM | **Powered by:** Bayesian Ensemble Technical Analysis")


# Call show() function to render the page when Streamlit loads this file
show()