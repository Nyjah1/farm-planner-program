"""
Streamlit Cloud entry point.
This file imports and runs the Streamlit UI from ui_app.py.

IMPORTANT: This is the ONLY file that should be executed by Streamlit Cloud.
DO NOT import cli_app.py here or anywhere in the Streamlit code path.
"""
# Import ui_app - this will execute the module-level code
# Then call main() function if it exists
try:
    import ui_app
    # Check if main() exists and call it
    if hasattr(ui_app, 'main'):
        ui_app.main()
    else:
        # If main() doesn't exist, the module-level code should handle everything
        # (ui_app.py has code at module level that runs when imported)
        pass
except AttributeError as e:
    import streamlit as st
    st.error(f"Startēšanās kļūda: ui_app modulim nav main() funkcijas. Kļūda: {e}")
    st.exception(e)
except Exception as e:
    import streamlit as st
    st.error("Startēšanās kļūda")
    st.exception(e)
