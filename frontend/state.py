"""Session-state initialization and shared UI callbacks."""

import streamlit as st

from backend import LearningBackend
from learning_config import QUESTION_MODE_TYPES


DEFAULTS = {
    "started": False,
    "category": None,
    "step": 0,
    "end_time": None,
    "timeout_sent": False,
    "show_home_dialog": False,
    "last_submit": None,
    "mode": "learn",
    "notes_subject": None,
    "setup_subject": None,
    "learning_timer": "Normal",
    "learning_types": list(QUESTION_MODE_TYPES["Both"]),
    "is_generating": False,
    "ask_messages": [],
}


def initialize_session():
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if "backend" not in st.session_state:
        st.session_state.backend = LearningBackend()
    return st.session_state.backend


def reset_chapter(backend, category, scope="", allowed_types=None, timer_preset="Normal"):
    allowed_types = tuple(allowed_types or QUESTION_MODE_TYPES["Both"])
    backend.start_course(category, scope, allowed_types, timer_preset)
    st.session_state.category = category
    st.session_state.started = True
    st.session_state.step = backend.first_step()
    st.session_state.end_time = None
    st.session_state.timeout_sent = False
    st.session_state.last_submit = None
    st.session_state.ask_messages = []
    st.session_state.is_generating = False
    st.session_state.learning_timer = timer_preset
    st.session_state.learning_types = list(allowed_types)


def mark_generating():
    """Pause timer refresh before a potentially slow model-backed action."""
    st.session_state.is_generating = True
