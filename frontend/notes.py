"""Notes editing and reusable question-preparation screens."""

import streamlit as st

from llm import LLMError


def _format_estimate(seconds):
    seconds = max(1, int(round(seconds)))
    if seconds < 60:
        return f"about {seconds}s"
    minutes, seconds = divmod(seconds, 60)
    return f"about {minutes}m {seconds}s" if seconds else f"about {minutes}m"


def render_question_preparation_run(backend, subject):
    st.subheader("Question Preparation Run")
    st.caption(
        "Creates nine reusable JSON files beside every notes.txt: Easy, Medium, and Hard "
        "subjective questions, objective questions, and theory cards. Both actions include the selected "
        "topic itself and every nested subtopic."
    )
    scope_key = f"question_prep_scope_{subject}"
    st.session_state.setdefault(scope_key, "")
    scope_mode = st.radio("Preparation scope", ["Whole subject", "Choose a topic or subtopic"], horizontal=True, key=f"question_prep_mode_{subject}", help="A selected topic includes that topic and every descendant subtopic with notes.")
    if scope_mode == "Whole subject":
        st.session_state[scope_key] = ""
        selected_scope = run_scope = ""
        st.caption(f"Selected: {subject} and all of its subtopics")
    else:
        selected_scope = st.session_state[scope_key]
        run_scope = selected_scope
        st.caption(f"Browsing: {subject if not selected_scope else f'{subject} / {selected_scope}'}")
        controls = st.columns(2)
        if controls[0].button("Use subject root", key=f"question_prep_root_{subject}"):
            st.session_state[scope_key] = ""
            st.rerun()
        if controls[1].button("Go up one level", key=f"question_prep_up_{subject}", disabled=not selected_scope):
            st.session_state[scope_key] = selected_scope.rsplit("/", 1)[0] if "/" in selected_scope else ""
            st.rerun()
        direct_topics = backend.get_direct_learning_subtopics(subject, selected_scope)
        if direct_topics:
            topic_filter = st.text_input("Filter direct subtopics", placeholder="Type to narrow the list", key=f"question_prep_filter_{subject}_{selected_scope}").casefold()
            matches = [topic for topic in direct_topics if topic_filter in topic.casefold()]
            visible = matches[:20]
            if len(matches) > 20:
                st.caption("Showing the first 20 matches. Refine the filter to narrow further.")
            if visible:
                next_topic = st.selectbox("Direct subtopic to prepare or open", options=[""] + visible, format_func=lambda value: "Choose a direct subtopic" if not value else value, key=f"question_prep_child_{subject}_{selected_scope}")
                if next_topic:
                    run_scope = f"{selected_scope}/{next_topic}" if selected_scope else next_topic
                if st.button("Open selected subtopic", key=f"question_prep_open_{subject}_{selected_scope}", disabled=not next_topic):
                    st.session_state[scope_key] = run_scope
                    st.rerun()
            else:
                st.info("No direct subtopics match that filter.")
        st.caption(f"Selected run boundary: {subject if not run_scope else f'{subject} / {run_scope}'}")

    notes_topic_count = len(backend.list_question_bank_topics(subject, run_scope))
    st.caption(f"This run will process {notes_topic_count} folder(s) that contain notes.txt.")
    run_action = st.radio("Question and theory files", ["Create if missing", "Regenerate for all"], horizontal=True, key=f"question_prep_action_{subject}", help="Create if missing leaves valid files unchanged. Regenerate for all overwrites all nine prepared files in every selected topic.")
    if st.button("Start Question Preparation Run", type="primary", use_container_width=True, key=f"question_prep_start_{subject}"):
        try:
            progress_bar = st.progress(0, text="Finding notes topics to prepare...")
            generated_durations = []

            def update_progress(completed, total, result):
                if not total:
                    progress_bar.progress(100, text="No notes topics found.")
                    return
                label = result.get("topic") or subject
                if result.get("status") == "generated" and result.get("elapsed_seconds") is not None:
                    generated_durations.append(result["elapsed_seconds"])
                estimate = ""
                if generated_durations:
                    estimate = f" Estimated remaining: {_format_estimate(sum(generated_durations) / len(generated_durations) * max(0, total - completed))}."
                progress_bar.progress(int(completed * 100 / total), text=f"Prepared {completed} of {total} topic folders: {label}.{estimate}")

            with st.spinner("Preparing reusable questions and theory cards. This can take a little while..."):
                summary = backend.prepare_question_banks(subject, run_scope, overwrite=run_action == "Regenerate for all", progress_callback=update_progress)
            if summary["topics"]:
                progress_bar.progress(100, text="Question preparation complete.")
            st.success(f"Question preparation finished across {summary['topics']} notes topic(s): {summary['generated']} topic(s) generated, {summary['cached']} unchanged topic(s) reused.")
            if summary["parallel_fallback"]:
                st.info(summary["parallel_fallback"])
            if summary["skipped"]:
                st.warning("Skipped: " + "; ".join(f"{entry.get('topic') or subject} ({entry.get('message')})" for entry in summary["skipped"]))
            if summary["failed"]:
                st.error("Some topics could not be prepared: " + "; ".join(f"{entry.get('topic') or subject} ({entry.get('message')})" for entry in summary["failed"]))
        except (ValueError, LLMError) as error:
            st.error(str(error))


