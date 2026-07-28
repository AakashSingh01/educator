"""Landing screen for selecting notes work or a subject to study."""

import streamlit as st


def render_home(backend):
    st.title("Learning App")
    st.subheader("Notes workspace")
    actions = st.columns(2)
    if actions[0].button("Prepare notes", key="prepare_notes", type="primary", width="stretch"):
        st.session_state.mode = "notes"
        st.rerun()
    if actions[1].button("Mock test", key="start_mock_test", width="stretch"):
        st.session_state.mode = "mock_test"
        st.rerun()
    st.subheader("Learn a subject")
    categories = backend.get_categories()
    if not categories:
        st.info("No subjects found. Add subject folders inside the course directory.")
        return

    with st.container(border=True):
        selected_subject = st.selectbox(
            "Choose a subject",
            categories,
            index=None,
            placeholder="Search or select a subject",
            key="home_subject",
        )
        if st.button(
            "Continue to learning setup",
            key="open_learning_setup",
            type="primary",
            disabled=selected_subject is None,
            width="stretch",
        ):
            st.session_state.setup_subject = selected_subject
            st.rerun()
