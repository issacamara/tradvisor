"""BigQuery Data Repository with 24-hour Streamlit caching and ADC support."""
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from app.data.schema import PROJECT_ID, SHARES_TABLE, DIVIDENDS_TABLE, FINANCIALS_TABLE, RATINGS_TABLE, COMPANIES_TABLE

def get_bigquery_client() -> bigquery.Client:
    """Initializes BigQuery client using Application Default Credentials (ADC)."""
    return bigquery.Client(project=PROJECT_ID)

@st.cache_data(ttl=86400)
def get_all_symbols() -> list[str]:
    """Fetches unique trading symbols available across shares and financials tables."""
    client = get_bigquery_client()
    query = f"""
        SELECT DISTINCT symbol 
        FROM `{SHARES_TABLE}` 
        WHERE symbol IS NOT NULL 
        ORDER BY symbol
    """
    df = client.query(query).to_dataframe()
    return df['symbol'].tolist() if not df.empty else []

@st.cache_data(ttl=86400)
def get_all_companies() -> list[str]:
    """Fetches company names available across stocks."""
    client = get_bigquery_client()
    query = f"""
        SELECT DISTINCT symbol, name 
        FROM `{SHARES_TABLE}` 
        WHERE symbol IS NOT NULL 
    """
    df = client.query(query).to_dataframe()
    return df.set_index('symbol')['name'].to_dict() if not df.empty else {}

@st.cache_data(ttl=86400)
def get_latest_prices() -> pd.DataFrame:
    """Retrieves the most recent stock closing price, volume, and 1-day change."""
    client = get_bigquery_client()
    query = f"""
        WITH ranked_shares AS (
            SELECT 
                symbol, 
                date, 
                close, 
                volume,
                LAG(close) OVER (PARTITION BY symbol ORDER BY date ASC) as prev_close,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
            FROM `{SHARES_TABLE}`
        )
        SELECT 
            symbol, 
            date, 
            close, 
            volume,
            prev_close,
            SAFE_DIVIDE(close - prev_close, prev_close) * 100 as change_pct
        FROM ranked_shares
        WHERE rn = 1
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=86400)
def get_stock_price_history(symbol: str, days: int = 1800) -> pd.DataFrame:
    """Retrieves up to 5 years (1800 days) of OHLCV daily trading data for a symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, date, open, high, low, close, volume
        FROM `{SHARES_TABLE}`
        WHERE symbol = @symbol
        ORDER BY date ASC
        LIMIT @days
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("symbol", "STRING", symbol),
            bigquery.ScalarQueryParameter("days", "INT64", days),
        ]
    )
    df = client.query(query, job_config=job_config).to_dataframe()
    if not df.empty and 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
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
        SELECT symbol, dividend, payment_date, fiscal_year
        FROM `{DIVIDENDS_TABLE}`
        WHERE symbol = @symbol
        ORDER BY fiscal_year DESC, payment_date DESC
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

@st.cache_data(ttl=86400)
def get_all_companies_with_sector() -> pd.DataFrame:
    """Retrieves all companies with sector classification."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, name, sector, activity_description
        FROM `{COMPANIES_TABLE}`
        ORDER BY sector, name
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=86400)
def get_company_by_symbol(symbol: str) -> pd.DataFrame:
    """Retrieves company details by symbol."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, name, sector, activity_description
        FROM `{COMPANIES_TABLE}`
        WHERE symbol = @symbol
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("symbol", "STRING", symbol)]
    )
    return client.query(query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=86400)
def get_companies_by_sector(sector: str) -> pd.DataFrame:
    """Retrieves all companies in a specific sector."""
    client = get_bigquery_client()
    query = f"""
        SELECT symbol, name, sector, activity_description
        FROM `{COMPANIES_TABLE}`
        WHERE sector = @sector
        ORDER BY name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("sector", "STRING", sector)]
    )
    return client.query(query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=86400)
def get_all_sectors() -> list[str]:
    """Retrieves all unique sectors."""
    client = get_bigquery_client()
    query = f"""
        SELECT DISTINCT sector
        FROM `{COMPANIES_TABLE}`
        WHERE sector IS NOT NULL
        ORDER BY sector
    """
    df = client.query(query).to_dataframe()
    return df['sector'].tolist() if not df.empty else []
