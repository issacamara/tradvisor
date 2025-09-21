import plotly.graph_objects as go
import json, os
from google.cloud import bigquery

def create_gauge_chart(value, title, max_val=100):
    """Create a gauge chart for confidence"""

    value_pct = value *100
    # Determine color based on value
    if value_pct >= 80:
        color = "#00ff00"  # Green
    elif value_pct >= 60:
        color = "#ffff00"  # Yellow
    else:
        color = "#ff6b6b"  # Red

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value_pct,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 20}},
        gauge={
            'axis': {'range': [None, max_val], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 50], 'color': "#ffcccc"},
                {'range': [50, 80], 'color': "#ffffcc"},
                {'range': [80, 100], 'color': "#ccffcc"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))

    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=60, b=20),
        paper_bgcolor="white"
    )

    return fig


def create_signal_pie_chart(probabilities):
    """Create pie chart for signal probabilities"""

    # Create pie chart data
    labels = ['Buy', 'Hold', 'Sell']
    values = [probabilities['BUY'] * 100, probabilities['KEEP'] * 100, probabilities['SELL'] * 100]
    colors = ['#16a34a', '#f59e0b', '#dc2626']

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        marker=dict(colors=colors)
    )])

    fig.update_layout(
        title=f'',

        title_font_size=16,
        height=400,
        showlegend=True,
        legend=dict(orientation="v", x=1.05, y=0.5)
    )

    fig.update_traces(
        textinfo='percent+label',
        textfont_size=12,
        hovertemplate='<b>%{label}</b><br>%{percent}<br>Value: %{value:.1f}%<extra></extra>'
    )
    #######################################################@
    # colors = {
    #     'BUY': '#00ff00',
    #     'KEEP': '#ffa500',
    #     'SELL': '#ff6b6b'
    # }
    #
    # fig = go.Figure(data=[go.Pie(
    #     labels=list(probabilities.keys()),
    #     values=list(probabilities.values()),
    #     hole=0.4,
    #     marker_colors=[colors[label] for label in probabilities.keys()],
    #     textinfo='label+percent',
    #     textposition='outside',
    #     textfont_size=14
    # )])
    #
    # fig.update_layout(
    #     title="Signal Probability",
    #     title_x=0.3,
    #     height=400,
    #     margin=dict(l=20, r=20, t=60, b=20),
    #     showlegend=False,
    #     legend=dict(
    #         orientation="h",
    #         yanchor="bottom",
    #         y=1.02,
    #         xanchor="right",
    #         x=1
    #     )
    # )

    return fig

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
