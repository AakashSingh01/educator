"""Landing screen for selecting notes work or a subject to study."""

import streamlit as st


def render_home(backend):
    st.title("Learning App")
    st.subheader("Notes workspace")
    actions = st.columns(2)
    if actions[0].button("📝 Prepare notes", key="prepare_notes", type="primary", width="stretch"):
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
    columns = st.columns(len(categories))
    for column, category in zip(columns, categories):
        if column.button(category, key=f"category_{category}"):
            st.session_state.setup_subject = category
            st.rerun()
