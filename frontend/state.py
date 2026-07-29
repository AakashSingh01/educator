"""Session-state initialization and shared UI callbacks."""

import streamlit as st

from backend import LearningBackend
from config.learning import QUESTION_MODE_TYPES
from config.question_bank import QUESTION_BANK_DIFFICULTIES
from llm_logging import LoggedLLMClient


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
    "learning_difficulties": list(QUESTION_BANK_DIFFICULTIES),
    "is_generating": False,
    "ask_messages": [],
    "mock_test_question_index": 0,
    "mock_test_end_time": None,
    "mock_test_timed_out": False,
    "home_panel": None,
    "read_subject": None,
    "read_scope": "",
}


def initialize_session():
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if "backend" not in st.session_state:
        st.session_state.backend = LearningBackend()
    elif not isinstance(st.session_state.backend.llm, LoggedLLMClient):
        st.session_state.backend.llm = LoggedLLMClient(st.session_state.backend.llm)
    return st.session_state.backend


def reset_chapter(
    backend,
    category,
    scope="",
    allowed_types=None,
    timer_preset="Normal",
    allowed_difficulties=None,
):
    allowed_types = tuple(allowed_types or QUESTION_MODE_TYPES["Both"])
    allowed_difficulties = tuple(
        allowed_difficulties or QUESTION_BANK_DIFFICULTIES
    )
    backend.start_course(
        category,
        scope,
        allowed_types,
        timer_preset,
        allowed_difficulties,
    )
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
    st.session_state.learning_difficulties = list(allowed_difficulties)


def mark_generating():
    """Pause timer refresh before a potentially slow model-backed action."""
    st.session_state.is_generating = True
