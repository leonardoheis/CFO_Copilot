import streamlit as st

from .health import health_page
from .test import test_page

pages = [
    st.Page(health_page, title="Health Page", icon=":material/favorite:"),
    st.Page(test_page, title="Test Page", icon=":material/check_circle:"),
]

__all__ = ["pages"]
