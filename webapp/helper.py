import plotly.graph_objects as go


def create_gauge_chart(value, title, max_val=100):
    """Create a gauge chart for confidence"""

    # Determine color based on value
    if value >= 80:
        color = "#00ff00"  # Green
    elif value >= 60:
        color = "#ffff00"  # Yellow
    else:
        color = "#ff6b6b"  # Red

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
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
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
        paper_bgcolor="white"
    )

    return fig


def create_signal_pie_chart(probabilities):
    """Create pie chart for signal probabilities"""

    colors = {
        'BUY': '#00ff00',
        'SELL': '#ff6b6b',
        'KEEP': '#ffa500'
    }

    fig = go.Figure(data=[go.Pie(
        labels=list(probabilities.keys()),
        values=list(probabilities.values()),
        hole=0.4,
        marker_colors=[colors[label] for label in probabilities.keys()],
        textinfo='label+percent',
        textposition='outside',
        textfont_size=14
    )])

    fig.update_layout(
        title="Signal Probability Distribution",
        title_x=0.5,
        height=400,
        margin=dict(l=20, r=20, t=60, b=20),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

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