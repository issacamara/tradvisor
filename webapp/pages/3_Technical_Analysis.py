"""
Page 3: Technical Analysis
Deep dive into technical indicators with charts
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_manager import DataManager
from trading import TechnicalIndicatorTrading


def apply_page_css():
    """Apply page-specific CSS"""
    st.markdown("""
    <style>
    .indicator-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #3b82f6;
        margin: 0.5rem 0;
    }
    .indicator-buy {
        border-left-color: #28a745;
    }
    .indicator-sell {
        border-left-color: #dc3545;
    }
    .indicator-hold {
        border-left-color: #ffc107;
    }
    .weight-badge {
        background-color: #e9ecef;
        padding: 0.25rem 0.5rem;
        border-radius: 5px;
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)


def calculate_indicators_for_stock(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Calculate all technical indicators for a specific stock"""
    trading_system = TechnicalIndicatorTrading()
    
    # Filter for symbol and get enough historical data
    symbol_data = df[df['SYMBOL'] == symbol].copy()
    
    if len(symbol_data) < 50:
        return pd.DataFrame()
    
    # Calculate indicators
    result = trading_system.calculate_indicators(symbol_data)
    
    return result


def create_price_with_indicators_chart(df: pd.DataFrame, indicators: list) -> go.Figure:
    """Create a price chart with selected indicators"""
    fig = make_subplots(
        rows=len(indicators) + 1, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5] + [0.5 / len(indicators)] * len(indicators)
    )
    
    # Price chart
    fig.add_trace(
        go.Scatter(x=df.index, y=df['close'], name='Close', line=dict(color='#3b82f6', width=2)),
        row=1, col=1
    )
    
    # Add selected indicators
    for i, ind in enumerate(indicators, start=2):
        if ind == 'MA' and 'ma' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['ma'], name='MA(20)', line=dict(color='#ff9800', width=1)), row=i, col=1)
        elif ind == 'EMA' and 'ema' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['ema'], name='EMA(20)', line=dict(color='#9c27b0', width=1)), row=i, col=1)
        elif ind == 'BB' and 'bb_upper' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], name='BB Upper', line=dict(color='#f44336', width=1), showlegend=False), row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], name='BB Lower', line=dict(color='#f44336', width=1), fill='tonexty', fillcolor='rgba(244,67,54,0.1)', showlegend=False), row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], name='BB Middle', line=dict(color='#f44336', width=1, dash='dash')), row=i, col=1)
        elif ind == 'VWAP' and 'vwap' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], name='VWAP', line=dict(color='#00bcd4', width=1)), row=i, col=1)
        elif ind == 'PSAR' and 'psar' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['psar'], name='PSAR', mode='markers', marker=dict(color='#795548', size=4)), row=i, col=1)
        elif ind == 'RSI' and 'rsi' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name='RSI', line=dict(color='#607d8b', width=1)), row=i, col=1)
            # Add overbought/oversold lines
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=i, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=i, col=1)
        elif ind == 'MACD' and 'macd' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['macd'], name='MACD', line=dict(color='#2196f3', width=1)), row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], name='Signal', line=dict(color='#ff5722', width=1)), row=i, col=1)
        elif ind == 'CCI' and 'cci' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['cci'], name='CCI', line=dict(color='#9c27b0', width=1)), row=i, col=1)
            fig.add_hline(y=100, line_dash="dash", line_color="red", row=i, col=1)
            fig.add_hline(y=-100, line_dash="dash", line_color="green", row=i, col=1)
        elif ind == 'STOCH' and 'stoch_k' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], name='%K', line=dict(color='#2196f3', width=1)), row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], name='%D', line=dict(color='#ff9800', width=1)), row=i, col=1)
        elif ind == 'CMF' and 'cmf' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['cmf'], name='CMF', line=dict(color='#4caf50', width=1)), row=i, col=1)
            fig.add_hline(y=0, line_dash="dash", line_color="gray", row=i, col=1)
    
    fig.update_layout(
        height=300 * (len(indicators) + 1),
        showlegend=True,
        template='plotly_white',
        margin=dict(l=50, r=50, t=30, b=50)
    )
    
    return fig


def get_indicator_signal(df: pd.DataFrame, indicator: str) -> str:
    """Get the current signal for an indicator"""
    if df.empty or len(df) < 2:
        return "HOLD"
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = {
        'MA': lambda: 'BUY' if latest['close'] > latest['ma'] else 'SELL' if latest['close'] < latest['ma'] else 'HOLD',
        'EMA': lambda: 'BUY' if latest['close'] > latest['ema'] else 'SELL' if latest['close'] < latest['ema'] else 'HOLD',
        'RSI': lambda: 'BUY' if latest['rsi'] < 30 else 'SELL' if latest['rsi'] > 70 else 'HOLD',
        'MACD': lambda: 'BUY' if latest['macd'] > latest['macd_signal'] else 'SELL' if latest['macd'] < latest['macd_signal'] else 'HOLD',
        'BB': lambda: 'BUY' if latest['close'] < latest['bb_lower'] else 'SELL' if latest['close'] > latest['bb_upper'] else 'HOLD',
        'VWAP': lambda: 'BUY' if latest['close'] > latest['vwap'] else 'SELL' if latest['close'] < latest['vwap'] else 'HOLD',
        'PSAR': lambda: 'BUY' if latest['close'] > latest['psar'] else 'SELL' if latest['close'] < latest['psar'] else 'HOLD',
        'CCI': lambda: 'BUY' if latest['cci'] < -100 else 'SELL' if latest['cci'] > 100 else 'HOLD',
        'STOCH': lambda: 'BUY' if latest['stoch_k'] < 20 else 'SELL' if latest['stoch_k'] > 80 else 'HOLD',
        'CMF': lambda: 'BUY' if latest['cmf'] > 0.1 else 'SELL' if latest['cmf'] < -0.1 else 'HOLD',
    }
    
    return signals.get(indicator, lambda: 'HOLD')()


def show():
    """Render the Technical Analysis page"""
    apply_page_css()
    
    # Page header
    st.markdown("# Technical Analysis")
    st.markdown("### Deep dive into technical indicators")
    st.markdown("---")
    
    # Load data
    try:
        dm = DataManager()
        shares = dm.load_data()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return
    
    # Stock selector
    col_select, _ = st.columns([1, 2])
    with col_select:
        selected_symbol = st.selectbox(
            "Select Stock for Analysis",
            sorted(shares['SYMBOL'].unique()),
            key="tech_symbol"
        )
    
    # Calculate indicators
    with st.spinner('Calculating technical indicators...'):
        indicator_data = calculate_indicators_for_stock(shares, selected_symbol)
    
    if indicator_data.empty:
        st.warning("Insufficient data for technical analysis")
        return
    
    # Get trading system for weights
    trading_system = TechnicalIndicatorTrading()
    weights = trading_system.get_market_regime_weights(indicator_data)
    
    # Current price data
    latest = indicator_data.iloc[-1]
    
    # Display current price and signals
    st.markdown(f"## {selected_symbol} - Technical Overview")
    
    col_price, col_conf = st.columns(2)
    with col_price:
        st.metric("Current Price", f"{latest['close']:.0f} XOF")
    with col_conf:
        # Get the confidence from original data
        stock_signals = shares[shares['SYMBOL'] == selected_symbol].iloc[-1]
        st.metric("Confidence", f"{stock_signals.get('CONFIDENCE', 0) * 100:.0f}%")
    
    # Indicator weights
    st.markdown("---")
    st.markdown("### Adaptive Indicator Weights")
    st.caption("Weights are automatically adjusted based on market conditions")
    
    col_w1, col_w2, col_w3, col_w4, col_w5 = st.columns(5)
    
    weight_items = list(weights.items())
    cols = [col_w1, col_w2, col_w3, col_w4, col_w5]
    
    for i, (indicator, weight) in enumerate(weight_items):
        with cols[i % 5]:
            st.markdown(f"<span class='weight-badge'>{indicator}: {weight:.0%}</span>", unsafe_allow_html=True)
    
    # Indicator selection
    st.markdown("---")
    st.markdown("### Indicator Charts")
    
    available_indicators = ['MA', 'EMA', 'RSI', 'MACD', 'BB', 'VWAP', 'CCI', 'STOCH', 'CMF', 'PSAR']
    
    col_ind1, col_ind2 = st.columns([1, 3])
    with col_ind1:
        selected_indicators = st.multiselect(
            "Select indicators to display",
            available_indicators,
            default=['MA', 'RSI', 'MACD']
        )
    
    if selected_indicators:
        fig = create_price_with_indicators_chart(indicator_data, selected_indicators)
        st.plotly_chart(fig, use_container_width=True)
    
    # Individual indicator signals
    st.markdown("---")
    st.markdown("### Indicator Signals")
    
    # Create signal columns
    signal_cols = st.columns(5)
    
    for i, indicator in enumerate(available_indicators):
        signal = get_indicator_signal(indicator_data, indicator)
        
        # Determine CSS class
        signal_class = "indicator-hold"
        if signal == "BUY":
            signal_class = "indicator-buy"
        elif signal == "SELL":
            signal_class = "indicator-sell"
        
        # Get current value
        value = "N/A"
        if indicator == 'RSI' and 'rsi' in indicator_data.columns:
            value = f"{latest['rsi']:.1f}"
        elif indicator == 'MACD' and 'macd' in indicator_data.columns:
            value = f"{latest['macd']:.2f}"
        elif indicator == 'CCI' and 'cci' in indicator_data.columns:
            value = f"{latest['cci']:.1f}"
        elif indicator == 'CMF' and 'cmf' in indicator_data.columns:
            value = f"{latest['cmf']:.3f}"
        elif indicator == 'STOCH' and 'stoch_k' in indicator_data.columns:
            value = f"{latest['stoch_k']:.1f}"
        
        with signal_cols[i % 5]:
            st.markdown(f"""
            <div class="indicator-card {signal_class}">
                <strong>{indicator}</strong><br>
                <span style="font-size: 1.2rem;">{signal}</span><br>
                <small>{value}</small>
            </div>
            """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.caption("Technical indicators calculated using TA-Lib. Weights adapt to market conditions.")
