# app.py
import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from backend import LearningBackend, PageType

st.set_page_config(page_title="Learning App", layout="wide")
backend = LearningBackend()

defaults = {
    "started": False,
    "category": None,
    "step": 0,
    "end_time": None,
    "timeout_sent": False,
    "show_home_dialog": False,
}
for k,v in defaults.items():
    st.session_state.setdefault(k,v)

def load_step():
    step = backend.get_step(st.session_state.step)
    if step["type"] != PageType.END and st.session_state.end_time is None:
        st.session_state.end_time = time.time()+step["time_limit"]
    return step

if not st.session_state.started:
    st.title("Learning App")
    st.write("Choose a category")
    
    cats=["Maths","Science","History", "Test"]
    cols=st.columns(len(cats))
    for i,c in enumerate(cats):
        if cols[i].button(c):
            backend.on_event("chapter_started",category=c)
            st.session_state.category=c
            st.session_state.started=True
            st.session_state.step=0
            st.session_state.end_time=None
            st.rerun()
    topic=st.text_input("Custom topic")
    if st.button("Start Custom") and topic:
        backend.on_event("chapter_started",category=topic)
        st.session_state.category=topic
        st.session_state.started=True
        st.session_state.step=0
        st.session_state.end_time=None
        st.rerun()
    st.stop()



if st.session_state.show_home_dialog:
    st.warning("Leave this chapter?")
    c1,c2=st.columns(2)
    with c1:
        if st.button("Yes"):
            backend.on_event("chapter_closed",step_id=st.session_state.step)
            st.session_state.started=False
            st.session_state.step=0
            st.session_state.end_time=None
            st.session_state.show_home_dialog=False
            st.rerun()
    with c2:
        if st.button("Cancel"):
            st.session_state.show_home_dialog=False
            st.rerun()

st_autorefresh(interval=1000,key="tick")
step=load_step()

if step["type"]==PageType.END:
    st.success("Completed!")
    if st.button("Restart"):
        st.session_state.started=False
        st.session_state.step=0
        st.session_state.end_time=None
        st.rerun()
    st.stop()

remaining=max(0,int(st.session_state.end_time-time.time()))
timed_out=remaining==0

# Header
col1, col2, col3 = st.columns([6, 2, 1])

with col1:
    st.subheader(f"📚 {st.session_state.category}")

with col2:
    st.metric("Time Left", f"{remaining}s")

with col3:
    if st.button("🏠 Home", use_container_width=True):
        st.session_state.show_home_dialog = True

st.metric("Time Left",f"{remaining}s")

if timed_out and not st.session_state.timeout_sent:
    backend.on_event("time_expired",step_id=st.session_state.step)
    st.session_state.timeout_sent=True

def goto_next():
    st.session_state.step=backend.next_step(st.session_state.step)
    st.session_state.end_time=None
    st.session_state.timeout_sent=False
    st.rerun()

if step["type"]==PageType.THEORY:
    st.header(step["title"])
    st.write(step["content"])
    if timed_out:
        st.warning("Reading time finished.")
    if st.button("Next"):
        backend.on_event("theory_completed",step_id=st.session_state.step)
        goto_next()

elif step["type"]==PageType.MCQ:
    st.header(step["question"])
    ans=st.radio("Select",step["options"],disabled=timed_out)
    if timed_out:
        st.error("Time over. Press Next.")
    else:
        if st.button("Submit"):
            idx=step["options"].index(ans)
            ok=backend.check_answer(step,idx)
            backend.on_event("answer_submitted",step_id=st.session_state.step,answer=idx,correct=ok,timed_out=False)
            st.success("Correct" if ok else "Incorrect")
            st.info(step["explanation"])
    if st.button("Next"):
        goto_next()

elif step["type"]==PageType.SUBJECTIVE:
    st.header(step["question"])
    txt=st.text_area("Answer",disabled=timed_out)
    if timed_out:
        st.error("Time over. Press Next.")
    else:
        if st.button("Submit"):
            backend.on_event("answer_submitted",step_id=st.session_state.step,answer=txt,timed_out=False)
            st.success("Saved")
    if st.button("Next"):
        goto_next()
