# app.py
import time
from html import escape

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from backend import LearningBackend, PageType
from llm import LLMError

st.set_page_config(page_title="Learning App", layout="wide")

defaults = {
    "started": False,
    "category": None,
    "step": 0,
    "end_time": None,
    "timeout_sent": False,
    "show_home_dialog": False,
    "last_submit": None,
    "mode": "learn",
    "notes_subject": None,
}
for k,v in defaults.items():
    st.session_state.setdefault(k,v)

if "backend" not in st.session_state:
    st.session_state.backend = LearningBackend()
backend = st.session_state.backend

def reset_chapter(category):
    backend.start_course(category)
    st.session_state.category = category
    st.session_state.started = True
    st.session_state.step = backend.first_step()
    st.session_state.end_time = None
    st.session_state.timeout_sent = False
    st.session_state.last_submit = None
    st.session_state.learner_thought = ""

def start_learning_scope(scope):
    backend.start_course(st.session_state.category, scope)
    st.session_state.step = backend.generate_initial_step(st.session_state.category)
    st.session_state.end_time = None
    st.session_state.timeout_sent = False
    st.session_state.last_submit = None

def render_notes_preparation():
    st.title("Prepare Notes")
    st.caption("Review each topic, choose its direct subtopics, and build the notes structure depth-first.")

    if st.button("← Back to learning", key="notes_back"):
        st.session_state.mode = "learn"
        st.session_state.notes_subject = None
        st.rerun()

    subject = st.session_state.notes_subject
    if subject is None:
        subjects = backend.get_categories()
        selected_subject = st.selectbox(
            "Existing subject folder",
            options=[""] + subjects,
            format_func=lambda value: "Choose an existing subject" if not value else value,
        )
        new_subject = st.text_input("Or create a new subject folder")
        if st.button("Start or resume notes", key="start_notes"):
            requested_subject = new_subject.strip() or selected_subject
            try:
                backend.begin_notes_session(requested_subject)
                st.session_state.notes_subject = requested_subject
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        return

    progress = backend.get_notes_progress(subject)
    if progress is None:
        st.warning("No saved notes plan was found for this subject.")
        if st.button("Start a new notes plan"):
            backend.begin_notes_session(subject)
            st.rerun()
        return

    completed_count = len(progress["completed"])
    st.caption(f"Subject: {subject} · Completed: {completed_count} · Waiting in DFS stack: {len(progress['queue'])}")
    if st.button("Stop and save progress", key="notes_stop"):
        st.session_state.notes_subject = None
        st.rerun()

    navigation = st.radio(
        "Notes workflow",
        options=["Continue depth-first", "Choose a topic to edit"],
        horizontal=True,
        key=f"notes_navigation_{subject}",
    )
    picker_edit_key = f"notes_editing_selected_{subject}"
    last_navigation_key = f"notes_last_navigation_{subject}"
    if st.session_state.get(last_navigation_key) != navigation:
        st.session_state[picker_edit_key] = False
        st.session_state[last_navigation_key] = navigation
    if navigation == "Choose a topic to edit" and not st.session_state.get(picker_edit_key, False):
        available_topics = backend.list_notes_topics(subject)
        chosen_topic = st.selectbox(
            "Available topic folders",
            options=available_topics,
            format_func=lambda path: subject if not path else f"{subject} / {path}",
        )
        if st.button("Open selected topic", key="open_notes_topic"):
            try:
                backend.select_notes_topic(subject, chosen_topic)
                st.session_state[picker_edit_key] = True
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        return
    if navigation == "Choose a topic to edit":
        st.caption("Editing the selected topic. Choose another topic if needed.")
        if st.button("Choose a different topic", key="choose_different_topic"):
            st.session_state[picker_edit_key] = False
            st.rerun()

    topic = backend.get_current_notes_topic(subject)
    if topic is None:
        st.success("All selected topics have been prepared. Your progress is saved.")
        col_restart, col_another = st.columns(2)
        if col_restart.button("Revisit this subject from the root", key="notes_restart"):
            backend.begin_notes_session(subject, restart=True)
            st.rerun()
        if col_another.button("Prepare another subject", key="notes_another"):
            st.session_state.notes_subject = None
            st.rerun()
        return

    st.subheader(topic["label"])
    if topic["existing_subtopics"]:
        st.info("Existing subtopic folders: " + ", ".join(topic["existing_subtopics"]))

    safe_topic_key = topic["relative_path"].replace("/", "_") or "root"
    draft_key = f"notes_draft_{subject}_{safe_topic_key}"
    instruction_key = f"notes_instruction_{subject}_{safe_topic_key}"
    suggestions_key = f"notes_suggestions_{subject}_{safe_topic_key}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = topic["notes"]

    note_instruction = st.text_input(
        "How should these notes be improved? (optional)",
        placeholder="For example: add a worked example, simplify the language, or focus on definitions.",
        key=instruction_key,
    )
    generate_label = "Regenerate notes" if topic["notes"] else "Generate notes"
    if st.button(generate_label, key=f"generate_{safe_topic_key}"):
        try:
            with st.spinner("Drafting notes..."):
                st.session_state[draft_key] = backend.generate_topic_notes(
                    subject, topic["relative_path"], note_instruction
                )
            st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))

    notes_draft = st.text_area(
        "Notes (edit until satisfied)",
        height=300,
        key=draft_key,
    )
    if st.button("Save notes", key=f"save_{safe_topic_key}"):
        try:
            backend.save_topic_notes(subject, topic["relative_path"], notes_draft)
            st.success("Notes saved. Now choose the direct subtopics to prepare.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    if not topic["notes"]:
        st.info("Generate or write the notes, then save them before choosing subtopics.")
        return

    if topic["existing_subtopics"]:
        with st.expander("Manage existing direct subtopics"):
            selected_existing = st.selectbox(
                "Subtopic to rename or remove",
                options=topic["existing_subtopics"],
                key=f"manage_{safe_topic_key}",
            )
            renamed_subtopic = st.text_input(
                "Rename selected subtopic to",
                key=f"rename_{safe_topic_key}",
            )
            if st.button("Rename subtopic", key=f"rename_button_{safe_topic_key}"):
                try:
                    backend.rename_subtopic(
                        subject, topic["relative_path"], selected_existing, renamed_subtopic
                    )
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
            remove_confirmed = st.checkbox(
                "I understand removal deletes this subtopic and all nested notes.",
                key=f"remove_confirm_{safe_topic_key}",
            )
            if st.button("Remove selected subtopic", key=f"remove_button_{safe_topic_key}"):
                if not remove_confirmed:
                    st.error("Confirm removal before deleting a subtopic.")
                else:
                    try:
                        backend.remove_subtopic(subject, topic["relative_path"], selected_existing)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

    if st.button("Suggest subtopics", key=f"suggest_{safe_topic_key}"):
        try:
            with st.spinner("Finding focused direct subtopics..."):
                st.session_state[suggestions_key] = backend.suggest_subtopics(subject, topic["relative_path"])
            st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))

    suggestions = st.session_state.get(suggestions_key, [])
    subtopic_options = list(dict.fromkeys(topic["existing_subtopics"] + suggestions))
    selected_subtopics = st.multiselect(
        "Choose subtopics to create or prepare",
        options=subtopic_options,
        help="Only selected subtopics are added to the saved DFS stack.",
        key=f"selected_{safe_topic_key}",
    )
    manual_subtopics = st.text_input(
        "Add other direct subtopics (comma-separated)",
        key=f"manual_{safe_topic_key}",
    )
    if st.button("Confirm subtopics and continue depth-first", key=f"continue_{safe_topic_key}"):
        manual_names = [name.strip() for name in manual_subtopics.split(",") if name.strip()]
        try:
            backend.complete_notes_topic(
                subject,
                topic["relative_path"],
                selected_subtopics + manual_names,
            )
            st.rerun()
        except ValueError as error:
            st.error(str(error))

