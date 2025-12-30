"""
Streamlit Cloud entry point.
This file imports and runs the Streamlit UI from ui_app.py.

IMPORTANT: This is the ONLY file that should be executed by Streamlit Cloud.
DO NOT import cli_app.py here or anywhere in the Streamlit code path.
"""
import streamlit as st

# Ensure we're not in CLI mode
if __name__ == "__main__":
    try:
        import ui_app
        ui_app.main()
    except Exception as e:
        st.error("Startēšanās kļūda")
        st.exception(e)
