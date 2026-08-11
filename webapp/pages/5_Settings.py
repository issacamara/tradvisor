"""
Page 5: Settings
Configuration, API keys, theme settings
"""

import streamlit as st
import os


def apply_page_css():
    """Apply page-specific CSS"""
    st.markdown("""
    <style>
    .settings-section {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .settings-header {
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    .env-var {
        background-color: #e9ecef;
        padding: 0.5rem;
        border-radius: 5px;
        font-family: monospace;
        margin: 0.25rem 0;
    }
    .status-active {
        color: #28a745;
        font-weight: bold;
    }
    .status-inactive {
        color: #dc3545;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)


def show():
    """Render the Settings page"""
    apply_page_css()
    
    # Page header
    st.markdown("# Settings")
    st.markdown("### Configuration and preferences")
    st.markdown("---")
    
    # Environment Status
    st.markdown("### Environment Status")
    
    project_id = os.environ.get('PROJECT_ID')
    # Determine environment based on PROJECT_ID
    if project_id and 'dev' in project_id.lower():
        environment = 'Development'
    elif project_id and 'prod' in project_id.lower():
        environment = 'Production'
    else:
        environment = os.environ.get('ENVIRONMENT', 'GCP')
    
    col_env1, col_env2, col_env3 = st.columns(3)
    
    with col_env1:
        st.metric("Environment", environment)
    
    with col_env2:
        st.metric("Project ID", project_id)
    
    with col_env3:
        # Check BigQuery connection
        try:
            from helper import getBigQueryClient
            client = getBigQueryClient()
            st.metric("BigQuery", "Connected", delta="OK")
        except Exception as e:
            st.metric("BigQuery", "Not Available", delta="Check credentials")
    
    # Data Source Settings
    st.markdown("---")
    st.markdown("### Data Source")
    
    st.markdown("""
    <div class="settings-section">
        <p>The application runs on GCP using BigQuery:</p>
        <ul>
            <li><strong>GCP Mode:</strong> Uses BigQuery for all data storage</li>
            <li><strong>PROJECT_ID</strong> environment variable must be set</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Display environment variables
    st.markdown("### Environment Variables")
    
    env_vars = [
        ("PROJECT_ID", "GCP Project ID for BigQuery"),
        ("GOOGLE_APPLICATION_CREDENTIALS", "Path to GCP service account JSON"),
        ("GOOGLE_APPLICATION_CREDENTIALS_JSON", "GCP credentials as JSON string"),
    ]
    
    for var, description in env_vars:
        value = os.environ.get(var, "Not set")
        if var == "GOOGLE_APPLICATION_CREDENTIALS_JSON" and value != "Not set":
            value = "[JSON string set]"
        
        st.markdown(f"""
        <div class="env-var">
            <strong>{var}</strong>: {value}<br>
            <small>{description}</small>
        </div>
        """, unsafe_allow_html=True)
    
    # Cache Settings
    st.markdown("---")
    st.markdown("### Cache Settings")
    
    st.markdown("""
    <div class="settings-section">
        <p><strong>Data Cache TTL:</strong> 24 hours (86400 seconds)</p>
        <p>Data is cached to improve performance. The cache is automatically invalidated after 24 hours.</p>
        <p>To clear cache, restart the application.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Technical Indicator Settings
    st.markdown("---")
    st.markdown("### Technical Indicator Weights")
    
    st.markdown("""
    <div class="settings-section">
        <p>Default indicator weights (can be customized in code):</p>
        <table>
            <tr><th>Indicator</th><th>Weight</th><th>Purpose</th></tr>
            <tr><td>RSI</td><td>15%</td><td>Momentum assessment</td></tr>
            <tr><td>MACD</td><td>15%</td><td>Trend confirmation</td></tr>
            <tr><td>VWAP</td><td>12%</td><td>Institutional benchmark</td></tr>
            <tr><td>Bollinger Bands</td><td>12%</td><td>Volatility adaptive</td></tr>
            <tr><td>MA</td><td>10%</td><td>Basic trend</td></tr>
            <tr><td>EMA</td><td>10%</td><td>Responsive trend</td></tr>
            <tr><td>CMF</td><td>8%</td><td>Volume confirmation</td></tr>
            <tr><td>CCI</td><td>8%</td><td>Cyclical trends</td></tr>
            <tr><td>Stochastic</td><td>5%</td><td>Volatile signals</td></tr>
            <tr><td>PSAR</td><td>5%</td><td>Trend reversal</td></tr>
        </table>
        <p><em>Weights automatically adapt based on market conditions (volatility and trend strength).</em></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Passive Income Scoring
    st.markdown("---")
    st.markdown("### Passive Income Scoring Criteria")
    
    st.markdown("""
    <div class="settings-section">
        <p><strong>Yield Score (40 pts):</strong></p>
        <ul>
            <li>> 8% dividend yield = 20 pts</li>
            <li>5-8% dividend yield = 15 pts</li>
            <li>< 5% dividend yield = 5 pts</li>
        </ul>
        <p><strong>Sustainability (30 pts):</strong></p>
        <ul>
            <li>ROE > 15% = 15 pts</li>
            <li>Payout ratio < 70% = 15 pts</li>
        </ul>
        <p><strong>Stability (20 pts):</strong></p>
        <ul>
            <li>Debt-to-Equity < 1 = 10 pts</li>
            <li>Credit Rating AA- or better = 10 pts</li>
        </ul>
        <p><strong>Growth (10 pts):</strong></p>
        <ul>
            <li>Net Margin > 10% = 10 pts</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # About Section
    st.markdown("---")
    st.markdown("### About TRADVISOR")
    
    st.markdown("""
    <div class="settings-section">
        <p><strong>TRADVISOR</strong> - BRVM Trading Dashboard</p>
        <p>Focused on passive income through dividends from West African Stock Exchange (BRVM) investments.</p>
        <p><strong>Target:</strong> 2,000 EUR/month passive income</p>
        <p><strong>Starting Capital:</strong> 100,000 EUR</p>
        <p><strong>Investment Horizon:</strong> 5+ years</p>
        <hr>
        <p><small>Version: 1.0.0 | Powered by Streamlit | Data: BRVM</small></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Danger Zone
    st.markdown("---")
    st.markdown("### Danger Zone")
    
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        if st.button("Clear All Cache", type="primary"):
            st.cache_data.clear()
            st.success("Cache cleared! Please refresh the page.")
    
    with col_d2:
        st.info("Note: Cache automatically expires after 24 hours.")
    
    # Footer
    st.markdown("---")
    st.caption("Settings are configured via environment variables. See README for deployment instructions.")
