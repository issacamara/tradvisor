"""BigQuery Data Repository with 24-hour Streamlit caching and ADC support."""
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from app.data.schema import PROJECT_ID, SHARES_TABLE, DIVIDENDS_TABLE, FINANCIALS_TABLE, RATINGS_TABLE

def get_bigquery_client() -> bigquery.Client:
    """Initializes BigQuery client using Application Default Credentials (ADC)."""
    return bigquery.Client(project=PROJECT_ID)

@st.cache_data(ttl=86400)
def get_all_symbols() -> list[str]:
    """Fetches unique trading symbols available across shares and financials tables."""
    client = get_bigquery_client()
    query = f"""
        SELECT DISTINCT SYMBOL 
        FROM `{SHARES_TABLE}` 
        WHERE SYMBOL IS NOT NULL 
        ORDER BY SYMBOL
    """
    df = client.query(query).to_dataframe()
    return df['SYMBOL'].tolist() if not df.empty else []

@st.cache_data(ttl=86400)
def get_all_companies() -> list[str]:
    """Fetches company names available across stocks."""
    client = get_bigquery_client()
    query = f"""
        SELECT DISTINCT NAME 
        FROM `{SHARES_TABLE}` 
        WHERE NAME IS NOT NULL 
    """
    df = client.query(query).to_dataframe()
    return df['NAME'].tolist() if not df.empty else []

@st.cache_data(ttl=86400)
def get_latest_prices() -> pd.DataFrame:
    """Retrieves the most recent stock closing price, volume, and 1-day change."""
    client = get_bigquery_client()
    query = f"""
        WITH ranked_shares AS (
            SELECT 
                SYMBOL, 
                DATE, 
                CLOSE, 
                VOLUME,
                LAG(CLOSE) OVER (PARTITION BY SYMBOL ORDER BY DATE ASC) as PREV_CLOSE,
                ROW_NUMBER() OVER (PARTITION BY SYMBOL ORDER BY DATE DESC) as rn
            FROM `{SHARES_TABLE}`
        )
        SELECT 
            SYMBOL, 
            DATE, 
            CLOSE, 
            VOLUME,
            PREV_CLOSE,
            SAFE_DIVIDE(CLOSE - PREV_CLOSE, PREV_CLOSE) * 100 as CHANGE_PCT
        FROM ranked_shares
        WHERE rn = 1
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=86400)
def get_stock_price_history(symbol: str, days: int = 1800) -> pd.DataFrame:
    """Retrieves up to 5 years (1800 days) of OHLCV daily trading data for a symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT SYMBOL, DATE, OPEN, HIGH, LOW, CLOSE, VOLUME
        FROM `{SHARES_TABLE}`
        WHERE SYMBOL = @symbol
        ORDER BY DATE ASC
        LIMIT @days
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("symbol", "STRING", symbol),
            bigquery.ScalarQueryParameter("days", "INT64", days),
        ]
    )
    df = client.query(query, job_config=job_config).to_dataframe()
    if not df.empty and 'DATE' in df.columns:
        df['DATE'] = pd.to_datetime(df['DATE'])
    return df

@st.cache_data(ttl=86400)
def get_stock_financials(symbol: str) -> pd.DataFrame:
    """Retrieves up to 5 years of financial statement records for a symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT 
            symbol, fiscal_year, revenue, net_income, total_debt,
            cash_and_cash_equivalents, total_equity, announcement_date, document_link
        FROM `{FINANCIALS_TABLE}`
        WHERE symbol = @symbol
        ORDER BY fiscal_year DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("symbol", "STRING", symbol)]
    )
    return client.query(query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=86400)
def get_stock_dividends(symbol: str) -> pd.DataFrame:
    """Retrieves historical dividend payments for a symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, dividend, payment_date, date
        FROM `{DIVIDENDS_TABLE}`
        WHERE symbol = @symbol
        ORDER BY payment_date DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("symbol", "STRING", symbol)]
    )
    return client.query(query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=86400)
def get_stock_ratings(symbol: str) -> pd.DataFrame:
    """Retrieves credit rating history for a stock symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, rating_year, rating_short_term, rating_long_term
        FROM `{RATINGS_TABLE}`
        WHERE symbol = @symbol
        ORDER BY rating_year DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("symbol", "STRING", symbol)]
    )
    return client.query(query, job_config=job_config).to_dataframe()
