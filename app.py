# app.py
import time
from html import escape

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from backend import LearningBackend, PageType
from llm import OllamaError

st.set_page_config(page_title="Learning App", layout="wide")

defaults = {
    "started": False,
    "category": None,
    "step": 0,
    "end_time": None,
    "timeout_sent": False,
    "show_home_dialog": False,
    "last_submit": None,
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

if not st.session_state.started:
    st.title("Learning App")
    st.write("Choose a category")

    categories = backend.get_categories()
    if not categories:
        st.info("No subjects found. Add subject folders inside the course directory.")
    else:
        cols = st.columns(len(categories))
        for col, category in zip(cols, categories):
            if col.button(category, key=f"category_{category}"):
                reset_chapter(category)
                st.rerun()
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

st_autorefresh(interval=1000,key="tick")
step=load_step()

step_time_limit = step.get("time_limit")
if step_time_limit is not None and st.session_state.end_time is not None:
    remaining = max(0, int(st.session_state.end_time - time.time()))
    timed_out = remaining == 0
else:
    remaining = None
    timed_out = False

# Header
col1, col2, col3 = st.columns([6, 2, 1])

with col1:
    st.subheader(f"📚 {st.session_state.category}")

with col2:
    if remaining is None:
        st.metric("Time Left", "Unlimited")
    else:
        st.metric("Time Left", f"{remaining}s")

with col3:
    if st.button("🏠 Home", use_container_width=True):
        st.session_state.show_home_dialog = True

learner_thought = st.text_input(
    "What would you like to learn or practise?",
    placeholder="For example: Explain fractions, or give me a similar question about addition.",
    key="learner_thought",
)
if st.button("Create lesson", key="create_lesson"):
    try:
        with st.spinner("Creating your lesson with Ollama..."):
            st.session_state.step = backend.generate_step(st.session_state.category, learner_thought)
        st.session_state.end_time = None
        st.session_state.timeout_sent = False
        st.session_state.last_submit = None
        st.rerun()
    except ValueError as error:
        st.error(str(error))
    except OllamaError:
        st.error("Ollama is unavailable. Check that it is running locally and llama3.2:latest is installed.")

if timed_out and not st.session_state.timeout_sent:
    backend.on_event("time_expired",step_id=st.session_state.step)
    st.session_state.timeout_sent=True

if step["type"] == PageType.END:
    st.info("Tell me what you would like to learn, and I will create a lesson or practice question.")
    st.stop()

def goto_next():
    st.session_state.step=backend.next_step(st.session_state.step)
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
    st.markdown(f'<div class="question-title">{escape(step["question"])}</div>', unsafe_allow_html=True)
    txt=st.text_area("Answer",disabled=timed_out)
    show_submit_feedback()
    if timed_out:
        st.error("Time over. Press Next.")
    else:
        if st.button("Submit", key="subjective_submit", disabled=already_submitted()):
            backend.on_event("answer_submitted",step_id=st.session_state.step,answer=txt,timed_out=False)
            st.session_state.last_submit = {
                "step": st.session_state.step,
                "status": "success",
                "message": "Saved",
                "info": f"Suggested answer: {step.get('sample_answer', 'No sample answer available.')}",
                "submitted": True,
            }
            st.rerun()
    if st.button("Next", key="subjective_next"):
        goto_next()
