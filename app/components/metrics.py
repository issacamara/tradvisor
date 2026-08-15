"""Metric badge and status indicators components."""
import streamlit as st


def render_score_badge(score: int, category: str):
  """Displays formatted score card with color highlight."""
  color = "#28a745" if score >= 80 else "#ffc107" if score >= 60 else "#dc3545"
  st.markdown(
      f"""
        <div style="background-color:{color}; padding:15px; border-radius:8px; text-align:center; color:white;">
            <h2 style="margin:0; font-size:32px;">{score} / 100</h2>
            <p style="margin:0; font-weight:bold;">{category}</p>
        </div>
        """,
      unsafe_allow_html=True,
  )