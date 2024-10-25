import sys
sys.path.append('..')
import duckdb as db
import pandas as pd
import streamlit as st
import yaml
import numpy as np
import util.trading as tr


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

    query2 = f"SELECT * FROM bonds"
    query3 = f"SELECT * FROM indices"
    query4 = f"SELECT * FROM dividends"
    query5 = f"SELECT * FROM capitalizations"
    shares = conn.execute(query1).df()
    bonds = conn.execute(query2).df()
    indices = conn.execute(query3).df()
    dividends = conn.execute(query4).df()
    capitalizations = conn.execute(query5).df()

    shares = pd.merge(shares, dividends[["SYMBOL","DIVIDEND","PAYMENT_DATE"]], on='SYMBOL', how='left')

    # shares = tr.get_trading_decisions(shares)


    return shares, bonds, indices, dividends, capitalizations


# Streamlit app
st.title("Tradvisor")

# Load and display stock data

main_container = st.container()
mt1, mt2 = main_container.tabs(["Top 10 Stocks", "Tab 2"])
with mt1:
    shares, bonds, indices, dividends, capitalizations = load_data()
    # mt1.dataframe(shares.head())
    for i in range(5):
        columns = mt1.columns(5)
        columns[0].write(shares.loc[i, 'NAME'])
        columns[1].metric('💸💸💸', f"{shares.loc[i, 'CLOSE']:.0f}")
        columns[2].metric('💸💸💸',shares.loc[i, 'DIVIDEND'])
        value = shares.loc[i, 'DIVIDEND']
        if np.isnan(value):
            value = 0
        columns[3].metric('ROI',f"{value/shares.loc[i, 'CLOSE']:.1%}" )
        columns[4].write(shares.loc[i, 'PAYMENT_DATE'])

    # mt1.dataframe(bonds.head())
    # mt1.dataframe(indices.head())
    # mt1.dataframe(dividends.head())
    # mt1.dataframe(capitalizations.head())
with mt2:
    mt2.write("Coming soon !")

