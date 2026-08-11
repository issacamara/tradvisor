"""
Page 2: Stock Analysis
Detailed fundamental analysis with passive income scoring
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from data_manager import DataManager
from core.fundamental.analyzer import (
    FundamentalAnalyzer,
    get_financial_summary,
    get_rating_summary
)


def apply_page_css():
    """Apply page-specific CSS"""
    st.markdown("""
    <style>
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        margin: 1rem 0;
    }
    .score-value {
        font-size: 3rem;
        font-weight: bold;
    }
    .score-label {
        font-size: 1rem;
        opacity: 0.9;
    }
    .score-breakdown {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .recommendation-buy {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    .recommendation-hold {
        background-color: #fff3cd;
        color: #856404;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    .recommendation-avoid {
        background-color: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)


def create_score_gauge(score: float, title: str = "Passive Income Score") -> go.Figure:
    """Create a gauge chart for the passive income score"""
    # Determine color based on score
    if score >= 70:
        color = "#28a745"  # Green
    elif score >= 50:
        color = "#ffc107"  # Yellow
    elif score >= 30:
        color = "#fd7e14"  # Orange
    else:
        color = "#dc3545"  # Red
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 20}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 30], 'color': '#ffcccc'},
                {'range': [30, 50], 'color': '#fff3cd'},
                {'range': [50, 70], 'color': '#d4edda'},
                {'range': [70, 100], 'color': '#c3e6cb'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 70
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
        paper_bgcolor="white"
    )
    
    return fig


def calculate_passive_income_score(financials: dict, ratings: dict, dividend: float, price: float) -> dict:
    """
    Calculate passive income score (0-100) based on IMPLEMENTATION_PLAN.md criteria.
    
    Returns dict with total score and breakdown.
    """
    score = {
        'total': 0,
        'yield_score': 0,
        'sustainability_score': 0,
        'stability_score': 0,
        'growth_score': 0
    }
    
    # Yield Score (0-40 points)
    if price > 0:
        dividend_yield = dividend / price
        if dividend_yield > 0.08:
            score['yield_score'] = 20
        elif dividend_yield >= 0.05:
            score['yield_score'] = 15
        elif dividend_yield > 0:
            score['yield_score'] = 5
    
    # Sustainability Score (0-30 points)
    # Based on ROE
    if financials.get('roe'):
        if financials['roe'] >= 0.15:
            score['sustainability_score'] += 15
        elif financials['roe'] > 0:
            score['sustainability_score'] += 5
    
    # Based on payout ratio (estimated)
    if financials.get('net_income') and financials['net_income'] > 0 and dividend > 0:
        # Simplified: dividend / net_income (needs shares outstanding for accurate calculation)
        # Using a rough estimate
        if dividend / price < 0.70:  # Low payout
            score['sustainability_score'] += 15
        elif dividend / price < 0.90:
            score['sustainability_score'] += 10
        elif dividend / price < 1.0:
            score['sustainability_score'] += 5
    
    # Stability Score (0-20 points)
    # Based on debt-to-equity
    if financials.get('debt_to_equity'):
        if financials['debt_to_equity'] < 1.0:
            score['stability_score'] += 10
        elif financials['debt_to_equity'] < 2.0:
            score['stability_score'] += 5
    
    # Based on credit rating
    if ratings.get('long_term'):
        rating = ratings['long_term'].upper()
        if 'AA' in rating:
            score['stability_score'] += 10
        elif 'A' in rating:
            score['stability_score'] += 7
        elif 'BBB' in rating:
            score['stability_score'] += 5
    
    # Growth Score (0-10 points)
    # Based on net margin
    if financials.get('net_margin'):
        if financials['net_margin'] >= 0.10:
            score['growth_score'] = 10
        elif financials['net_margin'] >= 0.05:
            score['growth_score'] = 7
        elif financials['net_margin'] > 0:
            score['growth_score'] = 3
    
    # Calculate total
    score['total'] = (
        score['yield_score'] +
        score['sustainability_score'] +
        score['stability_score'] +
        score['growth_score']
    )
    
    return score


def get_recommendation(score: int) -> tuple:
    """Get recommendation text and CSS class based on score"""
    if score >= 70:
        return ("STRONG BUY", "recommendation-buy")
    elif score >= 50:
        return ("BUY", "recommendation-buy")
    elif score >= 30:
        return ("HOLD", "recommendation-hold")
    else:
        return ("AVOID", "recommendation-avoid")


