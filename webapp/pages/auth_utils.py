# Authentication utility for pages
import streamlit as st


def require_auth():
    """
    Decorator/function to require authentication for a page.
    Call this at the beginning of each page's show() function.
    """
    if not st.session_state.get('authenticated', False):
        st.warning("Please log in to access this page.")
        st.stop()
        return False
    return True


def get_current_user():
    """Get the current authenticated user"""
    return st.session_state.get('user')
