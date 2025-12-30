"""
Streamlit Cloud entry point.
This file imports and runs the Streamlit UI from ui_app.py.
"""

import streamlit as st
from src.storage import Storage
from src.auth import ensure_auth_tables, ensure_admin_user
import ui_app

# Inicializē Storage pirms UI palaišanas
if 'storage' not in st.session_state:
    try:
        st.session_state.storage = Storage()
        ensure_auth_tables(st.session_state.storage)
        ensure_admin_user(st.session_state.storage)
    except Exception as e:
        st.error(f"Kļūda inicializējot sistēmu: {e}")
        import traceback
        print(f"Kļūda inicializējot sistēmu: {e}")
        print(traceback.format_exc())
        st.stop()

# Streamlit Cloud will execute this file, which will run the UI
ui_app.main()

