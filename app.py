"""ThalLink Hematologic Platform entrypoint; existing page URLs are preserved."""
from __future__ import annotations

import streamlit as st

from thalab.styles import inject_css, top_navigation
from ui.platform_home import render_platform_home

st.set_page_config(
    page_title="ThalLink | Hematologic Platform",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()
top_navigation("Command center")
render_platform_home()
