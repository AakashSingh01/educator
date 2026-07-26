"""Streamlit entry point: initialize state, then route to a focused view."""

import streamlit as st

from frontend.home import render_home
from frontend.learning_setup import render_learning_setup
from frontend.notes import render_notes_preparation
from frontend.session import render_learning_session
from frontend.state import initialize_session
from frontend.styles import inject_custom_styles


st.set_page_config(page_title="Learning App", layout="wide")

backend = initialize_session()
inject_custom_styles()

if st.session_state.mode == "notes":
    render_notes_preparation(backend)
elif st.session_state.setup_subject:
    render_learning_setup(backend)
elif not st.session_state.started:
    render_home(backend)
else:
    render_learning_session(backend)
