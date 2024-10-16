import streamlit as st
import pandas as pd
from util import trading_indicators as ti
import yaml
import duckdb as db


# Load configuration from YAML file
def load_config(config_path='config.yml'):
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    return config


config = load_config()
conn = db.connect(config['duckdb']['database'])


# Cache data for 1 day (86400 seconds)
@st.cache_data(ttl=86400)
def load_data():
    query1 = f"SELECT * FROM shares"
    query2 = f"SELECT * FROM bonds"
    query3 = f"SELECT * FROM indices"
    query4 = f"SELECT * FROM dividends"
    query5 = f"SELECT * FROM capitalizations"
    shares = conn.execute(query1).df()
    shares['EMA'] = ti.ema(shares['CLOSING_PRICE'])
    bonds = conn.execute(query2).df()
    return shares, bonds


# Streamlit app
st.title("Tradvisor")

# Load and display stock data

main_container = st.container()
mt1, mt2 = main_container.tabs(["Top 10 Stocks", "Tab 2"])
with mt1:
    shares, bonds = load_data()
    mt1.write(shares[['SYMBOL','NAME','CLOSING_PRICE','EMA']].head())
    # mt1.write(bonds.head())
with mt2:
    mt2.write("Coming soon !")

