"""Learning-area, item-type, and timer configuration screen."""

import streamlit as st

from config.learning import TIMER_PRESETS
from config.question_bank import QUESTION_BANK_DIFFICULTIES
from llm import LLMError

from .state import reset_chapter


def render_learning_setup(backend):
    subject = st.session_state.setup_subject
    st.title(f"Start {subject}")
    st.caption("Choose a learning area, time pace, and the kinds of items you want to study.")
    if st.button("← Back to subjects", key="setup_back"):
        st.session_state.setup_subject = None
        st.rerun()

    scope_key = f"setup_scope_{subject}"
    st.session_state.setdefault(scope_key, "")
    selected_scope = st.session_state[scope_key]
    st.subheader("Learning area")
    st.caption(f"Selected: {subject if not selected_scope else f'{subject} / {selected_scope}'}")
    scope_controls = st.columns(2)
    if scope_controls[0].button("Use full subject", key=f"scope_root_{subject}"):
        st.session_state[scope_key] = ""
        st.rerun()
    if scope_controls[1].button("Go up one level", key=f"scope_up_{subject}", disabled=not selected_scope):
        st.session_state[scope_key] = selected_scope.rsplit("/", 1)[0] if "/" in selected_scope else ""
        st.rerun()

    direct_subtopics = backend.get_direct_learning_subtopics(subject, selected_scope)
    if direct_subtopics:
        topic_filter = st.text_input("Filter direct subtopics", placeholder="Type to narrow the list", key=f"scope_filter_{subject}_{selected_scope}").casefold()
        matches = [topic for topic in direct_subtopics if topic_filter in topic.casefold()]
        visible = matches[:20]
        if len(matches) > 20:
            st.caption("Showing the first 20 matches. Refine the filter to narrow further.")
        if visible:
            next_topic = st.selectbox("Direct subtopic", options=visible, key=f"scope_child_{subject}_{selected_scope}")
            if st.button("Open subtopic", key=f"scope_open_{subject}_{selected_scope}"):
                st.session_state[scope_key] = f"{selected_scope}/{next_topic}" if selected_scope else next_topic
                st.rerun()
        else:
            st.info("No direct subtopics match that filter.")

    st.subheader("Include item types")
    columns = st.columns(3)
    include_objective = columns[0].checkbox("Objective", value=True, key=f"setup_objective_{subject}")
    include_subjective = columns[1].checkbox("Subjective", value=True, key=f"setup_subjective_{subject}")
    include_theory = columns[2].checkbox("Theory", value=False, key=f"setup_theory_{subject}")
    allowed_types = tuple(item_type for enabled, item_type in (
        (include_objective, "mcq"), (include_subjective, "subjective"), (include_theory, "theory")
    ) if enabled)

    st.subheader("Difficulty")
    difficulty_columns = st.columns(3)
    allowed_difficulties = tuple(
        difficulty
        for column, difficulty in zip(
            difficulty_columns,
            QUESTION_BANK_DIFFICULTIES,
        )
        if column.checkbox(
            difficulty.title(),
            value=True,
            key=f"setup_difficulty_{difficulty}_{subject}",
        )
    )
    if not allowed_difficulties:
        st.warning("Choose at least one difficulty.")

    learning_mode = st.checkbox("Learning mode (use infinite time)", key=f"setup_learning_mode_{subject}", help="Learning mode keeps every selected item type untimed.")
    if learning_mode:
        timer_preset = "Infinite"
        st.info("Learning mode uses infinite time for all selected item types.")
    else:
        timer_preset = st.selectbox("Timer", options=list(TIMER_PRESETS), index=list(TIMER_PRESETS).index("Normal"), key=f"timer_preset_{subject}")
        st.caption("Slow: 2 min objective / 4 min subjective · Normal: 1 min / 2 min · Fast: 30 sec / 1 min")

    if st.button(
        "Start learning",
        type="primary",
        use_container_width=True,
        key="start_configured_learning",
        disabled=not allowed_types or not allowed_difficulties,
    ):
        try:
            with st.spinner("Creating your first learning item..."):
                reset_chapter(
                    backend,
                    subject,
                    selected_scope,
                    allowed_types,
                    timer_preset,
                    allowed_difficulties,
                )
                st.session_state.step = backend.generate_initial_step(subject)
            st.session_state.setup_subject = None
            st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))
