# email_manager.py - Email Manager

"""
Email Manager for Trading Dashboard
Handles password reset email notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, json
import streamlit as st

secrets_json_str = json.loads(os.getenv('TRADVISOR_GMAIL_ACC_SECRET'))
os.environ['SMTP_USERNAME'] = secrets_json_str['SMTP_USERNAME']
os.environ['SMTP_PASSWORD'] = secrets_json_str['SMTP_PASSWORD']

class EmailManager:
    """Email manager for password reset functionality"""

    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_username)

    def send_reset_email(self, to_email: str, reset_token: str, base_url: str = "http://localhost:8501") -> bool:
        """Send password reset email"""
        try:
            if not self.smtp_username or not self.smtp_password:
                st.error("Email service not configured. Please contact administrator.")
                return False

            reset_url = f"{base_url}/?reset_token={reset_token}"

            subject = "Password Reset - Technical Trading Dashboard"

            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <div style="text-align: center; margin-bottom: 40px;">
                        <h1 style="color: #2E86AB; margin: 0; font-size: 28px;">ðŸ“ˆ Trading Dashboard</h1>
                        <p style="color: #666; margin-top: 10px;">Password Reset Request</p>
                    </div>

                    <h2 style="color: #333; margin-bottom: 20px;">Hello!</h2>

                    <p style="color: #555; line-height: 1.6; margin-bottom: 20px;">
                        You have requested a password reset for your Technical Trading Dashboard account.
                    </p>

                    <p style="color: #555; line-height: 1.6; margin-bottom: 30px;">
                        Click the button below to reset your password:
                    </p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="background-color: #4CAF50; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                            ðŸ”„ Reset Password
                        </a>
                    </div>

                    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0; color: #856404;">
                            â° <strong>Important:</strong> This link will expire in 1 hour for security reasons.
                        </p>
                    </div>

                    <p style="color: #555; line-height: 1.6; margin-top: 30px;">
                        If you didn't request this password reset, please ignore this email. Your account remains secure.
                    </p>

                    <div style="border-top: 1px solid #eee; margin-top: 40px; padding-top: 20px; text-align: center;">
                        <p style="color: #999; font-size: 14px; margin: 0;">
                            Best regards,<br>
                            <strong>Technical Trading Dashboard Team</strong>
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email

            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            return True

        except Exception as e:
            st.error(f"Error sending email: {str(e)}")
            return False