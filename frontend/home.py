"""Landing screen for selecting notes work or a subject to study."""

import streamlit as st


def render_home(backend):
    st.title("Learning App")
    st.subheader("Choose a workspace")
    actions = st.columns(4)
    if actions[0].button(
        "Notes",
        icon=":material/edit_note:",
        key="prepare_notes",
        width="stretch",
    ):
        st.session_state.mode = "notes"
        st.rerun()
    if actions[1].button(
        "Test",
        icon=":material/quiz:",
        key="start_mock_test",
        width="stretch",
    ):
        st.session_state.mode = "mock_test"
        st.rerun()
    if actions[2].button(
        "Read",
        icon=":material/menu_book:",
        key="start_reader",
        width="stretch",
    ):
        st.session_state.mode = "read"
        st.session_state.read_subject = None
        st.session_state.read_scope = ""
        st.rerun()
    if actions[3].button(
        "Learn",
        icon=":material/school:",
        key="show_learning_subjects",
        type="primary",
        width="stretch",
    ):
        st.session_state.home_panel = "learn"
        st.rerun()

    if st.session_state.home_panel != "learn":
        st.caption("Prepare notes, take a mock test, browse your material, or start a learning session.")
        return

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
