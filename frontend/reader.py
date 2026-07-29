"""Read-only course browser for notes and prepared learning items."""

import hashlib
from pathlib import Path

import streamlit as st


def _key_fragment(value):
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _render_notes(notes):
    if notes:
        st.markdown(notes)
    else:
        st.info("No notes.txt content is available in this folder.")


def _render_objective(items):
    if not items:
        st.info("No prepared objective questions are available in this folder.")
        return
    for index, item in enumerate(items, 1):
        with st.container(border=True):
            st.caption(f"{item.get('difficulty', '').title()} · Question {index}")
            st.markdown(item.get("question", "Question unavailable"))
            for option in item.get("options", []):
                st.markdown(f"- {option}")
            with st.expander("Show answer and explanation"):
                st.markdown(f"**Correct answer:** {item.get('correct_option', 'Unavailable')}")
                if item.get("explanation"):
                    st.markdown(item["explanation"])
                if item.get("reason"):
                    st.markdown(f"**Other options:** {item['reason']}")


def _render_subjective(items):
    if not items:
        st.info("No prepared subjective questions are available in this folder.")
        return
    for index, item in enumerate(items, 1):
        with st.container(border=True):
            st.caption(f"{item.get('difficulty', '').title()} · Question {index}")
            st.markdown(item.get("question", "Question unavailable"))
            with st.expander("Show model answer"):
                st.markdown(item.get("answer", "Answer unavailable"))


def _render_theory(items):
    if not items:
        st.info("No prepared theory cards are available in this folder.")
        return
    for index, item in enumerate(items, 1):
        with st.expander(
            f"{index}. {item.get('title', 'Theory card')} · "
            f"{item.get('difficulty', '').title()}"
        ):
            st.markdown(item.get("content", "Content unavailable"))


def _render_content(kind, topic):
    if kind == "Notes":
        _render_notes(topic["notes"])
    elif kind == "Objective":
        _render_objective(topic["objective"])
    elif kind == "Subjective":
        _render_subjective(topic["subjective"])
    else:
        _render_theory(topic["theory"])


@st.dialog("Expanded reader", width="large")
def _show_expanded_reader(kind, topic):
    st.subheader(topic["label"])
    st.caption(kind)
    with st.container(height=650):
        _render_content(kind, topic)


def _open_topic(subject, scope):
    st.session_state.read_subject = subject
    st.session_state.read_scope = scope


def _render_topic_navigator(backend):
    subject = st.session_state.read_subject
    scope = st.session_state.read_scope
    with st.container(border=True, height=560):
        st.subheader("Topics")
        if subject is None:
            st.caption("Choose a subject")
            categories = backend.get_categories()
            if not categories:
                st.info("No subject folders are available.")
            for category in categories:
                st.button(
                    category,
                    key=f"read_subject_{_key_fragment(category)}",
                    width="stretch",
                    on_click=_open_topic,
                    args=(category, ""),
                )
            return

        st.caption(subject if not scope else f"{subject} / {scope}")
        if st.button(
            "All subjects",
            icon=":material/home:",
            key="reader_all_subjects",
            width="stretch",
        ):
            _open_topic(None, "")
            st.rerun()
        if st.button(
            "Parent topic",
            icon=":material/arrow_upward:",
            key=f"reader_parent_{_key_fragment(subject + scope)}",
            disabled=not scope,
            width="stretch",
        ):
            parent = str(Path(scope).parent)
            _open_topic(subject, "" if parent == "." else parent)
            st.rerun()

        topic = backend.get_reader_topic(subject, scope)
        st.divider()
        st.caption("Subtopics")
        if not topic["children"]:
            st.caption("No direct subtopics")
        for child in topic["children"]:
            child_scope = str(Path(scope) / child) if scope else child
            st.button(
                child,
                key=f"read_child_{_key_fragment(subject + child_scope)}",
                width="stretch",
                on_click=_open_topic,
                args=(subject, child_scope),
            )


def _render_topic_content(backend):
    subject = st.session_state.read_subject
    if subject is None:
        st.title("Read")
        st.caption("Choose a subject from the topic navigator.")
        return

    topic = backend.get_reader_topic(subject, st.session_state.read_scope)
    st.title(topic["label"].split(" / ")[-1])
    st.caption(topic["label"])

    tab_specs = (
        ("Notes", 1 if topic["notes"] else 0),
        ("Objective", len(topic["objective"])),
        ("Subjective", len(topic["subjective"])),
        ("Theory", len(topic["theory"])),
    )
    labels = [f"{name} ({count})" for name, count in tab_specs]
    tabs = st.tabs(
        labels,
        height=500,
        key=f"reader_tabs_{_key_fragment(topic['label'])}",
        on_change="rerun",
    )
    for tab, (kind, _) in zip(tabs, tab_specs):
        if not tab.open:
            continue
        with tab:
            if st.button(
                "Expand",
                icon=":material/open_in_full:",
                key=f"reader_expand_{kind}_{_key_fragment(topic['label'])}",
            ):
                _show_expanded_reader(kind, topic)
            _render_content(kind, topic)


def render_reader(backend):
    controls = st.container(horizontal=True, vertical_alignment="center")
    if controls.button("Home", icon=":material/arrow_back:", key="reader_home"):
        st.session_state.mode = "learn"
        st.session_state.home_panel = None
        st.session_state.read_subject = None
        st.session_state.read_scope = ""
        st.rerun()
    controls.caption("Read-only workspace")

    if (
        st.session_state.read_subject is not None
        and st.session_state.read_subject not in backend.get_categories()
    ):
        st.session_state.read_subject = None
        st.session_state.read_scope = ""

    navigator, content = st.columns([1, 3], gap="large")
    with navigator:
        _render_topic_navigator(backend)
    with content:
        _render_topic_content(backend)
