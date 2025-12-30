"""
Streamlit Cloud entry point.
This file imports and runs the Streamlit UI from ui_app.py.
"""

import streamlit as st

try:
    import ui_app
    ui_app.main()
except Exception as e:
    st.error("Startēšanās kļūda")
    st.exception(e)