def render_notes_preparation(backend):
    st.title("Prepare Notes")
    st.caption("Review each topic, choose its direct subtopics, and build the notes structure in-depth.")
    if st.button("← Back to learning", key="notes_back"):
        st.session_state.mode = "learn"
        st.session_state.notes_subject = None
        st.rerun()

    subject = st.session_state.notes_subject
    if subject is None:
        subjects = backend.get_categories()
        selected_subject = st.selectbox("Existing subject folder", options=[""] + subjects, format_func=lambda value: "Choose an existing subject" if not value else value)
        new_subject = st.text_input("Or create a new subject folder")
        if st.button("Start or resume notes", key="start_notes"):
            try:
                requested_subject = new_subject.strip() or selected_subject
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

    st.caption(f"Subject: {subject} · Completed: {len(progress['completed'])} · Waiting in DFS stack: {len(progress['queue'])}")
    if st.button("Stop and save progress", key="notes_stop"):
        st.session_state.notes_subject = None
        st.rerun()
    with st.expander("Prepare reusable questions and theory", expanded=False):
        render_question_preparation_run(backend, subject)

    navigation = st.radio("Notes workflow", ["Continue in-depth", "Choose a topic to edit"], horizontal=True, key=f"notes_navigation_{subject}")
    picker_edit_key = f"notes_editing_selected_{subject}"
    last_navigation_key = f"notes_last_navigation_{subject}"
    if st.session_state.get(last_navigation_key) != navigation:
        st.session_state[picker_edit_key] = False
        st.session_state[last_navigation_key] = navigation
    if navigation == "Choose a topic to edit" and not st.session_state.get(picker_edit_key, False):
        browse_key = f"notes_browse_scope_{subject}"
        st.session_state.setdefault(browse_key, "")
        browse_scope = st.session_state[browse_key]
        st.caption(f"Browsing: {subject if not browse_scope else f'{subject} / {browse_scope}'}")
        controls = st.columns(2)
        if controls[0].button("Use subject root", key=f"notes_browse_root_{subject}"):
            st.session_state[browse_key] = ""
            st.rerun()
        if controls[1].button("Go up one level", key=f"notes_browse_up_{subject}", disabled=not browse_scope):
            st.session_state[browse_key] = browse_scope.rsplit("/", 1)[0] if "/" in browse_scope else ""
            st.rerun()
        direct_topics = backend.get_direct_learning_subtopics(subject, browse_scope)
        if direct_topics:
            topic_filter = st.text_input("Filter direct subtopics", placeholder="Type to narrow the list", key=f"notes_browse_filter_{subject}_{browse_scope}").casefold()
            matches = [topic for topic in direct_topics if topic_filter in topic.casefold()]
            visible = matches[:20]
            if len(matches) > 20:
                st.caption("Showing the first 20 matches. Refine the filter to narrow further.")
            if visible:
                next_topic = st.selectbox("Direct subtopic", options=visible, key=f"notes_browse_child_{subject}_{browse_scope}")
                if st.button("Open subtopic", key=f"notes_browse_open_{subject}_{browse_scope}"):
                    st.session_state[browse_key] = f"{browse_scope}/{next_topic}" if browse_scope else next_topic
                    st.rerun()
            else:
                st.info("No direct subtopics match that filter.")
        if st.button("Edit this topic", key="open_notes_topic"):
            try:
                backend.select_notes_topic(subject, browse_scope)
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
        restart, another = st.columns(2)
        if restart.button("Revisit this subject from the root", key="notes_restart"):
            backend.begin_notes_session(subject, restart=True)
            st.rerun()
        if another.button("Prepare another subject", key="notes_another"):
            st.session_state.notes_subject = None
            st.rerun()
        return

    st.subheader(topic["label"])
    if topic["existing_subtopics"]:
        st.info("Existing subtopic folders: " + ", ".join(topic["existing_subtopics"]))
    safe_key = topic["relative_path"].replace("/", "_") or "root"
    draft_key = f"notes_draft_{subject}_{safe_key}"
    instruction_key = f"notes_instruction_{subject}_{safe_key}"
    suggestions_key = f"notes_suggestions_{subject}_{safe_key}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = topic["notes"]
    note_instruction = st.text_input("How should these notes be improved? (optional)", placeholder="For example: add a worked example, simplify the language, or focus on definitions.", key=instruction_key)
    if st.button("Regenerate notes" if topic["notes"] else "Generate notes", key=f"generate_{safe_key}"):
        try:
            with st.spinner("Drafting notes..."):
                st.session_state[draft_key] = backend.generate_topic_notes(subject, topic["relative_path"], note_instruction)
            st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))
    notes_draft = st.text_area("Notes (edit until satisfied)", height=300, key=draft_key)
    if st.button("Save notes", key=f"save_{safe_key}"):
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
            selected_existing = st.selectbox("Subtopic to rename or remove", options=topic["existing_subtopics"], key=f"manage_{safe_key}")
            renamed = st.text_input("Rename selected subtopic to", key=f"rename_{safe_key}")
            if st.button("Rename subtopic", key=f"rename_button_{safe_key}"):
                try:
                    backend.rename_subtopic(subject, topic["relative_path"], selected_existing, renamed)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
            confirmed = st.checkbox("I understand removal deletes this subtopic and all nested notes.", key=f"remove_confirm_{safe_key}")
            if st.button("Remove selected subtopic", key=f"remove_button_{safe_key}"):
                if not confirmed:
                    st.error("Confirm removal before deleting a subtopic.")
                else:
                    try:
                        backend.remove_subtopic(subject, topic["relative_path"], selected_existing)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

    instruction = st.text_input("Instruction for subtopics (optional)", placeholder="For example: focus on practical concepts, exclude advanced topics, or suggest only five.", key=f"subtopic_instruction_{subject}_{safe_key}")
    if st.button("Suggest or regenerate subtopics", key=f"suggest_{safe_key}"):
        try:
            with st.spinner("Finding focused direct subtopics..."):
                st.session_state[suggestions_key] = backend.suggest_subtopics(subject, topic["relative_path"], instruction)
            st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))
    suggestions = st.session_state.get(suggestions_key, [])
    selected_subtopics = st.multiselect("Choose subtopics to create or prepare", options=list(dict.fromkeys(topic["existing_subtopics"] + suggestions)), help="Only selected subtopics are added to the saved DFS stack.", key=f"selected_{safe_key}")
    manual = st.text_input("Add other direct subtopics (comma-separated)", key=f"manual_{safe_key}")
    if st.button("Confirm subtopics and continue in-depth", key=f"continue_{safe_key}"):
        try:
            backend.complete_notes_topic(subject, topic["relative_path"], selected_subtopics + [name.strip() for name in manual.split(",") if name.strip()])
            st.rerun()
        except ValueError as error:
            st.error(str(error))