def show():
    """Render the Stock Analysis page"""
    apply_page_css()
    
    # Page header
    st.markdown("# Stock Analysis")
    st.markdown("### Fundamental Analysis & Passive Income Scoring")
    st.markdown("---")
    
    # Load data
    try:
        dm = DataManager()
        shares = dm.load_data()
        financials_df = dm.load_financials()
        ratings_df = dm.load_ratings()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return
    
    # Handle empty data
    if shares.empty:
        st.warning("No stock data available. Please check BigQuery connection.")
        return
    
    # Stock selector
    col_select, _ = st.columns([1, 2])
    with col_select:
        selected_symbol = st.selectbox(
            "Select Stock for Analysis",
            sorted(shares['SYMBOL'].unique()),
            key="analysis_symbol"
        )
    
    # Get stock data
    stock_data = shares[shares['SYMBOL'] == selected_symbol].sort_values('DATE').iloc[-1]
    symbol_financials = get_financial_summary(financials_df, selected_symbol)
    symbol_ratings = get_rating_summary(ratings_df, selected_symbol)
    
    # Calculate additional ratios
    if symbol_financials.get('total_equity') and symbol_financials.get('total_debt'):
        symbol_financials['debt_to_equity'] = symbol_financials['total_debt'] / symbol_financials['total_equity']
    if symbol_financials.get('net_income') and symbol_financials.get('total_equity'):
        symbol_financials['roe'] = symbol_financials['net_income'] / symbol_financials['total_equity']
    if symbol_financials.get('net_income') and symbol_financials.get('revenue'):
        symbol_financials['net_margin'] = symbol_financials['net_income'] / symbol_financials['revenue']
    
    # Calculate passive income score
    score = calculate_passive_income_score(
        symbol_financials,
        symbol_ratings,
        stock_data.get('DIVIDEND', 0),
        stock_data.get('CLOSE', 0)
    )
    
    recommendation, rec_class = get_recommendation(score['total'])
    
    # Main content
    st.markdown(f"## {selected_symbol} - {stock_data.get('NAME', 'N/A')}")
    
    # Score Section
    col_score, col_rec = st.columns([1, 1])
    
    with col_score:
        fig = create_score_gauge(score['total'], "Passive Income Score")
        st.plotly_chart(fig, use_container_width=True)
    
    with col_rec:
        st.markdown("### Investment Recommendation")
        st.markdown(f'<div class="{rec_class}">{recommendation}</div>', unsafe_allow_html=True)
        
        st.markdown("### Score Breakdown")
        st.markdown(f"""
        <div class="score-breakdown">
            <p><strong>Yield Score:</strong> {score['yield_score']}/40 pts</p>
            <p><strong>Sustainability:</strong> {score['sustainability_score']}/30 pts</p>
            <p><strong>Stability:</strong> {score['stability_score']}/20 pts</p>
            <p><strong>Growth:</strong> {score['growth_score']}/10 pts</p>
            <hr>
            <p><strong>Total:</strong> {score['total']}/100 pts</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Key Metrics
    st.markdown("---")
    st.markdown("### Key Financial Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        dividend_yield = stock_data.get('DIVIDEND', 0) / stock_data.get('CLOSE', 1) * 100 if stock_data.get('CLOSE', 0) > 0 else 0
        st.metric("Dividend Yield", f"{dividend_yield:.2f}%")
    
    with col2:
        st.metric("Dividend", f"{stock_data.get('DIVIDEND', 0):.0f} XOF")
    
    with col3:
        st.metric("Price", f"{stock_data.get('CLOSE', 0):.0f} XOF")
    
    with col4:
        st.metric("ROI", f"{stock_data.get('ROI', 0):.2%}")
    
    # Financial Ratios
    st.markdown("---")
    st.markdown("### Financial Ratios")
    
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    
    with col_r1:
        de = symbol_financials.get('debt_to_equity')
        st.metric("Debt-to-Equity", f"{de:.2f}" if de else "N/A")
    
    with col_r2:
        roe = symbol_financials.get('roe')
        st.metric("ROE", f"{roe:.1%}" if roe else "N/A")
    
    with col_r3:
        nm = symbol_financials.get('net_margin')
        st.metric("Net Margin", f"{nm:.1%}" if nm else "N/A")
    
    with col_r4:
        fy = symbol_financials.get('fiscal_year')
        st.metric("Fiscal Year", str(fy) if fy else "N/A")
    
    # Credit Ratings
    st.markdown("---")
    st.markdown("### Credit Ratings")
    
    col_rt1, col_rt2 = st.columns(2)
    
    with col_rt1:
        lt_rating = symbol_ratings.get('long_term', 'N/A')
        st.metric("Long-Term Rating", lt_rating if lt_rating else "N/A")
    
    with col_rt2:
        st.metric("Short-Term Rating", symbol_ratings.get('short_term', 'N/A') or "N/A")
    
    # Long-term investment criteria
    st.markdown("---")
    st.markdown("### Long-Term Investment Criteria")
    
    criteria = [
        ("Dividend Yield > 6%", dividend_yield > 6, dividend_yield),
        ("ROE > 15%", (symbol_financials.get('roe') or 0) > 0.15, symbol_financials.get('roe')),
        ("Debt-to-Equity < 1", (symbol_financials.get('debt_to_equity') or float('inf')) < 1, symbol_financials.get('debt_to_equity')),
        ("Net Margin > 10%", (symbol_financials.get('net_margin') or 0) > 0.10, symbol_financials.get('net_margin')),
    ]
    
    for criterion, passed, value in criteria:
        status = "✅" if passed else "❌"
        value_str = f"{value:.2%}" if isinstance(value, float) else str(value)
        st.markdown(f"{status} **{criterion}**: {value_str}")
    
    # Footer
    st.markdown("---")
    st.caption("Scoring based on IMPLEMENTATION_PLAN.md criteria")
