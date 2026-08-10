"""
TRADVISOR - Main Entry Point
BRVM Trading Dashboard with Multi-Page Architecture

This is the main entry point for the Streamlit application.
Authentication is handled at this level, and pages are rendered via Streamlit's multi-page system.
"""

import os

import streamlit as st

# Import core modules
from database import DatabaseManager
from email_manager import EmailManager
from auth_ui import AuthUI


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


@st.cache_resource
def init_components():
    """Initialize all dashboard components"""
    db_manager = DatabaseManager()
    email_manager = EmailManager()
    auth_ui = AuthUI(db_manager, email_manager)

    return {
        'db': db_manager,
        'email': email_manager,
        'auth_ui': auth_ui,
    }


def show_authentication_flow(components):
    """Handle authentication flow"""
    auth_ui = components['auth_ui']

    if st.session_state.get('show_register', False):
        auth_ui.show_register_page()
    else:
        auth_ui.show_login_page()


def show_main_dashboard(components, user):
    """Show the main trading dashboard (redirects to pages)"""
    auth_ui = components['auth_ui']
    # Show user profile in sidebar
    auth_ui.show_user_profile(user)

    # The actual dashboard content is in the pages/ directory
    # Streamlit automatically handles page routing
def main():
    """Main application entry point"""

    # Apply global CSS
    apply_global_css()

    # Initialize components
    components = init_components()

    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None

    # ============================================================
    # Authentication setting - controlled by environment variable
    # Set AUTH_DISABLED=false to enable authentication
    # Currently disabled for quick testing - will re-enable with new auth page
    # ============================================================
    AUTH_DISABLED = os.environ.get('AUTH_DISABLED', 'true').lower() == 'true'

    if AUTH_DISABLED:
        # Bypass authentication - show dashboard directly
        # Create a dummy user for testing
        if not st.session_state.user:
            st.session_state.user = {'email': 'test@tradvisor.com', 'name': 'Test User'}
        st.session_state.authenticated = True
        show_main_dashboard(components, st.session_state.user)
    elif st.session_state.authenticated and st.session_state.user:
        show_main_dashboard(components, st.session_state.user)
    else:
        show_authentication_flow(components)

    # Footer
    if st.session_state.authenticated:
        st.markdown("---")
        st.markdown("**Data Source:** BRVM | **Powered by:** Bayesian Ensemble Technical Analysis")
if __name__ == "__main__":
    main()