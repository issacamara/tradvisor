# data_manager.py - Stock Data Manager

"""
Data Manager for Trading Dashboard
Handles stock data fetching and technical indicator calculations
"""

import os
import pandas as pd
import streamlit as st
from trading import TechnicalIndicatorTrading
from helper import getBigQueryClient
import duckdb


project_id = os.environ.get('PROJECT_ID')

if project_id:
    ENVIRONMENT = 'gcp'
else:
    ENVIRONMENT = "on-premise"

class DataManager:
    """Manages stock data fetching and technical indicator calculations"""

    @staticmethod
    @st.cache_data(ttl=86400)
    def load_data():
        shares = None
        dividends = None
        trading_system = TechnicalIndicatorTrading()
        if ENVIRONMENT == 'gcp':
            query1 = f"""
                        WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM `{project_id}.stocks.SHARES`)
                        SELECT * FROM `{project_id}.stocks.SHARES`
                        WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                            AND (SELECT max_date FROM latest_date)
                        ORDER BY date DESC
                    """

            query2 = f"SELECT * FROM bonds"
            query3 = f"SELECT * FROM indices"
            query4 = f"""
                        SELECT * FROM `{project_id}.stocks.DIVIDENDS`
                        WHERE DATE(date) = (SELECT MAX(DATE(date)) FROM `{project_id}.stocks.DIVIDENDS`)
                    """
            query5 = f"SELECT * FROM capitalizations"
            client = getBigQueryClient()

            shares = client.query(query1).to_dataframe()
            dividends = client.query(query4).to_dataframe()

        if ENVIRONMENT == 'on-premise':
            query1 = f"""
                        WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM SHARES)
                        SELECT * FROM SHARES
                        WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                            AND (SELECT max_date FROM latest_date)
                        ORDER BY date DESC
                    """
            query4 = f"""
                            SELECT * FROM DIVIDENDS
                            WHERE CAST(date as DATE) = (SELECT MAX(CAST(date as DATE)) FROM DIVIDENDS)
                        """

            conn = duckdb.connect('database/financial_assets.db')
            shares = conn.execute(query1).df()
            dividends = conn.execute(query4).df()

        # bonds = conn.execute(query2).df()
        # indices = conn.execute(query3).df()

        # capitalizations = conn.execute(query5).df()

        result = shares.merge(dividends[["SYMBOL", "DIVIDEND", "PAYMENT_DATE"]], on='SYMBOL', how='left')
        # result = tr.get_trading_decisions(result)
        result = trading_system.generate_signals(result, adaptive_weights=True)
        result['ROI'] = result['DIVIDEND'] / result['CLOSE']

        # return shares, bonds, indices, dividends, capitalizations
        return result