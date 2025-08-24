import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/health"


def health_page() -> None:
    st.write("# Health Page")

    if not st.button("Show Results"):
        return

    response = requests.get(API_BASE_URL, timeout=5)
    if response.ok:
        st.success(f"Prediction: {response.json()}")
        return

    st.error(f"There was an error in the request: {response.text}")
