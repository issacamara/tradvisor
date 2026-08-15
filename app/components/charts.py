"""Plotly chart renderers for technical indicators, price history, and dividends."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def render_candlestick_chart(df_ta: pd.DataFrame, symbol: str) -> go.Figure:
    """Renders interactive candlestick chart with MA, EMA, BB, VWAP, and PSAR overlays."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_ta['DATE'], open=df_ta['OPEN'], high=df_ta['HIGH'],
        low=df_ta['LOW'], close=df_ta['CLOSE'], name='OHLC'
    ), row=1, col=1)

    # Overlays
    if 'MA20' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['MA20'], line=dict(color='orange', width=1.5), name='MA20'), row=1, col=1)
    if 'MA50' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['MA50'], line=dict(color='blue', width=1.5), name='MA50'), row=1, col=1)
    if 'VWAP' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['VWAP'], line=dict(color='purple', width=1.5, dash='dash'), name='VWAP'), row=1, col=1)
    if 'BB_Upper' in df_ta.columns and 'BB_Lower' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB Lower'), row=1, col=1)
    if 'PSAR' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['PSAR'], mode='markers', marker=dict(size=3, color='black'), name='PSAR'), row=1, col=1)

    # Volume Subplot
    colors = ['green' if row['CLOSE'] >= row['OPEN'] else 'red' for _, row in df_ta.iterrows()]
    fig.add_trace(go.Bar(x=df_ta['DATE'], y=df_ta['VOLUME'], marker_color=colors, name='Volume'), row=2, col=1)

    fig.update_layout(
        title=f"{symbol} - Technical Analysis Chart",
        xaxis_rangeslider_visible=False,
        template='plotly_white',
        height=600,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

def render_rsi_macd_chart(df_ta: pd.DataFrame) -> go.Figure:
    """Renders RSI and MACD oscillator subplots."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.5])

    # RSI
    if 'RSI' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['RSI'], line=dict(color='purple', width=2), name='RSI (14)'), row=1, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=1, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=1, col=1)

    # MACD
    if 'MACD' in df_ta.columns and 'MACD_Signal' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['MACD'], line=dict(color='blue', width=1.5), name='MACD'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_ta['DATE'], y=df_ta['MACD_Signal'], line=dict(color='orange', width=1.5), name='Signal'), row=2, col=1)
        if 'MACD_Hist' in df_ta.columns:
            colors = ['green' if val >= 0 else 'red' for val in df_ta['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_ta['DATE'], y=df_ta['MACD_Hist'], marker_color=colors, name='Histogram'), row=2, col=1)

    fig.update_layout(height=400, template='plotly_white', margin=dict(l=20, r=20, t=20, b=20))
    return fig

def render_financial_bar_chart(df_fin: pd.DataFrame, symbol: str) -> go.Figure:
    """Renders 5-year Revenue and Net Income trend chart."""
    df_sorted = df_fin.sort_values('fiscal_year', ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_sorted['fiscal_year'], y=df_sorted['revenue'], name='Revenue (XOF)', marker_color='#1f77b4'))
    fig.add_trace(go.Bar(x=df_sorted['fiscal_year'], y=df_sorted['net_income'], name='Net Income (XOF)', marker_color='#2ca02c'))
    fig.update_layout(
        title=f"{symbol} - 5-Year Financial Trend (Revenue vs Net Income)",
        barmode='group',
        template='plotly_white',
        height=350,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig
