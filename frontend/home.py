"""Landing screen for selecting notes work or a subject to study."""

import streamlit as st


def render_home(backend):
    st.title("Learning App")
    st.subheader("Notes workspace")
    if st.button("📝 Prepare notes", key="prepare_notes", type="primary", use_container_width=True):
        st.session_state.mode = "notes"
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
