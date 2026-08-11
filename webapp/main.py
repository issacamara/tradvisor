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
    import sys
    import os
    print("[DEBUG] main() function started", file=sys.stderr, flush=True)
    
    # Apply global CSS
    apply_global_css()

    # Check authentication
    if not st.session_state.get('authenticated', False):
        st.title("TRADVISOR - Login Required")
        st.warning("Please log in to access the dashboard")
        
        with st.form("login_form"):
            st.subheader("Quick Login (Demo)")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login", type="primary"):
                # Demo: accept any login for now
                st.session_state.authenticated = True
                st.session_state.user = {"email": email, "created_at": "2024-01-01"}
                st.rerun()
        
        st.markdown("---")
        st.caption("Contact admin for access")
        return

    # Show branding in sidebar
    with st.sidebar:
        st.markdown("---")
        st.subheader("TRADVISOR")
        st.markdown("**BRVM Trading Dashboard**")
        st.markdown(f"Environment: **{os.environ.get('ENVIRONMENT', 'prod')}**")
        st.markdown(f"Project: **{os.environ.get('PROJECT_ID', 'N/A')}**")
        st.markdown("---")
        
        # Logout button
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # The actual dashboard content is in the pages/ directory
    # Streamlit automatically handles page routing

    # Footer
    st.markdown("---")
    st.markdown("**Data Source:** BRVM | **Powered by:** Bayesian Ensemble Technical Analysis")


if __name__ == "__main__":
    main()