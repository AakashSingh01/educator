"""Active learning-item display, timing, feedback, and follow-up chat."""

import time
from html import escape

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from backend import PageType
from llm import LLMError

from .state import mark_generating


def _load_step(backend):
    step = backend.get_step(st.session_state.step)
    if step["type"] != PageType.END:
        time_limit = step.get("time_limit")
        if st.session_state.end_time is None and time_limit is not None:
            st.session_state.end_time = time.time() + time_limit
    return step


def _goto_next(backend):
    try:
        with st.spinner("Creating the next item..."):
            st.session_state.step = backend.generate_follow_up_step(st.session_state.category, "")
    except ValueError as error:
        st.session_state.is_generating = False
        st.error(str(error))
        return
    except LLMError:
        st.session_state.is_generating = False
        st.error("The configured AI provider is unavailable. Check its connection and model settings.")
        return
    st.session_state.end_time = None
    st.session_state.timeout_sent = False
    st.session_state.last_submit = None
    st.session_state.is_generating = False
    st.session_state.ask_messages = []
    st.rerun()


def _show_submit_feedback():
    feedback = st.session_state.last_submit
    if feedback and feedback.get("step") == st.session_state.step:
        (st.success if feedback["status"] == "success" else st.error)(feedback["message"])
        if feedback.get("info"):
            st.info(feedback["info"])


def _already_submitted():
    feedback = st.session_state.last_submit
    return bool(feedback and feedback.get("step") == st.session_state.step and feedback.get("submitted"))


def _render_ask_box(backend, step):
    if not _already_submitted():
        return
    for message in st.session_state.ask_messages:
        if message.get("step") == st.session_state.step:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    with st.form(f"ask_form_{st.session_state.step}", clear_on_submit=True):
        question = st.text_input("Ask a follow-up about this result", placeholder="Why is this answer correct?")
        submitted = st.form_submit_button("Ask", on_click=mark_generating)
    if submitted:
        try:
            with st.spinner("Preparing an answer..."):
                answer = backend.ask_about_result(st.session_state.category, step, question)
            st.session_state.ask_messages.extend((
                {"step": st.session_state.step, "role": "user", "content": question.strip()},
                {"step": st.session_state.step, "role": "assistant", "content": answer},
            ))
            st.session_state.is_generating = False
            st.rerun()
        except (ValueError, LLMError) as error:
            st.session_state.is_generating = False
            st.error(str(error))


def _render_home_dialog(backend):
    if not st.session_state.show_home_dialog:
        return
    st.warning("Leave this chapter?")
    yes, cancel = st.columns(2)
    if yes.button("Yes"):
        backend.on_event("chapter_closed", step_id=st.session_state.step)
        st.session_state.started = False
        st.session_state.setup_subject = None
        st.session_state.step = backend.first_step()
        st.session_state.end_time = None
        st.session_state.timeout_sent = False
        st.session_state.last_submit = None
        st.session_state.show_home_dialog = False
        st.rerun()
    if cancel.button("Cancel"):
        st.session_state.show_home_dialog = False
        st.rerun()


def render_learning_session(backend):
    _render_home_dialog(backend)
    step = _load_step(backend)
    step_time_limit = step.get("time_limit")
    if step_time_limit is not None and st.session_state.end_time is not None:
        remaining = max(0, int(st.session_state.end_time - time.time()))
        timed_out = remaining == 0
        if not st.session_state.is_generating:
            st_autorefresh(interval=1000, key="tick")
    else:
        remaining = None
        timed_out = False

    subject_column, timer_column, home_column = st.columns([6, 2, 1])
    with subject_column:
        st.subheader(f"📚 {st.session_state.category}")
        boundary = backend.get_learning_boundary_label()
        if boundary:
            st.caption(f"Learning area: {boundary}")
    with timer_column:
        st.metric("Time Left", "Unlimited" if remaining is None else f"{remaining}s")
    with home_column:
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.show_home_dialog = True

    if timed_out and not st.session_state.timeout_sent:
        backend.on_event("time_expired", step_id=st.session_state.step)
        st.session_state.timeout_sent = True
    if step["type"] == PageType.END:
        st.info("No learning item is available. Return home and select the subject again.")
        st.stop()

    if step["type"] == PageType.THEORY:
        st.header(step["title"])
        st.write(step["content"])
        if timed_out:
            st.warning("Reading time finished.")
        if st.button("Next", type="primary", on_click=mark_generating):
            backend.on_event("theory_completed", step_id=st.session_state.step)
            _goto_next(backend)
        return

    st.caption(f"Question scope: {backend.get_learning_context_label() or st.session_state.category}")
    st.markdown(f'<div class="question-title">{escape(step["question"])}</div>', unsafe_allow_html=True)
    if step["type"] == PageType.MCQ:
        answer = st.radio("Select", step["options"], disabled=timed_out)
        _show_submit_feedback()
        if timed_out:
            st.error("Time over. Press Next.")
        elif st.button("Submit", key="mcq_submit", disabled=_already_submitted()):
            try:
                answer_index = step["options"].index(answer)
                correct = backend.check_answer(step, answer_index)
                backend.on_event("answer_submitted", step_id=st.session_state.step, answer=answer_index, correct=correct, timed_out=False)
                st.session_state.last_submit = {
                    "step": st.session_state.step,
                    "status": "success" if correct else "error",
                    "message": "Correct" if correct else "Incorrect",
                    "info": "\n\n".join(filter(None, (
                        f"Correct answer: {step.get('correct_option', step['options'][step['answer']])}",
                        step.get("explanation", ""),
                        f"Why the other options do not fit: {step.get('reason', '')}" if step.get("reason") else "",
                    ))),
                    "submitted": True,
                }
            except (KeyError, TypeError, ValueError):
                st.session_state.last_submit = {"step": st.session_state.step, "status": "error", "message": "This question could not be submitted. Please continue to the next question."}
            st.rerun()
        if st.button("Next", key="mcq_next", type="primary", on_click=mark_generating):
            _goto_next(backend)
        _render_ask_box(backend, step)
        return

    answer = st.text_area("Answer", disabled=timed_out)
    _show_submit_feedback()
    if timed_out:
        st.error("Time over. Press Next.")
    elif st.button("Submit", key="subjective_submit", disabled=_already_submitted(), on_click=mark_generating):
        try:
            with st.spinner("Checking your answer..."):
                assessment = backend.evaluate_subjective_answer(st.session_state.category, step, answer)
            backend.on_event("answer_submitted", step_id=st.session_state.step, answer=answer, timed_out=False)
            st.session_state.last_submit = {
                "step": st.session_state.step,
                "status": "success" if assessment["correct"] else "error",
                "message": "Correct" if assessment["correct"] else "Not quite",
                "info": f"{assessment['feedback']}\n\nSuggested answer: {step.get('sample_answer', 'No sample answer available.')}",
                "submitted": True,
            }
            st.session_state.is_generating = False
            st.rerun()
        except ValueError as error:
            st.session_state.is_generating = False
            st.error(str(error))
        except LLMError:
            st.session_state.is_generating = False
            st.error("The configured AI provider is unavailable. Check its connection and model settings.")
    if st.button("Next", key="subjective_next", type="primary", on_click=mark_generating):
        _goto_next(backend)
    _render_ask_box(backend, step)
