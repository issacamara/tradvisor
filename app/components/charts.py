"""Plotly chart renderers for technical indicators, price history, and dividends."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def render_candlestick_chart(df_ta: pd.DataFrame, symbol: str) -> go.Figure:
    """Renders interactive candlestick chart with MA, EMA, BB, VWAP, and PSAR overlays."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_ta['date'], open=df_ta['open'], high=df_ta['high'],
        low=df_ta['low'], close=df_ta['close'], name='OHLC'
    ), row=1, col=1)

    # Overlays
    if 'ma20' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['ma20'], line=dict(color='orange', width=1.5), name='MA20'), row=1, col=1)
    if 'ma50' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['ma50'], line=dict(color='blue', width=1.5), name='MA50'), row=1, col=1)
    if 'vwap' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['vwap'], line=dict(color='purple', width=1.5, dash='dash'), name='VWAP'), row=1, col=1)
    if 'bb_upper' in df_ta.columns and 'bb_lower' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['bb_upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['bb_lower'], line=dict(color='gray', width=1, dash='dot'), name='BB Lower'), row=1, col=1)
    if 'psar' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['psar'], mode='markers', marker=dict(size=3, color='black'), name='PSAR'), row=1, col=1)

    # Volume Subplot
    colors = ['green' if row['close'] >= row['open'] else 'red' for _, row in df_ta.iterrows()]
    fig.add_trace(go.Bar(x=df_ta['date'], y=df_ta['volume'], marker_color=colors, name='Volume'), row=2, col=1)

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
    if 'rsi' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['rsi'], line=dict(color='purple', width=2), name='RSI (14)'), row=1, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=1, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=1, col=1)

    # MACD
    if 'macd' in df_ta.columns and 'macd_signal' in df_ta.columns:
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['macd'], line=dict(color='blue', width=1.5), name='MACD'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_ta['date'], y=df_ta['macd_signal'], line=dict(color='orange', width=1.5), name='Signal'), row=2, col=1)
        if 'macd_hist' in df_ta.columns:
            colors = ['green' if val >= 0 else 'red' for val in df_ta['macd_hist']]
            fig.add_trace(go.Bar(x=df_ta['date'], y=df_ta['macd_hist'], marker_color=colors, name='Histogram'), row=2, col=1)

    fig.update_layout(height=400, template='plotly_white', margin=dict(l=20, r=20, t=20, b=20))
    return fig

# def render_financial_bar_chart(df_fin: pd.DataFrame, symbol: str) -> go.Figure:
#     """Renders 5-year Revenue and Net Income trend chart."""
#     df_sorted = df_fin.sort_values('fiscal_year', ascending=True)
#     fig = go.Figure()
#     fig.add_trace(go.Bar(x=df_sorted['fiscal_year'], y=df_sorted['revenue'], name='Revenue (XOF)', marker_color='#1f77b4'))
#     fig.add_trace(go.Bar(x=df_sorted['fiscal_year'], y=df_sorted['net_income'], name='Net Income (XOF)', marker_color='#2ca02c'))
#     fig.update_layout(
#         title=f"{symbol} - 5-Year Financial Trend (Revenue vs Net Income)",
#         barmode='group',
#         template='plotly_white',
#         height=350,
#         margin=dict(l=20, r=20, t=40, b=20)
#     )
#     return fig

def render_financial_bar_chart(
    df_fin: pd.DataFrame, symbol: str, company_name: str = ''
) -> go.Figure:
  """Renders 5-year grouped bar chart (Revenue, Net Income, Total Debt, Cash & Cash Eq., Total Equity)

  with conditional bar coloring for negative Net Income and colored YoY growth annotations.
  """
  if df_fin.empty:
    return go.Figure()

  df_sorted = df_fin.sort_values('fiscal_year', ascending=True).reset_index(
      drop=True
  )

  # 2. Financial metrics included in the grouped bar chart (all in FCFA)
  metrics = [
      {'col': 'revenue', 'name': 'Revenue (FCFA)', 'base_color': '#1f77b4'},
      {'col': 'net_income', 'name': 'Net Income (FCFA)', 'base_color': '#2ca02c'},
      {'col': 'total_debt', 'name': 'Total Debt (FCFA)', 'base_color': '#ff7f0e'},
      {
          'col': 'cash_and_cash_equivalents',
          'name': 'Cash & Cash Eq. (FCFA)',
          'base_color': '#17becf',
      },
      {
          'col': 'total_equity',
          'name': 'Total Equity (FCFA)',
          'base_color': '#9467bd',
      },
  ]

  fig = go.Figure()

  for m in metrics:
    col = m['col']
    if col not in df_sorted.columns:
      continue

    values = df_sorted[col].values

    # 1. Negative net_income bars rendered in red (#d62728)
    if col == 'net_income':
      bar_colors = [
          '#d62728' if (pd.notnull(v) and v < 0) else '#2ca02c' for v in values
      ]
    else:
      bar_colors = [m['base_color']] * len(values)

    # 3. YoY growth / decline calculations and colored text annotations
    text_labels = []
    text_colors = []

    for i in range(len(values)):
      curr = values[i]
      if i == 0 or pd.isna(curr) or pd.isna(values[i - 1]) or values[i - 1] == 0:
        text_labels.append('')
        text_colors.append('#333333')
      else:
        prev = values[i - 1]
        pct = ((curr - prev) / abs(prev)) * 100
        text_labels.append(f'{pct:+.1f}%')
        # Green (#2ca02c) for positive growth, Red (#d62728) for decline
        text_colors.append('#2ca02c' if pct >= 0 else '#d62728')

    fig.add_trace(
        go.Bar(
            x=df_sorted['fiscal_year'],
            y=values,
            name=m['name'],
            marker_color=bar_colors,
            text=text_labels,
            textposition='outside',
            textfont=dict(color=text_colors, size=11),
        )
    )

  # 4 & Currencies: Display Company Name and FCFA units
  title_text = (
      f'{company_name} ({symbol}) - Financial Statement Trends (FCFA)'
      if company_name
      else f'{symbol} - Financial Statement Trends (FCFA)'
  )

  fig.update_layout(
      title=title_text,
      barmode='group',
      template='plotly_white',
      height=480,
      yaxis=dict(title='Amount (FCFA)'),
      xaxis=dict(title='Fiscal Year', type='category'),
      legend=dict(
          orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1
      ),
      margin=dict(l=20, r=20, t=60, b=20),
  )

  return fig