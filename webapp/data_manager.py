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


def get_project_id():
    """Get project ID dynamically at runtime"""
    return os.environ.get('PROJECT_ID')


def get_bigquery_client_safe():
    """Get BigQuery client with error handling for local development"""
    try:
        return getBigQueryClient()
    except Exception as e:
        st.error(f"BigQuery connection error: {str(e)}")
        st.info("Note: Data loading requires GCP credentials. Run with `gcloud auth application-default login` locally, or deploy to Cloud Run for production.")
        return None


class DataManager:
    """Manages stock data fetching and technical indicator calculations"""

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_data():
        # Get project_id at runtime
        project_id = get_project_id()
        
        # Check for project_id
        if not project_id:
            st.error("PROJECT_ID environment variable not set")
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        shares = None
        dividends = None
        financials = None
        ratings = None
        trading_system = TechnicalIndicatorTrading()
        
        # Use lowercase table names (BigQuery defaults to lowercase)
        # Fixed: BigQuery uses DATE_SUB instead of - INTERVAL
        query1 = f"""
                    WITH latest_date AS (SELECT MAX(CAST(date AS DATE)) AS max_date FROM `{project_id}.stocks.shares`)
                    SELECT * FROM `{project_id}.stocks.shares`
                    WHERE CAST(date AS DATE) BETWEEN DATE_SUB((SELECT max_date FROM latest_date), INTERVAL 90 DAY)
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
        
        try:
            st.info(f"Executing query1 (shares): {query1[:200]}...")
            shares = client.query(query1).to_dataframe()
            st.success(f"Shares query returned: {len(shares)} rows")
            
            st.info(f"Executing query4 (dividends): {query4[:200]}...")
            dividends = client.query(query4).to_dataframe()
            st.success(f"Dividends query returned: {len(dividends)} rows")
            
            st.info(f"Executing query6 (financials)")
            financials = client.query(query6).to_dataframe()
            st.success(f"Financials query returned: {len(financials)} rows")
            
            st.info(f"Executing query7 (ratings)")
            ratings = client.query(query7).to_dataframe()
            st.success(f"Ratings query returned: {len(ratings)} rows")
            
        except Exception as e:
            st.error(f"Error querying BigQuery: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            return pd.DataFrame()

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
    @st.cache_data(ttl=3600)
    def load_financials():
        """Load financial statements data"""
        project_id = get_project_id()
        
        if not project_id:
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
            
        query = f"SELECT * FROM `{project_id}.stocks.financials` ORDER BY symbol, fiscal_year DESC"
        try:
            financials = client.query(query).to_dataframe()
        except Exception as e:
            st.error(f"Error loading financials: {str(e)}")
            return pd.DataFrame()
        
        return financials
    
    @staticmethod
    @st.cache_data(ttl=3600)
    def load_ratings():
        """Load ratings data"""
        project_id = get_project_id()
        
        if not project_id:
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
            
        query = f"SELECT * FROM `{project_id}.stocks.ratings` ORDER BY symbol, rating_year DESC"
        try:
            ratings = client.query(query).to_dataframe()
        except Exception as e:
            st.error(f"Error loading ratings: {str(e)}")
            return pd.DataFrame()
        
        return ratings
