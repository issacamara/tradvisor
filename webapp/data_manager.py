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


project_id = os.environ.get('PROJECT_ID')


class DataManager:
    """Manages stock data fetching and technical indicator calculations"""

    @staticmethod
    @st.cache_data(ttl=86400)
    def load_data():
        shares = None
        dividends = None
        financials = None
        ratings = None
        trading_system = TechnicalIndicatorTrading()
        
        # Use lowercase table names (BigQuery defaults to lowercase)
        query1 = f"""
                    WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM `{project_id}.stocks.shares`)
                    SELECT * FROM `{project_id}.stocks.shares`
                    WHERE CAST(date AS DATE) BETWEEN (SELECT max_date FROM latest_date) - INTERVAL '90' DAY
                        AND (SELECT max_date FROM latest_date)
                    ORDER BY date DESC
                """

        query4 = f"""
                    SELECT * FROM `{project_id}.stocks.dividends`
                    WHERE DATE(date) = (SELECT MAX(DATE(date)) FROM `{project_id}.stocks.dividends`)
                """
        
        # Load financials table
        query6 = f"SELECT * FROM `{project_id}.stocks.financials`"
        
        # Load ratings table (latest year)
        query7 = f"""
                    SELECT * FROM `{project_id}.stocks.ratings`
                    WHERE rating_year = (SELECT MAX(rating_year) FROM `{project_id}.stocks.ratings`)
                """
        
        client = getBigQueryClient()

        shares = client.query(query1).to_dataframe()
        dividends = client.query(query4).to_dataframe()
        financials = client.query(query6).to_dataframe()
        ratings = client.query(query7).to_dataframe()

        result = shares.merge(dividends[["SYMBOL", "DIVIDEND", "PAYMENT_DATE"]], on='SYMBOL', how='left')
        
        # Merge financials data
        if financials is not None and not financials.empty:
            # Get latest fiscal year for each symbol
            latest_financials = financials.loc[financials.groupby('symbol')['fiscal_year'].idxmax()]
            result = result.merge(
                latest_financials[['symbol', 'revenue', 'net_income', 'total_debt', 
                                   'cash_and_cash_equivalents', 'total_equity', 'fiscal_year']],
                left_on='SYMBOL',
                right_on='symbol',
                how='left'
            )
            result = result.drop(columns=['symbol'], errors='ignore')
        
        # Merge ratings data
        if ratings is not None and not ratings.empty:
            result = result.merge(
                ratings[['symbol', 'rating_short_term', 'rating_long_term', 'rating_year']],
                left_on='SYMBOL',
                right_on='symbol',
                how='left'
            )
            result = result.drop(columns=['symbol'], errors='ignore')
        
        result = trading_system.generate_signals(result, adaptive_weights=True)
        result['ROI'] = result['DIVIDEND'] / result['CLOSE']

        return result
    
    @staticmethod
    @st.cache_data(ttl=86400)
    def load_financials():
        """Load financial statements data"""
        query = f"SELECT * FROM `{project_id}.stocks.financials` ORDER BY symbol, fiscal_year DESC"
        client = getBigQueryClient()
        financials = client.query(query).to_dataframe()
        
        return financials
    
    @staticmethod
    @st.cache_data(ttl=86400)
    def load_ratings():
        """Load ratings data"""
        query = f"SELECT * FROM `{project_id}.stocks.ratings` ORDER BY symbol, rating_year DESC"
        client = getBigQueryClient()
        ratings = client.query(query).to_dataframe()
        
        return ratings
