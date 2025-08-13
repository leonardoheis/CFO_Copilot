import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/health"


def health_page() -> None:
    st.write("# Health Page")
    if st.button("Show Results"):
        response = requests.get(API_BASE_URL, timeout=5)
        if response.status_code == 200:
            st.success(f"Prediction: {response.json()}")
        else:
            st.error(f"Error: {response.text}")