def load_step():
    step = backend.get_step(st.session_state.step)
    if step["type"] != PageType.END:
        time_limit = step.get("time_limit")
        if st.session_state.end_time is None and time_limit is not None:
            st.session_state.end_time = time.time() + time_limit
    return step

def inject_custom_styles():
    st.markdown(
        """
        <style>
        div[role="radiogroup"] label,
        div[role="radio"] {
            font-size: 2.4rem !important;
        }
        .stRadio label,
        .stRadio div[role="radio"] {
            font-size: 2.4rem !important;
        }
        .question-title {
            font-size: 2.75rem;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }
        .stTextArea label {
            font-size: 1.15rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

inject_custom_styles()

if st.session_state.mode == "notes":
    render_notes_preparation()
    st.stop()

if not st.session_state.started:
    st.title("Learning App")
    st.subheader("Notes workspace")
    if st.button("📝 Prepare notes", key="prepare_notes", type="primary", use_container_width=True):
        st.session_state.mode = "notes"
        st.rerun()

    st.divider()
    st.subheader("Learn a subject")

    categories = backend.get_categories()
    if not categories:
        st.info("No subjects found. Add subject folders inside the course directory.")
    else:
        cols = st.columns(len(categories))
        for col, category in zip(cols, categories):
            if col.button(category, key=f"category_{category}"):
                try:
                    reset_chapter(category)
                    with st.spinner("Creating your first learning item..."):
                        st.session_state.step = backend.generate_initial_step(category)
                    st.rerun()
                except (ValueError, LLMError) as error:
                    st.session_state.started = False
                    st.error(str(error))
    st.stop()



if st.session_state.show_home_dialog:
    st.warning("Leave this chapter?")
    c1,c2=st.columns(2)
    with c1:
        if st.button("Yes"):
            backend.on_event("chapter_closed",step_id=st.session_state.step)
            st.session_state.started=False
            st.session_state.step=backend.first_step()
            st.session_state.end_time=None
            st.session_state.timeout_sent=False
            st.session_state.last_submit=None
            st.session_state.show_home_dialog=False
            st.rerun()
    with c2:
        if st.button("Cancel"):
            st.session_state.show_home_dialog=False
            st.rerun()

step=load_step()

step_time_limit = step.get("time_limit")
if step_time_limit is not None and st.session_state.end_time is not None:
    remaining = max(0, int(st.session_state.end_time - time.time()))
    timed_out = remaining == 0
    st_autorefresh(interval=1000, key="tick")
else:
    remaining = None
    timed_out = False

# Header
col1, col2, col3 = st.columns([6, 2, 1])

with col1:
    st.subheader(f"📚 {st.session_state.category}")
    learning_scope = backend.get_learning_context_label()
    if learning_scope:
        st.caption(f"Learning focus: {learning_scope}")

with col2:
    if remaining is None:
        st.metric("Time Left", "Unlimited")
    else:
        st.metric("Time Left", f"{remaining}s")

with col3:
    if st.button("🏠 Home", use_container_width=True):
        st.session_state.show_home_dialog = True

learning_scopes = backend.get_learning_scopes(st.session_state.category)
selected_scope = st.selectbox(
    "Learning area",
    options=learning_scopes,
    format_func=lambda scope: "Full subject (random prepared note)" if not scope else scope,
    key=f"learning_scope_{st.session_state.category}",
)
if st.button("Use selected learning area", key="use_learning_scope"):
    try:
        with st.spinner("Creating a learning item from the selected notes..."):
            start_learning_scope(selected_scope)
        st.rerun()
    except (ValueError, LLMError) as error:
        st.error(str(error))

learner_thought = st.text_input(
    "Add a comment or ask a follow-up question (optional)",
    placeholder="For example: Why is that true? Or: give me a similar question.",
    key="learner_thought",
)

if timed_out and not st.session_state.timeout_sent:
    backend.on_event("time_expired",step_id=st.session_state.step)
    st.session_state.timeout_sent=True

if step["type"] == PageType.END:
    st.info("No learning item is available. Return home and select the subject again.")
    st.stop()

def goto_next():
    try:
        with st.spinner("Creating the next item..."):
            st.session_state.step = backend.generate_follow_up_step(
                st.session_state.category,
                st.session_state.learner_thought,
            )
    except ValueError as error:
        st.error(str(error))
        return
    except LLMError:
        st.error("The configured AI provider is unavailable. Check its connection and model settings.")
        return
    st.session_state.end_time=None
    st.session_state.timeout_sent=False
    st.session_state.last_submit=None
    st.rerun()

def show_submit_feedback():
    feedback = st.session_state.last_submit
    if feedback and feedback.get("step") == st.session_state.step:
        if feedback["status"] == "success":
            st.success(feedback["message"])
        else:
            st.error(feedback["message"])
        if feedback.get("info"):
            st.info(feedback["info"])

def already_submitted():
    feedback = st.session_state.last_submit
    return bool(feedback and feedback.get("step") == st.session_state.step and feedback.get("submitted"))

if step["type"]==PageType.THEORY:
    st.header(step["title"])
    st.write(step["content"])
    if timed_out:
        st.warning("Reading time finished.")
    if st.button("Next"):
        backend.on_event("theory_completed",step_id=st.session_state.step)
        goto_next()

elif step["type"]==PageType.MCQ:
    st.caption(f"Question scope: {backend.get_learning_context_label() or st.session_state.category}")
    st.markdown(f'<div class="question-title">{escape(step["question"])}</div>', unsafe_allow_html=True)
    ans=st.radio("Select",step["options"],disabled=timed_out)
    show_submit_feedback()
    if timed_out:
        st.error("Time over. Press Next.")
    else:
        if st.button("Submit", key="mcq_submit", disabled=already_submitted()):
            try:
                idx = step["options"].index(ans)
                ok = backend.check_answer(step, idx)
                backend.on_event("answer_submitted", step_id=st.session_state.step, answer=idx, correct=ok, timed_out=False)
                st.session_state.last_submit = {
                    "step": st.session_state.step,
                    "status": "success" if ok else "error",
                    "message": "Correct" if ok else "Incorrect",
                    "info": step.get("explanation"),
                    "submitted": True,
                }
            except (KeyError, TypeError, ValueError):
                st.session_state.last_submit = {
                    "step": st.session_state.step,
                    "status": "error",
                    "message": "This question could not be submitted. Please continue to the next question.",
                }
            st.rerun()
    if st.button("Next", key="mcq_next"):
        goto_next()

elif step["type"]==PageType.SUBJECTIVE:
    st.caption(f"Question scope: {backend.get_learning_context_label() or st.session_state.category}")
    st.markdown(f'<div class="question-title">{escape(step["question"])}</div>', unsafe_allow_html=True)
    txt=st.text_area("Answer",disabled=timed_out)
    show_submit_feedback()
    if timed_out:
        st.error("Time over. Press Next.")
    else:
        if st.button("Submit", key="subjective_submit", disabled=already_submitted()):
            try:
                with st.spinner("Checking your answer..."):
                    assessment = backend.evaluate_subjective_answer(
                        st.session_state.category,
                        step,
                        txt,
                    )
                backend.on_event("answer_submitted",step_id=st.session_state.step,answer=txt,timed_out=False)
                st.session_state.last_submit = {
                    "step": st.session_state.step,
                    "status": "success" if assessment["correct"] else "error",
                    "message": "Correct" if assessment["correct"] else "Not quite",
                    "info": (
                        f"{assessment['feedback']}\n\n"
                        f"Suggested answer: {step.get('sample_answer', 'No sample answer available.')}"
                    ),
                    "submitted": True,
                }
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except LLMError:
                st.error("The configured AI provider is unavailable. Check its connection and model settings.")
    if st.button("Next", key="subjective_next"):
        goto_next()
