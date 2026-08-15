"""View 5: Settings, BigQuery connection status & cache controls."""
import streamlit as st
from app.data.repository import get_bigquery_client
from app.data.schema import PROJECT_ID, SHARES_TABLE, DIVIDENDS_TABLE, FINANCIALS_TABLE, RATINGS_TABLE

def show():
    st.title("⚙️ System Settings & GCP Diagnostics")

    st.subheader("🔍 BigQuery Database Connection Status")
    try:
        client = get_bigquery_client()
        st.success(f"Successfully connected to GCP Project: `{PROJECT_ID}` using ADC.")

        tables = [SHARES_TABLE, DIVIDENDS_TABLE, FINANCIALS_TABLE, RATINGS_TABLE]
        for tbl in tables:
            query = f"SELECT COUNT(*) as cnt FROM `{tbl}`"
            cnt = client.query(query).to_dataframe().iloc[0]['cnt']
            st.write(f"• Table `{tbl}`: **{cnt:,}** records")

    except Exception as e:
        st.error(f"Error connecting to BigQuery: {str(e)}")

    st.subheader("🧹 Cache Management")
    if st.button("Clear Streamlit Data Cache"):
        st.cache_data.clear()
        st.success("Cache cleared successfully!")

if __name__ == "__main__":
    show()
