"""Prepared multiple-choice mock-test assembly, attempts, and grading."""

import random
from pathlib import Path

from config.question_bank import normalise_difficulties


class MockTestMixin:
    """Create and grade a one-session mock test from prepared MCQ banks."""

    def _mock_test_candidates(self, subject, scope="", difficulties=None):
        """Return prepared MCQs in one subject or a topic subtree."""

        subject = self._folder_name(subject)
        difficulties = normalise_difficulties(difficulties)
        if subject not in self.get_categories():
            raise ValueError("Choose a valid subject for the mock test.")
        if not isinstance(scope, str) or scope not in self.get_learning_scopes(subject):
            raise ValueError("Choose a valid subject, topic, or subtopic for the mock test.")

        candidates = []
        seen_identifiers = set()
        for identifier, step, context in self._prepared_item_candidates(
            subject,
            scope,
            "mcq",
            difficulties,
        ):
            if identifier in seen_identifiers:
                continue
            seen_identifiers.add(identifier)
            candidates.append({
                "id": identifier,
                "subject": subject,
                "topic": context["label"],
                "question": step["question"],
                "options": list(step["options"]),
                "answer": step["answer"],
                "correct_option": step["correct_option"],
                "explanation": step["explanation"],
                "reason": step.get("reason", ""),
                "difficulty": step.get("difficulty"),
            })
        return candidates

    def get_mock_test_capacity(self, subject, scope="", difficulties=None):
        """Return the usable prepared MCQs in a subject or its topic subtree."""

        return len(self._mock_test_candidates(subject, scope, difficulties))

    @staticmethod
    def _scope_label(subject, scope):
        return subject if not scope else f"{subject} / {scope}"

    @staticmethod
    def _scopes_overlap(first_scope, second_scope):
        """Return whether two subject-relative topic trees share questions."""

        if not first_scope or not second_scope:
            return True
        first_path, second_path = Path(first_scope), Path(second_scope)
        return (
            first_path == second_path
            or first_path in second_path.parents
            or second_path in first_path.parents
        )

    def _normalise_mock_test_scopes(self, scope_question_counts):
        """Accept new scope requests and the legacy subject-to-count mapping."""

        if isinstance(scope_question_counts, dict):
            raw_requests = [
                {"subject": subject, "scope": "", "count": count}
                for subject, count in scope_question_counts.items()
            ]
        elif isinstance(scope_question_counts, (list, tuple)):
            raw_requests = list(scope_question_counts)
        else:
            raise ValueError("Choose at least one subject, topic, or subtopic and a question count.")
        if not raw_requests:
            raise ValueError("Choose at least one subject, topic, or subtopic and a question count.")

        requests = []
        for raw_request in raw_requests:
            if not isinstance(raw_request, dict):
                raise ValueError("Each mock-test area must include a subject and question count.")
            raw_subject = raw_request.get("subject")
            raw_scope = raw_request.get("scope", "")
            requested_count = raw_request.get("count")
            if not isinstance(raw_subject, str) or not raw_subject.strip():
                raise ValueError("Choose a valid subject for every mock-test area.")
            if not isinstance(raw_scope, str):
                raise ValueError("Choose a valid topic or subtopic for every mock-test area.")
            if not isinstance(requested_count, int) or isinstance(requested_count, bool) or requested_count <= 0:
                raise ValueError("Choose a positive question count for every mock-test area.")
            subject = self._folder_name(raw_subject)
            scope = raw_scope.strip()
            if scope not in self.get_learning_scopes(subject):
                raise ValueError(f"Choose a valid topic or subtopic for {subject}.")
            requests.append({"subject": subject, "scope": scope, "count": requested_count})

        for index, request in enumerate(requests):
            for other_request in requests[index + 1:]:
                if request["subject"] != other_request["subject"]:
                    continue
                if self._scopes_overlap(request["scope"], other_request["scope"]):
                    raise ValueError(
                        "Choose non-overlapping areas. A full subject already includes its topics and subtopics."
                    )
        return requests

    def create_mock_test(
        self,
        scope_question_counts,
        duration_minutes,
        correct_marks,
        incorrect_marks,
        difficulties=None,
    ):
        """Create a shuffled, mutable test with exact counts per selected area."""

        difficulties = normalise_difficulties(difficulties)
        if not isinstance(duration_minutes, (int, float)) or isinstance(duration_minutes, bool) or duration_minutes <= 0:
            raise ValueError("Test duration must be greater than zero minutes.")
        if not isinstance(correct_marks, (int, float)) or isinstance(correct_marks, bool) or correct_marks <= 0:
            raise ValueError("Correct-answer marks must be greater than zero.")
        if not isinstance(incorrect_marks, (int, float)) or isinstance(incorrect_marks, bool) or incorrect_marks > 0:
            raise ValueError("Incorrect-answer marks must be zero or negative.")

        requests = self._normalise_mock_test_scopes(scope_question_counts)
        questions = []
        selected_identifiers = set()
        normalized_scope_counts = {}
        normalized_subject_counts = {}
        for request in requests:
            subject, scope, requested_count = (
                request["subject"],
                request["scope"],
                request["count"],
            )
            label = self._scope_label(subject, scope)
            candidates = [
                candidate
                for candidate in self._mock_test_candidates(
                    subject,
                    scope,
                    difficulties,
                )
                if candidate["id"] not in selected_identifiers
            ]
            if requested_count > len(candidates):
                raise ValueError(
                    f"{label} has only {len(candidates)} prepared objective questions, "
                    f"but {requested_count} were requested."
                )
            selected = random.sample(candidates, requested_count)
            selected_identifiers.update(candidate["id"] for candidate in selected)
            normalized_scope_counts[label] = requested_count
            normalized_subject_counts[subject] = normalized_subject_counts.get(subject, 0) + requested_count
            questions.extend(selected)

        random.shuffle(questions)
        self.mock_test_counter += 1
        self.mock_test_session = {
            "id": self.mock_test_counter,
            "questions": questions,
            "answers": {},
            "subject_question_counts": normalized_subject_counts,
            "scope_question_counts": normalized_scope_counts,
            "difficulties": difficulties,
            "duration_seconds": int(round(duration_minutes * 60)),
            "correct_marks": float(correct_marks),
            "incorrect_marks": float(incorrect_marks),
            "submitted": False,
            "result": None,
        }
        self.on_event("mock_test_started", questions=len(questions), scopes=tuple(normalized_scope_counts))
        return self.mock_test_session

    def get_mock_test(self):
        return self.mock_test_session

    def clear_mock_test(self):
        self.mock_test_session = None

    def record_mock_test_answer(self, question_index, answer_index):
        test = self.get_mock_test()
        if not test:
            raise ValueError("Start a mock test first.")
        if test["submitted"]:
            raise ValueError("This mock test has already been submitted.")
        if not isinstance(question_index, int) or not 0 <= question_index < len(test["questions"]):
            raise ValueError("Choose a valid mock-test question.")
        if answer_index is None:
            test["answers"].pop(question_index, None)
            return
        if not isinstance(answer_index, int) or not 0 <= answer_index < len(test["questions"][question_index]["options"]):
            raise ValueError("Choose a valid answer option.")
        test["answers"][question_index] = answer_index

    def get_mock_test_progress(self):
        test = self.get_mock_test()
        if not test:
            return {"total": 0, "attempted": 0, "unattempted": 0}
        total = len(test["questions"])
        attempted = len(test["answers"])
        return {"total": total, "attempted": attempted, "unattempted": total - attempted}

    def submit_mock_test(self):
        """Lock answers and return the final score and per-question outcomes."""

        test = self.get_mock_test()
        if not test:
            raise ValueError("Start a mock test first.")
        if test["submitted"]:
            return test["result"]

        correct = incorrect = unattempted = 0
        total_marks = 0.0
        outcomes = []
        for index, question in enumerate(test["questions"]):
            selected_answer = test["answers"].get(index)
            if selected_answer is None:
                outcome, marks = "unattempted", 0.0
                unattempted += 1
            elif selected_answer == question["answer"]:
                outcome, marks = "correct", test["correct_marks"]
                correct += 1
            else:
                outcome, marks = "incorrect", test["incorrect_marks"]
                incorrect += 1
            total_marks += marks
            outcomes.append({"outcome": outcome, "marks": marks})

        result = {
            "total_marks": total_marks,
            "maximum_marks": len(test["questions"]) * test["correct_marks"],
            "correct": correct,
            "incorrect": incorrect,
            "unattempted": unattempted,
            "outcomes": outcomes,
        }
        test["submitted"] = True
        test["result"] = result
        self.on_event("mock_test_submitted", total_marks=total_marks, correct=correct, incorrect=incorrect)
        return result
