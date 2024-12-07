import sys
import duckdb as db
import pandas as pd
import streamlit as st
import yaml
import numpy as np
from streamlit import columns

import trading as tr

# Load configuration from YAML file
def load_config(config_path='config.yml'):
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    return config


config = load_config()
conn = db.connect(config['duckdb']['database'])


# Cache data for 1 day (86400 seconds)
# @st.cache_data(ttl=86400)
def load_data():
    query1 = f"""SELECT * FROM shares order by date desc"""
    shares = conn.execute(query1).df()

    # query2 = f"SELECT * FROM bonds"
    # query3 = f"SELECT * FROM indices"
    query4 = f"SELECT * FROM dividends"
    # query5 = f"SELECT * FROM capitalizations"
    #
    # bonds = conn.execute(query2).df()
    # indices = conn.execute(query3).df()
    dividends = conn.execute(query4).df()
    # capitalizations = conn.execute(query5).df()

    shares = pd.merge(shares, dividends[["SYMBOL","DIVIDEND","PAYMENT_DATE"]], on='SYMBOL', how='left')
    # shares = shares.set_index('DATE')
    shares = tr.get_trading_decisions(shares)


    # return shares, bonds, indices, dividends, capitalizations
    return shares


# Streamlit app
st.title("Tradvisor")

# Load and display stock data

main_container = st.container()
mt1, mt2 = main_container.tabs(["Top 10 Stocks", "Portfolio"])
with mt1:
    shares = load_data()
    shares = shares[shares.index=='2024-12-06'].reset_index()
    # print(shares[['NAME','Buy','Sell','Keep','MA', 'EMA', 'RSI', 'MACD', 'MACD_signal', 'BB_upper', 'BB_middle', 'BB_lower',
    #                        'STOCH_k', 'STOCH_d', 'CMF', 'CCI', 'PSAR', 'VWAP']].sort_values(by='Buy',ascending=False))

    # shares, bonds, indices, dividends, capitalizations = load_data()
    # mt1.dataframe(shares.head())
    header_rows = mt1.columns(5)
    headers = ['NAME', 'PRICE', 'DIVIDEND', 'ROI', 'ADVICE']
    for i in range(5):
        header_rows[i].write(headers[i])
    for i in range(5):
        columns = mt1.columns(5)
        columns[0].write(shares.loc[i, 'NAME'])
        columns[1].metric('', f"{shares.loc[i, 'CLOSE']:.0f}")
        columns[2].metric('💸💸💸',shares.loc[i, 'DIVIDEND'])
        value = shares.loc[i, 'DIVIDEND']
        if np.isnan(value):
            value = 0
        columns[3].metric('ROI',f"{value/shares.loc[i, 'CLOSE']:.1%}" )
        columns[4].write(shares.loc[i, 'Keep'])

    # mt1.dataframe(bonds.head())
    # mt1.dataframe(indices.head())
    # mt1.dataframe(dividends.head())
    # mt1.dataframe(capitalizations.head())
with mt2.form("stock_form"):
    # Input form for adding new stock
    mt2.subheader("Add a new stock to your portfolio")

    ticker = mt2.text_input("Stock Ticker", max_chars=5).upper()
    price = mt2.number_input("Price of Purchase", min_value=0.01, format="%.2f")
    quantity = mt2.number_input("Number of Stocks", min_value=1, format="%d")

    submit_button = st.form_submit_button("Add Stock")

    if submit_button:
        if ticker and price > 0 and quantity > 0:
            mt2.session_state.portfolio.append({
                'Ticker': ticker,
                'Price': price,
                'Quantity': quantity
            })
            st.success(f"Added {quantity} shares of {ticker} at ${price:.2f} each.")
        else:
            st.error("Please enter valid stock details.")

