# database.py - BigQuery Database Manager

"""
Database Manager for Trading Dashboard Authentication
Handles BigQuery operations for user management
"""

import hashlib
import secrets
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
from google.cloud import bigquery
from google.oauth2 import service_account
import streamlit as st
import os
import json
import re
from helper import create_gauge_chart, create_signal_pie_chart, create_stock_chart, getBigQueryClient
import duckdb as db

DB_BACKEND = os.getenv("DB_BACKEND", "duckdb").lower()

"""
Database Manager for Trading Dashboard Authentication
Adaptive backend: DuckDB (on-premise) or BigQuery (cloud) depending on environment variable DB_BACKEND
"""

import os
import json
import re
import hashlib
import secrets
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
import streamlit as st

# DB_BACKEND = os.getenv("DB_BACKEND", "duckdb").lower()
ENVIRONMENT = None
# DuckDB Implementation (local/on-premise)
if os.environ.get('PROJECT_ID'):
    ENVIRONMENT = 'gcp'
else:
    ENVIRONMENT = "on-premise"
if ENVIRONMENT == "on-premise":
    import duckdb

    class DatabaseManager:
        def __init__(self):
            self.db_path = os.getenv("DUCKDB_PATH", "trading_dashboard.db")
            self.conn = duckdb.connect("database/users.db")
            self._ensure_tables()

        def _ensure_tables(self):
            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR,
                email VARCHAR UNIQUE,
                password_hash VARCHAR,
                salt VARCHAR,
                created_at TIMESTAMP,
                last_login TIMESTAMP,
                reset_token VARCHAR,
                reset_token_expires TIMESTAMP,
                preferences VARCHAR
            );
            '''
            self.conn.execute(create_table_sql)

        def create_user(self, email: str, password: str) -> bool:
            if self.get_user_by_email(email):
                return False
            salt = secrets.token_hex(32)
            password_hash = self._hash_password(password, salt)
            user_id = secrets.token_hex(16)
            created_at = datetime.utcnow()
            try:
                self.conn.execute(
                    '''INSERT INTO users (user_id, email, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)''',
                    [user_id, email.lower(), password_hash, salt, created_at]
                )
                return True
            except Exception as e:
                st.error(f"Error creating user (DuckDB): {str(e)}")
                return False

        def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
            user = self.get_user_by_email(email)
            if not user:
                return None
            password_hash = self._hash_password(password, user['salt'])
            if password_hash == user['password_hash']:
                self.conn.execute(
                    'UPDATE users SET last_login=? WHERE email=?',
                    [datetime.utcnow(), email.lower()]
                )
                return {
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'created_at': user['created_at']
                }
            return None

        def get_user_by_email(self, email: str) -> Optional[Dict]:
            try:
                result = self.conn.execute(
                    'SELECT * FROM users WHERE email=? LIMIT 1', [email.lower()]
                ).fetchone()
                if result:
                    columns = [x[0] for x in self.conn.description]
                    return dict(zip(columns, result))
                return None
            except Exception as e:
                st.error(f"Error retrieving user from DuckDB: {str(e)}")
                return None

        def _update_last_login(self, email: str):
            self.conn.execute(
                'UPDATE users SET last_login=? WHERE email=?',
                [datetime.utcnow(), email.lower()]
            )

        def create_reset_token(self, email: str) -> Optional[str]:
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(hours=1)
            self.conn.execute(
                'UPDATE users SET reset_token=?, reset_token_expires=? WHERE email=?',
                [token, expires, email.lower()]
            )
            user = self.get_user_by_email(email)
            return token if user and user.get("reset_token") == token else None

        def reset_password_with_token(self, token: str, new_password: str) -> bool:
            user = self.conn.execute(
                'SELECT email, reset_token_expires FROM users WHERE reset_token=? LIMIT 1', [token]
            ).fetchone()
            if not user:
                return False
            email, expires = user
            if expires < datetime.utcnow():
                return False
            salt = secrets.token_hex(32)
            password_hash = self._hash_password(new_password, salt)
            self.conn.execute(
                'UPDATE users SET password_hash=?, salt=?, reset_token=NULL, reset_token_expires=NULL WHERE email=?',
                [password_hash, salt, email]
            )
            return True

        @staticmethod
        def _hash_password(password: str, salt: str) -> str:
            return hashlib.sha256((password + salt).encode()).hexdigest()

        @staticmethod
        def validate_email(email: str) -> bool:
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return re.match(pattern, email) is not None

        @staticmethod
        def validate_password(password: str) -> tuple:
            if len(password) < 8:
                return False, "Password must be at least 8 characters"
            if not re.search(r"[A-Z]", password):
                return False, "Password must contain at least one uppercase letter"
            if not re.search(r"[a-z]", password):
                return False, "Password must contain at least one lowercase letter"
            if not re.search(r"\d", password):
                return False, "Password must contain at least one number"
            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
                return False, "Password must contain at least one special character"
            return True, "Password is strong"

else:

    class DatabaseManager:
        """BigQuery database manager for user authentication"""

        def __init__(self):
            try:
                # Load BigQuery credentials
                self.project_id = os.environ.get('PROJECT_ID')
                self.environment = 'gcp'
                self.client = getBigQueryClient()
                self.project_id = os.environ.get('PROJECT_ID')
                self.dataset_id = "trading_dashboard"
                self.table_id = "users"

                # Ensure dataset and table exist
                self._create_dataset_if_not_exists()
                self._create_users_table_if_not_exists()

            except Exception as e:
                st.error(f"Database connection error1: {str(e)}")
                self.client = None

        def _create_dataset_if_not_exists(self):
            """Create BigQuery dataset if it doesn't exist"""
            try:
                dataset_ref = self.client.dataset(self.dataset_id)
                try:
                    self.client.get_dataset(dataset_ref)
                except:
                    dataset = bigquery.Dataset(dataset_ref)
                    dataset.location = "EU"
                    dataset.description = "Tradvisor user authentication data"
                    self.client.create_dataset(dataset, timeout=30)
            except Exception as e:
                st.error(f"Error creating dataset: {str(e)}")

        def _create_users_table_if_not_exists(self):
            """Create users table if it doesn't exist"""
            try:
                table_ref = self.client.dataset(self.dataset_id).table(self.table_id)
                try:
                    self.client.get_table(table_ref)
                except:
                    schema = [
                        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("password_hash", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("salt", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
                        bigquery.SchemaField("last_login", "TIMESTAMP", mode="NULLABLE"),
                        bigquery.SchemaField("reset_token", "STRING", mode="NULLABLE"),
                        bigquery.SchemaField("reset_token_expires", "TIMESTAMP", mode="NULLABLE"),
                        bigquery.SchemaField("preferences", "JSON", mode="NULLABLE"),
                    ]

                    table = bigquery.Table(table_ref, schema=schema)
                    table = self.client.create_table(table)
            except Exception as e:
                st.error(f"Error creating users table: {str(e)}")

        def create_user(self, email: str, password: str) -> bool:
            """Create a new user account"""
            try:
                # Check if user already exists
                if self.get_user_by_email(email):
                    return False

                # Generate salt and hash password
                salt = secrets.token_hex(32)
                password_hash = self._hash_password(password, salt)
                user_id = secrets.token_hex(16)

                # Insert user into BigQuery
                query = f"""
                INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                (user_id, email, password_hash, salt, created_at)
                VALUES (@user_id, @email, @password_hash, @salt, @created_at)
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                        bigquery.ScalarQueryParameter("email", "STRING", email.lower()),
                        bigquery.ScalarQueryParameter("password_hash", "STRING", password_hash),
                        bigquery.ScalarQueryParameter("salt", "STRING", salt),
                        bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", datetime.utcnow()),
                    ]
                )

                query_job = self.client.query(query, job_config=job_config)
                query_job.result()
                return True

            except Exception as e:
                st.error(f"Error creating user: {str(e)}")
                return False

        def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
            """Authenticate user login"""
            try:
                user = self.get_user_by_email(email)
                if not user:
                    return None

                # Verify password
                password_hash = self._hash_password(password, user['salt'])
                if password_hash == user['password_hash']:
                    # Update last login
                    self._update_last_login(email)
                    return {
                        'user_id': user['user_id'],
                        'email': user['email'],
                        'created_at': user['created_at']
                    }
                return None

            except Exception as e:
                st.error(f"Authentication error: {str(e)}")
                return None

        def get_user_by_email(self, email: str) -> Optional[Dict]:
            """Get user by email address"""
            try:
                query = f"""
                SELECT user_id, email, password_hash, salt, created_at, preferences
                FROM `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                WHERE email = @email
                LIMIT 1
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("email", "STRING", email.lower())
                    ]
                )

                query_job = self.client.query(query, job_config=job_config)
                results = query_job.result()

                for row in results:
                    return {
                        'user_id': row.user_id,
                        'email': row.email,
                        'password_hash': row.password_hash,
                        'salt': row.salt,
                        'created_at': row.created_at,
                        'preferences': row.preferences
                    }
                return None

            except Exception as e:
                st.error(f"Error getting user: {str(e)}")
                return None

        def _update_last_login(self, email: str):
            """Update user's last login timestamp"""
            try:
                query = f"""
                UPDATE `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                SET last_login = @last_login
                WHERE email = @email
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("last_login", "TIMESTAMP", datetime.utcnow()),
                        bigquery.ScalarQueryParameter("email", "STRING", email.lower())
                    ]
                )

                query_job = self.client.query(query, job_config=job_config)
                query_job.result()

            except Exception as e:
                st.error(f"Error updating last login: {str(e)}")

        def create_reset_token(self, email: str) -> Optional[str]:
            """Create password reset token"""
            try:
                token = secrets.token_urlsafe(32)
                expires = datetime.utcnow() + timedelta(hours=1)

                query = f"""
                UPDATE `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                SET reset_token = @token, reset_token_expires = @expires
                WHERE email = @email
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("token", "STRING", token),
                        bigquery.ScalarQueryParameter("expires", "TIMESTAMP", expires),
                        bigquery.ScalarQueryParameter("email", "STRING", email.lower())
                    ]
                )

                query_job = self.client.query(query, job_config=job_config)
                result = query_job.result()

                if query_job.num_dml_affected_rows > 0:
                    return token
                return None

            except Exception as e:
                st.error(f"Error creating reset token: {str(e)}")
                return None

        def reset_password_with_token(self, token: str, new_password: str) -> bool:
            """Reset password using valid token"""
            try:
                # Find user with valid token
                utc_now = datetime.utcnow()
                query = f"""
                SELECT email
                FROM `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                WHERE reset_token = @token AND reset_token_expires > @utc_now
                LIMIT 1
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("token", "STRING", token),
                        bigquery.ScalarQueryParameter("now", "TIMESTAMP", datetime.utcnow())
                    ]
                )

                query_job = self.client.query(query, job_config=job_config)
                results = query_job.result()

                user_email = None
                for row in results:
                    user_email = row.email
                    break

                if not user_email:
                    return False

                # Update password and clear reset token
                salt = secrets.token_hex(32)
                password_hash = self._hash_password(new_password, salt)

                update_query = f"""
                UPDATE `{self.project_id}.{self.dataset_id}.{self.table_id}` 
                SET password_hash = @password_hash, salt = @salt, 
                    reset_token = NULL, reset_token_expires = NULL
                WHERE email = @email
                """

                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("password_hash", "STRING", password_hash),
                        bigquery.ScalarQueryParameter("salt", "STRING", salt),
                        bigquery.ScalarQueryParameter("email", "STRING", user_email)
                    ]
                )

                query_job = self.client.query(update_query, job_config=job_config)
                query_job.result()
                return True

            except Exception as e:
                st.error(f"Error resetting password: {str(e)}")
                return False

        @staticmethod
        def _hash_password(password: str, salt: str) -> str:
            """Hash password with salt using SHA-256"""
            return hashlib.sha256((password + salt).encode()).hexdigest()

        @staticmethod
        def validate_email(email: str) -> bool:
            """Validate email format"""
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return re.match(pattern, email) is not None

        @staticmethod
        def validate_password(password: str) -> tuple[bool, str]:
            """Validate password strength"""
            if len(password) < 8:
                return False, "Password must be at least 8 characters long"

            if not re.search(r"[A-Z]", password):
                return False, "Password must contain at least one uppercase letter"

            if not re.search(r"[a-z]", password):
                return False, "Password must contain at least one lowercase letter"

            if not re.search(r"\d", password):
                return False, "Password must contain at least one number"

            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
                return False, "Password must contain at least one special character"

            return True, "Password is strong"