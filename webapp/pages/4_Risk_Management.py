"""
Page 4: Risk Management
Stop-loss, position sizing, and risk analysis
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from data_manager import DataManager


def apply_page_css():
    """Apply page-specific CSS"""
    st.markdown("""
    <style>
    .risk-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .risk-high {
        border-left: 4px solid #dc3545;
    }
    .risk-medium {
        border-left: 4px solid #ffc107;
    }
    .risk-low {
        border-left: 4px solid #28a745;
    }
    .position-size {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
    }
    .position-amount {
        font-size: 2.5rem;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range for stop-loss"""
    if len(df) < period + 1:
        return 0
    
    high = df['HIGH'].values if 'HIGH' in df.columns else df['high'].values
    low = df['LOW'].values if 'LOW' in df.columns else df['low'].values
    close = df['CLOSE'].values if 'CLOSE' in df.columns else df['close'].values
    
    # Calculate True Range
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = 0  # First value is undefined
    
    # Calculate ATR
    atr = np.mean(tr[-period:])
    
    return atr


def calculate_stop_loss(current_price: float, atr: float, method: str = 'atr_2x') -> dict:
    """
    Calculate stop-loss prices based on different methods.
    
    Methods:
    - atr_2x: 2x ATR below current price
    - atr_1_5x: 1.5x ATR below current price
    - percentage_5: 5% below current price
    - percentage_10: 10% below current price
    """
    stop_prices = {}
    
    if method == 'atr_2x' or method == 'all':
        stop_prices['ATR 2x'] = current_price - (2 * atr)
    
    if method == 'atr_1_5x' or method == 'all':
        stop_prices['ATR 1.5x'] = current_price - (1.5 * atr)
    
    if method == 'percentage_5' or method == 'all':
        stop_prices['5% Stop'] = current_price * 0.95
    
    if method == 'percentage_10' or method == 'all':
        stop_prices['10% Stop'] = current_price * 0.90
    
    return stop_prices


def calculate_position_size(
    account_balance: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss_price: float
) -> dict:
    """
    Calculate position size based on risk management principles.
    
    Returns:
        dict with shares, position_value, risk_amount
    """
    # Risk amount in currency
    risk_amount = account_balance * (risk_percentage / 100)
    
    # Risk per share
    risk_per_share = entry_price - stop_loss_price
    
    if risk_per_share <= 0:
        return {
            'shares': 0,
            'position_value': 0,
            'risk_amount': risk_amount,
            'risk_percentage': risk_percentage
        }
    
    # Number of shares
    shares = int(risk_amount / risk_per_share)
    
    # Position value
    position_value = shares * entry_price
    
    return {
        'shares': shares,
        'position_value': position_value,
        'risk_amount': risk_amount,
        'risk_percentage': risk_percentage,
        'risk_per_share': risk_per_share
    }


def calculate_kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate Kelly Criterion for position sizing.
    
    K% = W - (1-W) / (R)
    Where W = win rate, R = win/loss ratio
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0
    
    win_loss_ratio = avg_win / avg_loss
    kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
    
    # Kelly should be between 0 and 1
    return max(0, min(kelly, 1))


def calculate_risk_score(
    volatility: float,
    debt_to_equity: float,
    current_ratio: float,
    rating: str
) -> dict:
    """
    Calculate overall risk score (0-100, lower is safer).
    """
    score = 0
    max_score = 100
    
    # Volatility score (0-30)
    if volatility > 0.03:
        score += 30
    elif volatility > 0.02:
        score += 20
    elif volatility > 0.01:
        score += 10
    
    # Debt-to-equity score (0-25)
    if debt_to_equity > 2:
        score += 25
    elif debt_to_equity > 1:
        score += 15
    elif debt_to_equity > 0.5:
        score += 5
    
    # Current ratio score (0-20)
    if current_ratio < 1:
        score += 20
    elif current_ratio < 1.5:
        score += 10
    
    # Credit rating score (0-25)
    rating = (rating or '').upper()
    if 'B' in rating:
        score += 25
    elif 'BB' in rating:
        score += 20
    elif 'BBB' in rating:
        score += 15
    elif 'A' in rating:
        score += 5
    elif 'AA' in rating or 'AAA' in rating:
        score += 0
    
    # Risk level
    if score >= 70:
        risk_level = "HIGH"
    elif score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    return {
        'score': score,
        'max_score': max_score,
        'risk_level': risk_level
    }


def create_risk_gauge(score: float) -> go.Figure:
    """Create a gauge chart for risk score"""
    if score >= 70:
        color = "#dc3545"  # Red
    elif score >= 40:
        color = "#ffc107"  # Yellow
    else:
        color = "#28a745"  # Green
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': 'Risk Score', 'font': {'size': 20}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': '#d4edda'},
                {'range': [40, 70], 'color': '#fff3cd'},
                {'range': [70, 100], 'color': '#f8d7da'}
            ]
        }
    ))
    
    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=60, b=20),
        paper_bgcolor="white"
    )
    
    return fig


def show():
    """Render the Risk Management page"""
    apply_page_css()
    
    # Page header
    st.markdown("# Risk Management")
    st.markdown("### Stop-loss, position sizing, and risk analysis")
    st.markdown("---")
    
    # Load data
    try:
        dm = DataManager()
        shares = dm.load_data()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return
    
    # Sidebar inputs
    st.sidebar.markdown("### Risk Parameters")
    
    account_balance = st.sidebar.number_input(
        "Account Balance (XOF)",
        min_value=100000,
        value=10000000,
        step=100000,
        format="%d"
    )
    
    risk_percentage = st.sidebar.slider(
        "Risk per Trade (%)",
        min_value=0.5,
        max_value=10.0,
        value=2.0,
        step=0.5
    )
    
    # Stock selector
    col_select, _ = st.columns([1, 2])
    with col_select:
        selected_symbol = st.selectbox(
            "Select Stock",
            sorted(shares['SYMBOL'].unique()),
            key="risk_symbol"
        )
    
    # Get stock data
    stock_data = shares[shares['SYMBOL'] == selected_symbol].sort_values('DATE')
    
    if len(stock_data) < 30:
        st.warning("Insufficient data for risk analysis")
        return
    
    latest = stock_data.iloc[-1]
    current_price = latest['CLOSE']
    
    # Calculate ATR
    atr = calculate_atr(stock_data)
    
    # Display current price
    st.markdown(f"## {selected_symbol} - Risk Analysis")
    
    col_price, col_atr = st.columns(2)
    with col_price:
        st.metric("Current Price", f"{current_price:.0f} XOF")
    with col_atr:
        st.metric("ATR (14)", f"{atr:.0f} XOF")
    
    # Stop-Loss Section
    st.markdown("---")
    st.markdown("### Stop-Loss Levels")
    
    stop_prices = calculate_stop_loss(current_price, atr, 'all')
    
    col_sl1, col_sl2, col_sl3, col_sl4 = st.columns(4)
    
    for i, (method, price) in enumerate(stop_prices.items()):
        with [col_sl1, col_sl2, col_sl3, col_sl4][i]:
            loss_pct = ((current_price - price) / current_price) * 100
            st.metric(method, f"{price:.0f} XOF", f"-{loss_pct:.1f}%")
    
    # Position Sizing Section
    st.markdown("---")
    st.markdown("### Position Sizing")
    
    # Use 2x ATR as default stop-loss
    default_stop = current_price - (2 * atr)
    
    col_ps1, col_ps2 = st.columns(2)
    
    with col_ps1:
        stop_loss_input = st.number_input(
            "Stop-Loss Price (XOF)",
            min_value=1.0,
            value=float(default_stop),
            step=100.0
        )
    
    with col_ps2:
        st.metric("Risk per Share", f"{current_price - stop_loss_input:.0f} XOF")
    
    # Calculate position size
    position = calculate_position_size(
        account_balance,
        risk_percentage,
        current_price,
        stop_loss_input
    )
    
    # Display position size
    st.markdown(f"""
    <div class="position-size">
        <div class="position-amount">{position['shares']:,}</div>
        <div>shares</div>
        <hr>
        <div>Position Value: {position['position_value']:,.0f} XOF</div>
        <div>Risk Amount: {position['risk_amount']:,.0f} XOF ({position['risk_percentage']:.1f}%)</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Risk Score Section
    st.markdown("---")
    st.markdown("### Stock Risk Score")
    
    col_rs1, col_rs2 = st.columns(2)
    
    with col_rs1:
        # Calculate volatility (standard deviation of returns)
        returns = stock_data['CLOSE'].pct_change().dropna()
        volatility = returns.std()
        
        # Get financial data for risk calculation
        financials_df = dm.load_financials()
        ratings_df = dm.load_ratings()
        
        from core.fundamental.analyzer import get_financial_summary, get_rating_summary
        symbol_financials = get_financial_summary(financials_df, selected_symbol)
        symbol_ratings = get_rating_summary(ratings_df, selected_symbol)
        
        # Calculate ratios
        debt_to_equity = 0
        if symbol_financials.get('total_equity') and symbol_financials.get('total_debt'):
            debt_to_equity = symbol_financials['total_debt'] / symbol_financials['total_equity']
        
        current_ratio = 1.5  # Default assumption
        if symbol_financials.get('cash') and symbol_financials.get('total_debt'):
            current_ratio = symbol_financials['cash'] / symbol_financials['total_debt']
        
        rating = symbol_ratings.get('long_term', '')
        
        # Calculate risk score
        risk = calculate_risk_score(volatility, debt_to_equity, current_ratio, rating)
        
        fig = create_risk_gauge(risk['score'])
        st.plotly_chart(fig, use_container_width=True)
    
    with col_rs2:
        st.markdown("#### Risk Factors")
        
        st.markdown(f"""
        <div class="risk-card risk-{'high' if volatility > 0.02 else 'low'}">
            <strong>Volatility:</strong> {volatility:.2%}<br>
            <small>Daily return standard deviation</small>
        </div>
        <div class="risk-card risk-{'high' if debt_to_equity > 1 else 'low'}">
            <strong>Debt-to-Equity:</strong> {debt_to_equity:.2f}<br>
            <small>Financial leverage</small>
        </div>
        <div class="risk-card risk-{'high' if current_ratio < 1 else 'low'}">
            <strong>Current Ratio:</strong> {current_ratio:.2f}<br>
            <small>Liquidity measure</small>
        </div>
        <div class="risk-card risk-{'high' if 'B' in str(rating).upper() else 'low'}">
            <strong>Credit Rating:</strong> {rating or 'N/A'}<br>
            <small>Financial stability</small>
        </div>
        """, unsafe_allow_html=True)
    
    # Kelly Criterion Section
    st.markdown("---")
    st.markdown("### Kelly Criterion (Optional)")
    st.caption("Advanced position sizing based on win rate and win/loss ratio")
    
    col_k1, col_k2, col_k3 = st.columns(3)
    
    with col_k1:
        win_rate = st.slider("Win Rate (%)", 30, 70, 50) / 100
    
    with col_k2:
        avg_win = st.number_input("Avg Win (%)", 1.0, 50.0, 10.0) / 100
    
    with col_k3:
        avg_loss = st.number_input("Avg Loss (%)", 1.0, 50.0, 5.0) / 100
    
    kelly = calculate_kelly_criterion(win_rate, avg_win, avg_loss)
    
    st.metric("Kelly %", f"{kelly:.1%}", help="Optimal position size. Use half for conservative approach.")
    
    if kelly > 0:
        kelly_shares = int((account_balance * kelly * 0.5) / (current_price - stop_loss_input))
        st.info(f"Conservative Kelly position: ~{kelly_shares:,} shares")
    
    # Footer
    st.markdown("---")
    st.caption("Risk management calculations are for educational purposes. Always consider your personal risk tolerance.")
