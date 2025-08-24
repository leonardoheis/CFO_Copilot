import streamlit as st

from app.frontend.pages import PAGES


def main() -> None:
    pg = st.navigation(PAGES)
    pg.run()


if __name__ == "__main__":
    main()
