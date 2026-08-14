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
    
    # Table name constants
    TABLE_SHARES = "stocks.shares"
    TABLE_DIVIDENDS = "stocks.dividends"
    TABLE_FINANCIALS = "stocks.financials"
    TABLE_RATINGS = "stocks.ratings"

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_shares(project_id: str = None, days: int = 90) -> pd.DataFrame:
        """
        Load shares/price data from BigQuery.
        
        Args:
            project_id: GCP project ID (defaults to env PROJECT_ID)
            days: Number of days of historical data to load
            
        Returns:
            DataFrame with columns: symbol, date, open, high, low, close, volume
        """
        if not project_id:
            project_id = get_project_id()
        
        if not project_id:
            st.error("PROJECT_ID environment variable not set")
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        query = f"""
            WITH latest_date AS (
                SELECT MAX(CAST(date AS DATE)) AS max_date 
                FROM `{project_id}.{DataManager.TABLE_SHARES}`
            )
            SELECT * FROM `{project_id}.{DataManager.TABLE_SHARES}`
            WHERE CAST(date AS DATE) BETWEEN 
                DATE_SUB((SELECT max_date FROM latest_date), INTERVAL {days} DAY)
                AND (SELECT max_date FROM latest_date)
            ORDER BY symbol, date DESC
        """
        
        try:
            shares = client.query(query).to_dataframe()
            
            # Debug output
            import sys
            print(f"[DEBUG] Raw shares from BigQuery: {len(shares)} rows", file=sys.stderr, flush=True)
            print(f"[DEBUG] Raw columns: {list(shares.columns)}", file=sys.stderr, flush=True)
            
            if shares.empty:
                st.warning("No shares data found in BigQuery. The table may be empty.")
                return shares
            
            # Convert column names to lowercase
            shares.columns = shares.columns.str.lower()
            print(f"[DEBUG] Converted columns: {list(shares.columns)}", file=sys.stderr, flush=True)
            
            return shares
        except Exception as e:
            st.error(f"Error loading shares: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            return pd.DataFrame()

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_dividends(project_id: str = None) -> pd.DataFrame:
        """
        Load latest dividend data from BigQuery.
        
        Args:
            project_id: GCP project ID (defaults to env PROJECT_ID)
            
        Returns:
            DataFrame with columns: symbol, date, dividend, payment_date
        """
        if not project_id:
            project_id = get_project_id()
        
        if not project_id:
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        query = f"""
            SELECT * FROM `{project_id}.{DataManager.TABLE_DIVIDENDS}`
            WHERE DATE(date) = (
                SELECT MAX(DATE(date)) 
                FROM `{project_id}.{DataManager.TABLE_DIVIDENDS}`
            )
        """
        
        try:
            dividends = client.query(query).to_dataframe()
            dividends.columns = dividends.columns.str.lower()
            return dividends
        except Exception as e:
            st.error(f"Error loading dividends: {str(e)}")
            return pd.DataFrame()

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_financials(project_id: str = None) -> pd.DataFrame:
        """
        Load financial statements data from BigQuery.
        
        Args:
            project_id: GCP project ID (defaults to env PROJECT_ID)
            
        Returns:
            DataFrame with columns: symbol, fiscal_year, revenue, net_income, 
                                   total_debt, cash_and_cash_equivalents, total_equity
        """
        if not project_id:
            project_id = get_project_id()
        
        if not project_id:
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        query = f"SELECT * FROM `{project_id}.{DataManager.TABLE_FINANCIALS}` ORDER BY symbol, fiscal_year DESC"
        
        try:
            financials = client.query(query).to_dataframe()
            financials.columns = financials.columns.str.lower()
            return financials
        except Exception as e:
            st.error(f"Error loading financials: {str(e)}")
            return pd.DataFrame()

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_ratings(project_id: str = None) -> pd.DataFrame:
        """
        Load ratings data from BigQuery.
        
        Args:
            project_id: GCP project ID (defaults to env PROJECT_ID)
            
        Returns:
            DataFrame with columns: symbol, rating_year, rating_short_term, rating_long_term
        """
        if not project_id:
            project_id = get_project_id()
        
        if not project_id:
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        query = f"""
            SELECT * FROM `{project_id}.{DataManager.TABLE_RATINGS}`
            WHERE rating_year = (
                SELECT MAX(rating_year) 
                FROM `{project_id}.{DataManager.TABLE_RATINGS}`
            )
        """
        
        try:
            ratings = client.query(query).to_dataframe()
            ratings.columns = ratings.columns.str.lower()
            return ratings
        except Exception as e:
            st.error(f"Error loading ratings: {str(e)}")
            return pd.DataFrame()

    @staticmethod
    @st.cache_data(ttl=3600)
    def load_data():
        """
        Load all data sources and merge into a single DataFrame.
        
        This is a convenience method that loads:
        - Shares (price data)
        - Dividends
        - Financials (latest fiscal year per symbol)
        - Ratings (latest year)
        
        Then generates technical indicators and trading signals.
        
        Returns:
            DataFrame with all merged data including signals and indicators
        """
        # Get project_id at runtime
        project_id = get_project_id()
        
        # Check for project_id
        if not project_id:
            st.error("PROJECT_ID environment variable not set")
            return pd.DataFrame()
        
        client = get_bigquery_client_safe()
        if client is None:
            return pd.DataFrame()
        
        # Load each data source separately
        shares = DataManager.load_shares(project_id)
        dividends = DataManager.load_dividends(project_id)
        financials = DataManager.load_financials(project_id)
        ratings = DataManager.load_ratings(project_id)
        
        # Check if shares loaded successfully
        if shares.empty:
            return pd.DataFrame()
        
        # Merge dividends
        print(f"[DEBUG] Before merge - shares: {shares.shape}, dividends: {dividends.shape}", file=sys.stderr, flush=True)
        result = shares.merge(
            dividends[["symbol", "dividend", "payment_date"]], 
            on='symbol', 
            how='left'
        )
        print(f"[DEBUG] After dividends merge: {result.shape}", file=sys.stderr, flush=True)
        
        # Merge financials (latest fiscal year per symbol)
        if financials is not None and not financials.empty:
            latest_financials = financials.loc[financials.groupby('symbol')['fiscal_year'].idxmax()]
            result = result.merge(
                latest_financials[['symbol', 'revenue', 'net_income', 'total_debt', 
                                   'cash_and_cash_equivalents', 'total_equity', 'fiscal_year']],
                left_on='symbol',
                right_on='symbol',
                how='left'
            )
        
        # Merge ratings
        if ratings is not None and not ratings.empty:
            result = result.merge(
                ratings[['symbol', 'rating_short_term', 'rating_long_term', 'rating_year']],
                left_on='symbol',
                right_on='symbol',
                how='left'
            )
        
        # Generate technical indicators and signals
        trading_system = TechnicalIndicatorTrading()
        
        # Debug: Check data before generating signals
        import sys
        print(f"[DEBUG] Data before generate_signals: {result.shape} rows", file=sys.stderr, flush=True)
        print(f"[DEBUG] Columns: {list(result.columns)}", file=sys.stderr, flush=True)
        print(f"[DEBUG] Unique symbols: {result['symbol'].nunique()}", file=sys.stderr, flush=True)
        
        # Check if we have enough data per symbol
        symbol_counts = result.groupby('symbol').size()
        print(f"[DEBUG] Rows per symbol: {symbol_counts.to_dict()}", file=sys.stderr, flush=True)
        
        # Check required columns
        required = ['symbol', 'open', 'high', 'low', 'close', 'volume', 'date']
        missing = [col for col in required if col not in result.columns]
        if missing:
            st.error(f"Missing required columns: {missing}")
            return pd.DataFrame()
        
        # Check if we have enough data (need 30+ rows per symbol)
        min_rows = symbol_counts.min()
        if min_rows < 30:
            st.warning(f"Insufficient data: minimum {min_rows} rows per symbol (need 30+)")
            st.info("Consider increasing the days parameter in load_shares()")
        
        try:
            result = trading_system.generate_signals(result, adaptive_weights=True)
        except ValueError as e:
            st.error(f"Error generating signals: {e}")
            st.info("This usually means insufficient data per symbol. Try loading more historical data.")
            return pd.DataFrame()
        
        # Calculate ROI
        result['roi'] = result['dividend'] / result['close']

        return result
