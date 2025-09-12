import duckdb as db
import streamlit as st
import plotly.graph_objects as go
import os

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

ENVIRONMENT = 'gcp'
project_id = os.environ.get('PROJECT_ID')
# project_id = "dev-tradvisor"
# os.environ["PROJECT_ID"] = project_id
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "webapp/key.json"
client = None
if project_id:
    client = getBigQueryClient()
else:
    ENVIRONMENT = 'on-premise'
    conn = db.connect('database/financial_assets.db')

dataset_names = {"on-premise": "", "gcp":f"{project_id}.stocks."}
st.write(f"Environment is {ENVIRONMENT} ")


# Cache data for 1 day (86400 seconds)
@st.cache_data(ttl=86400)
def load_data():
    shares = None
    dividends = None
    trading_system = TechnicalIndicatorTrading()
    query1 = f"""
                WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM `{dataset_names[ENVIRONMENT]}SHARES`)
                SELECT * FROM `{dataset_names[ENVIRONMENT]}SHARES`
                WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                    AND (SELECT max_date FROM latest_date)
                ORDER BY date DESC
            """

    # query1onprem = f"""
    #             WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM {dataset_names[ENVIRONMENT]}SHARES)
    #             SELECT * FROM {dataset_names[ENVIRONMENT]}SHARES
    #             WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
    #                 AND (SELECT max_date FROM latest_date)
    #             ORDER BY date DESC
    #         """

    # query2 = f"SELECT * FROM bonds"
    # query3 = f"SELECT * FROM indices"
    query4 = f"""
                SELECT * FROM `{dataset_names[ENVIRONMENT]}DIVIDENDS`
                WHERE DATE(date) = (SELECT MAX(DATE(date)) FROM `{dataset_names[ENVIRONMENT]}DIVIDENDS`)
            """
    # query4onPrem = f"""
    #             SELECT * FROM {dataset_names[ENVIRONMENT]}DIVIDENDS
    #             WHERE CAST(date as DATE) = (SELECT MAX(CAST(date as DATE)) FROM {dataset_names[ENVIRONMENT]}DIVIDENDS)
    #         """
    # query5 = f"SELECT * FROM capitalizations"
    if ENVIRONMENT=='on-premise':
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

    result = shares.merge(dividends[["SYMBOL","DIVIDEND","PAYMENT_DATE"]], on='SYMBOL', how='left')
    # result = tr.get_trading_decisions(result)
    result = trading_system.generate_signals(result, adaptive_weights=True)
    result['ROI'] = result['DIVIDEND'] / result['CLOSE']

    # return shares, bonds, indices, dividends, capitalizations
    return result


# Streamlit app
st.title(f"Tradvisor {ENVIRONMENT} ")
# Custom CSS for styling
st.markdown("""
    <style>
    .stTab {background-color: #f0f2f6;padding: 20px;border-radius: 10px;}
    .metric-card {background-color: white;padding: 20px;border-radius: 10px;box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;}
    </style>
""", unsafe_allow_html=True)
# Load and display stock data
shares = load_data()

main_container = st.container()

st.sidebar.header("Choose the symbol")
selected_symbol = st.sidebar.selectbox("",
        options=shares['SYMBOL'].unique())

historical_data = shares[shares['SYMBOL']==selected_symbol].sort_index()
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
    col1, col2 = main_container.columns([2, 1])
    # selected_symbol = col2.selectbox(
    #     "Select Stock Symbol",
    #     options=shares['SYMBOL'].unique()
    # )

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=historical_data['DATE'], y=historical_data['CLOSE'], mode='lines', name='Close Price'))
    fig.update_layout(
        title=f"{selected_symbol} Closing Price",
        xaxis_title="Date",
        yaxis_title="Close Price (XOF)",
        template="plotly_white",
        height=600,
    )

    with col1:
        col1.subheader("Latest Recommendations")

        # Signal probabilities
        pie_fig = create_signal_pie_chart(latest_data[['BUY', 'KEEP', 'SELL']].to_dict())
        col1.plotly_chart(pie_fig, use_container_width=True)
        # display_recommendation_metrics(latest_data)

    with(col2):
        # Confidence gauge
        gauge_fig = create_gauge_chart(latest_data['CONFIDENCE'], "Signal Confidence (%)")
        col2.plotly_chart(gauge_fig, use_container_width=True)
    main_container.plotly_chart(fig, use_container_width=True)

    main_container.dataframe(shares[shares['SYMBOL'] == selected_symbol])


