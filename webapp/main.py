"""
TRADVISOR - Main Entry Point
BRVM Trading Dashboard with Multi-Page Architecture

This is the main entry point for the Streamlit application.
Authentication is handled at this level, and pages are rendered via Streamlit's multi-page system.
"""

import os
import sys
import logging

# ULTRA EARLY DEBUG - stderr goes to Cloud Run logs
print(f"[DEBUG] main.py starting...", file=sys.stderr, flush=True)
print(f"[DEBUG] PROJECT_ID: {os.environ.get('PROJECT_ID', 'NOT SET')}", file=sys.stderr, flush=True)
print(f"[DEBUG] Python: {sys.version}", file=sys.stderr, flush=True)

import streamlit as st

# Also set up logging to stderr
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

# Import core modules (lazy loaded to avoid BigQuery errors locally)
# from database import DatabaseManager
# from email_manager import EmailManager



def apply_global_css():
    """Apply global CSS styling"""
    st.markdown("""
    <style>
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Custom metric styling */
    div[data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e1e5e9;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* Success/Error message styling */
    .stAlert {
        border-radius: 10px;
        border-left: 4px solid;
        font-weight: 500;
    }

    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    /* Form styling */
    .stForm {
        border: 1px solid #e1e5e9;
        border-radius: 15px;
        padding: 2rem;
        background-color: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)


def main():
    """Main application entry point"""

    # Apply global CSS
    apply_global_css()

    # Show branding in sidebar
    with st.sidebar:
        st.markdown("---")
        st.subheader("TRADVISOR")
        st.markdown("**BRVM Trading Dashboard 3**")
        st.markdown("---")

    # The actual dashboard content is in the pages/ directory
    # Streamlit automatically handles page routing

    # Footer
    st.markdown("---")
    st.markdown("**Data Source:** BRVM | **Powered by:** Bayesian Ensemble Technical Analysis")


if __name__ == "__main__":
    main()