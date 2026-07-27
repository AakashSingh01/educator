"""Mock-test configuration, navigation, timing, and review screens."""

import time

import streamlit as st


def _format_remaining(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def _format_marks(value):
    return f"{value:+g}" if value else "0"


def _normalise_question_index(value, total_questions):
    """Convert stale widget/session values to a safe zero-based question index."""

    try:
        index = int(value)
    except (TypeError, ValueError):
        index = 0
    return min(max(0, index), max(0, total_questions - 1))


def _question_token(index):
    return f"question:{index}"


def _index_from_question_token(value, total_questions):
    if isinstance(value, str) and value.startswith("question:"):
        value = value.split(":", 1)[1]
    return _normalise_question_index(value, total_questions)


def _return_to_learning_home(backend):
    backend.clear_mock_test()
    st.session_state.mode = "learn"
    st.session_state.mock_test_question_index = 0
    st.session_state.mock_test_end_time = None
    st.session_state.mock_test_timed_out = False
    st.rerun()


def _render_mock_test_setup(backend):
    st.title("Mock test")
    st.caption("Build a timed objective test from your prepared question banks. Answers remain editable until final submission.")
    if st.button("← Back to learning", key="mock_test_back"):
        _return_to_learning_home(backend)

    subjects = st.multiselect(
        "Subjects to include",
        options=backend.get_categories(),
        key="mock_test_subjects",
        placeholder="Choose one or more subjects",
        help="Each selected subject contributes the exact number of prepared objective questions you choose below.",
    )
    if not subjects:
        st.info("Choose at least one subject to configure the test.")
        return

    capacities = {subject: backend.get_mock_test_capacity(subject) for subject in subjects}
    unavailable = [subject for subject, capacity in capacities.items() if not capacity]
    if unavailable:
        st.warning(
            "No prepared objective questions are available for: " + ", ".join(unavailable) + ". "
            "Run Question Preparation for those subjects first."
        )

    with st.form("mock_test_configuration"):
        st.subheader("Questions by subject")
        subject_counts = {}
        for subject in subjects:
            capacity = capacities[subject]
            if not capacity:
                continue
            subject_counts[subject] = st.number_input(
                f"{subject} questions (up to {capacity})",
                min_value=1,
                max_value=capacity,
                value=min(10, capacity),
                step=1,
                key=f"mock_test_count_{subject}",
            )

        st.subheader("Timing and marks")
        timing, correct, incorrect = st.columns(3)
        duration_minutes = timing.number_input(
            "Total test time (minutes)",
            min_value=1,
            value=180,
            step=15,
            key="mock_test_duration_minutes",
            help="Choose any duration you need; long tests are supported.",
        )
        correct_marks = correct.number_input(
            "Marks for a correct answer",
            min_value=0.01,
            value=4.0,
            step=0.25,
            format="%.2f",
            key="mock_test_correct_marks",
        )
        incorrect_marks = incorrect.number_input(
            "Marks for an incorrect answer",
            max_value=0.0,
            value=-1.0,
            step=0.25,
            format="%.2f",
            key="mock_test_incorrect_marks",
        )
        start = st.form_submit_button("Start mock test", type="primary", disabled=bool(unavailable))

    if not start:
        return
    try:
        test = backend.create_mock_test(
            subject_counts,
            duration_minutes,
            correct_marks,
            incorrect_marks,
        )
        st.session_state.mock_test_question_index = 0
        st.session_state[_active_question_key(test["id"])] = 0
        st.session_state[_navigator_key(test["id"])] = _question_token(0)
        st.session_state.mock_test_end_time = time.time() + test["duration_seconds"]
        st.session_state.mock_test_timed_out = False
        st.rerun()
    except ValueError as error:
        st.error(str(error))


def _navigator_key(test_id):
    return f"mock_test_jump_{test_id}"


def _active_question_key(test_id):
    return f"mock_test_active_question_{test_id}"


def _set_mock_test_question(index, test_id, total_questions):
    """Keep navigation in one stable state value, independent of the selectbox."""

    current_index = _normalise_question_index(index, total_questions)
    st.session_state[_active_question_key(test_id)] = current_index
    st.session_state[_navigator_key(test_id)] = _question_token(current_index)


def _select_mock_test_question(test_id, total_questions):
    navigator_key = _navigator_key(test_id)
    current_index = _index_from_question_token(
        st.session_state.get(navigator_key), total_questions
    )
    _set_mock_test_question(current_index, test_id, total_questions)


def _save_mock_test_answer(
    backend,
    question_index,
    options,
    answer_key,
    test_id,
    total_questions,
):
    selected_option = st.session_state.get(answer_key)
    answer_index = options.index(selected_option) if selected_option in options else None
    backend.record_mock_test_answer(question_index, answer_index)
    # A timer rerun must not move an answer submission back to Question 1.
    _set_mock_test_question(question_index, test_id, total_questions)


def _question_label(test, index):
    question_number = index + 1
    if not test["submitted"]:
        return (
            f"✓ Question {question_number} — attempted"
            if index in test["answers"]
            else f"○ Question {question_number} — not attempted"
        )
    outcome = test["result"]["outcomes"][index]["outcome"]
    labels = {
        "correct": f"✓ Question {question_number} — correct",
        "incorrect": f"✗ Question {question_number} — incorrect",
        "unattempted": f"○ Question {question_number} — not attempted",
    }
    return labels[outcome]


def _render_mock_test_summary(test):
    result = test["result"]
    st.success("Test submitted. Answers are now locked.")
    marks, correct, incorrect, unattempted = st.columns(4)
    marks.metric("Total marks", f"{result['total_marks']:g} / {result['maximum_marks']:g}")
    correct.metric("Correct", result["correct"])
    incorrect.metric("Incorrect", result["incorrect"])
    unattempted.metric("Not attempted", result["unattempted"])


def _render_mock_test_question(backend, test, current_index, total_questions):
    question = test["questions"][current_index]
    submitted = test["submitted"]
    st.subheader(f"Question {current_index + 1}")
    st.caption(f"{question['subject']} · {question['topic']}" + (f" · {question['difficulty'].title()}" if question.get("difficulty") else ""))
    st.write(question["question"])

    answer_key = f"mock_test_{test['id']}_answer_{current_index}"
    saved_answer = test["answers"].get(current_index)
    if answer_key not in st.session_state and saved_answer is not None:
        st.session_state[answer_key] = question["options"][saved_answer]
    st.radio(
        "Select one answer",
        question["options"],
        index=None,
        key=answer_key,
        disabled=submitted,
        on_change=_save_mock_test_answer if not submitted else None,
        args=(
            backend,
            current_index,
            question["options"],
            answer_key,
            test["id"],
            total_questions,
        ) if not submitted else None,
        persist_state="session",
    )

    if submitted:
        outcome = test["result"]["outcomes"][current_index]
        if outcome["outcome"] == "correct":
            st.success(f"Correct · {_format_marks(outcome['marks'])} marks")
        elif outcome["outcome"] == "incorrect":
            st.error(f"Incorrect · {_format_marks(outcome['marks'])} marks")
        else:
            st.warning("Not attempted · 0 marks")
        st.info(f"Correct answer: {question['correct_option']}\n\n{question['explanation']}")
        if question.get("reason"):
            st.caption(question["reason"])


@st.fragment(run_every=1)
def _render_mock_test_timer(backend, test_id, timer_slot):
    """Refresh only the countdown; leave the active question widgets untouched."""

    test = backend.get_mock_test()
    if not test or test["id"] != test_id or test["submitted"]:
        return

    end_time = st.session_state.get("mock_test_end_time")
    if end_time is None:
        end_time = time.time() + test["duration_seconds"]
        st.session_state.mock_test_end_time = end_time
    remaining = max(0, int(end_time - time.time()))
    with timer_slot:
        timer_slot.metric("Time left", _format_remaining(remaining))

    if remaining == 0:
        backend.submit_mock_test()
        st.session_state.mock_test_end_time = None
        st.session_state.mock_test_timed_out = True
        st.rerun()


def _render_mock_test_attempt(backend, test):
    total_questions = len(test["questions"])
    test_id = test["id"]
    navigator_key = _navigator_key(test_id)
    active_key = _active_question_key(test_id)
    navigator_options = [_question_token(index) for index in range(total_questions)]
    existing_active_index = st.session_state.get(active_key)
    if existing_active_index is None:
        # Preserve the selected question for a test that was already open
        # before the stable active-question key was introduced.
        existing_active_index = _index_from_question_token(
            st.session_state.get(
                navigator_key,
                st.session_state.get("mock_test_question_index", 0),
            ),
            total_questions,
        )
    active_index = _normalise_question_index(existing_active_index, total_questions)
    # Set both values before their widgets render. This also heals stale state
    # left by tests created before the stable active-question key existed.
    _set_mock_test_question(active_index, test_id, total_questions)

    st.title("Mock test review" if test["submitted"] else "Mock test")
    progress = backend.get_mock_test_progress()
    status, timer, marks = st.columns(3)
    status.metric("Attempted", f"{progress['attempted']} / {progress['total']}")
    if test["submitted"]:
        timer.metric("Time left", "Submitted")
    else:
        _render_mock_test_timer(backend, test_id, timer)
    marks.metric("Marking", f"{_format_marks(test['correct_marks'])} / {_format_marks(test['incorrect_marks'])}")
    st.progress(progress["attempted"] / progress["total"], text=f"{progress['unattempted']} question(s) still not attempted")

    if st.session_state.get("mock_test_timed_out"):
        st.warning("Time is over, so the test was submitted automatically.")

    if test["submitted"]:
        _render_mock_test_summary(test)

    st.selectbox(
        "Jump to any question",
        options=navigator_options,
        format_func=lambda token: _question_label(
            test, _index_from_question_token(token, total_questions)
        ),
        key=navigator_key,
        on_change=_select_mock_test_question,
        args=(test_id, total_questions),
        help="Search by question number in this list. The icon shows whether the question is attempted, and after submission whether it is correct.",
    )
    current_index = _normalise_question_index(
        st.session_state.get(active_key), total_questions
    )
    _render_mock_test_question(backend, test, current_index, total_questions)

    navigation = st.container(horizontal=True)
    navigation.button(
        "Previous question",
        disabled=current_index == 0,
        on_click=_set_mock_test_question,
        args=(current_index - 1, test_id, total_questions),
        key=f"mock_test_previous_{test_id}_{current_index}",
    )
    navigation.button(
        "Next question",
        disabled=current_index == total_questions - 1,
        on_click=_set_mock_test_question,
        args=(current_index + 1, test_id, total_questions),
        key=f"mock_test_next_{test_id}_{current_index}",
    )

    if test["submitted"]:
        if st.button("Return to learning home", key=f"mock_test_home_{test_id}"):
            _return_to_learning_home(backend)
        return

    st.divider()
    st.checkbox(
        "I understand that final submission locks every answer.",
        key=f"mock_test_confirm_submit_{test_id}",
    )
    if st.button(
        "Submit final test",
        type="primary",
        disabled=not st.session_state[f"mock_test_confirm_submit_{test_id}"],
        key=f"mock_test_submit_{test_id}",
    ):
        backend.submit_mock_test()
        st.session_state.mock_test_end_time = None
        st.session_state.mock_test_timed_out = False
        st.rerun()


def render_mock_test(backend):
    test = backend.get_mock_test()
    if test is None:
        _render_mock_test_setup(backend)
        return
    _render_mock_test_attempt(backend, test)
