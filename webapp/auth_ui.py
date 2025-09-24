# auth_ui.py - Authentication UI Components

"""
Authentication UI Components for Trading Dashboard
Handles login, registration, and password reset interfaces
"""

import streamlit as st
import time
from typing import Dict
from database import DatabaseManager
from email_manager import EmailManager


class AuthUI:
    """Authentication user interface components"""

    def __init__(self, db_manager: DatabaseManager, email_manager: EmailManager):
        self.db = db_manager
        self.email = email_manager

    def show_login_page(self):
        """Display login page"""
        st.title("Login to Technical Trading Dashboard")
        # Check for reset token in URL
        query_params = st.query_params
        reset_token = query_params.get("reset_token", None)
        if reset_token:
            self.show_reset_password_form(reset_token)
            return

        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            with st.form("login_form"):
                st.subheader("Sign In")

                email = st.text_input("Email Address", placeholder="your.email@example.com")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                col_login, col_register = st.columns(2)

                with col_login:
                    login_submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

                with col_register:
                    register_submitted = st.form_submit_button("Create Account", use_container_width=True)

                forgot_submitted = st.form_submit_button("Forgot Password?", use_container_width=True)

                if login_submitted and email and password:
                    with st.spinner("Authenticating..."):
                        user = self.db.authenticate_user(email, password)
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.user = user
                            st.success("Login successful!")
                            # st.balloons()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Invalid email or password")

                elif register_submitted:
                    st.session_state.show_register = True
                    st.rerun()

                elif forgot_submitted and email:
                    self.handle_forgot_password(email)

                elif forgot_submitted and not email:
                    st.error("Please enter your email address first")

    def show_register_page(self):
        """Display registration page"""
        st.title("Create Your Trading Account")
        st.markdown("**Join thousands of traders using advanced technical analysis**")

        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            with st.form("register_form"):
                st.subheader("Sign Up")

                email = st.text_input("Email Address", placeholder="your.email@example.com")
                password = st.text_input("Password", type="password", placeholder="Create a strong password")
                confirm_password = st.text_input("Confirm Password", type="password",
                                                 placeholder="Confirm your password")

                # Password requirements
                with st.expander("Password Requirements"):
                    st.markdown("""
                    **Your password must contain:**
                    - At least 8 characters long
                    - At least one uppercase letter (A-Z)
                    - At least one lowercase letter (a-z)  
                    - At least one number (0-9)
                    - At least one special character (!@#$%^&*(),.?\":{}|<>)
                    """)

                col_register, col_back = st.columns(2)

                with col_register:
                    register_submitted = st.form_submit_button("Create Account", use_container_width=True,
                                                               type="primary")

                with col_back:
                    back_submitted = st.form_submit_button("Back to Login", use_container_width=True)

                if register_submitted:
                    self.handle_registration(email, password, confirm_password)

                elif back_submitted:
                    st.session_state.show_register = False
                    st.rerun()

    def show_reset_password_form(self, token: str):
        """Display password reset form"""
        st.title("Reset Your Password")

        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            with st.form("reset_form"):
                st.subheader("Enter New Password")

                new_password = st.text_input("New Password", type="password", placeholder="Enter new password")
                confirm_password = st.text_input("Confirm New Password", type="password",
                                                 placeholder="Confirm new password")

                with st.expander("Password Requirements"):
                    st.markdown("""
                    **Your password must contain:**
                    - At least 8 characters long
                    - At least one uppercase letter (A-Z)
                    - At least one lowercase letter (a-z)  
                    - At least one number (0-9)
                    - At least one special character
                    """)

                if st.form_submit_button("Reset Password", use_container_width=True, type="primary"):
                    if not new_password or not confirm_password:
                        st.error("Please fill in both password fields")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match")
                    else:
                        is_valid, message = self.db.validate_password(new_password)
                        if not is_valid:
                            st.error(f"{message}")
                        else:
                            with st.spinner("Resetting password..."):
                                if self.db.reset_password_with_token(token, new_password):
                                    st.success(
                                        "Password reset successfully! You can now login with your new password.")
                                    st.balloons()
                                    # Clear URL parameters
                                    st.query_params.clear()
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("Invalid or expired reset token")

    def handle_registration(self, email: str, password: str, confirm_password: str):
        """Handle user registration"""
        if not email or not password or not confirm_password:
            st.error("Please fill in all fields")
            return

        if not self.db.validate_email(email):
            st.error("Please enter a valid email address")
            return

        if password != confirm_password:
            st.error("Passwords do not match")
            return

        is_valid, message = self.db.validate_password(password)
        if not is_valid:
            st.error(f"{message}")
            return

        with st.spinner("Creating your account..."):
            if self.db.create_user(email, password):
                st.success("Account created successfully! You can now login.")
                st.balloons()
                st.session_state.show_register = False
                time.sleep(1)
                st.rerun()
            else:
                st.error("Account creation failed. Email may already be registered.")

    def handle_forgot_password(self, email: str):
        """Handle forgot password request"""
        if not self.db.validate_email(email):
            st.error("Please enter a valid email address")
            return

        with st.spinner("Processing password reset..."):
            user = self.db.get_user_by_email(email)
            if not user:
                # Don't reveal if email exists for security
                st.success("If an account with this email exists, a password reset link has been sent.")
                return

            reset_token = self.db.create_reset_token(email)
            # print("R=", reset_token)
            if reset_token:
                if self.email.send_reset_email(email, reset_token):
                    st.success("Password reset email sent! Check your inbox.")
                else:
                    st.error("Failed to send reset email. Please try again later.")
            else:
                st.error("Failed to generate reset token. Please try again.")

    def show_user_profile(self, user: Dict):
        """Display user profile in sidebar"""
        with st.sidebar:
            st.markdown("---")
            st.subheader("User Profile")

            # User info
            st.markdown(f"Email:** {user['email']}")
            st.markdown(f"Member since:** {user['created_at'].strftime('%B %Y')}")

            # Logout button
            if st.button("Logout", use_container_width=True, type="primary"):
                # Clear all session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.success("Logged out successfully!")
                time.sleep(1)
                st.rerun()