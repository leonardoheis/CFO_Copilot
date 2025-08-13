import pages
import streamlit as st


def main() -> None:
    pg = st.navigation(pages.pages)
    pg.run()


if __name__ == "__main__":
    main()
