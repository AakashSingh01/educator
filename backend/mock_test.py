"""Prepared multiple-choice mock-test assembly, attempts, and grading."""

import random


class MockTestMixin:
    """Create and grade a one-session mock test from prepared MCQ banks."""

    def _mock_test_candidates(self, subject):
        subject = self._folder_name(subject)
        if subject not in self.get_categories():
            raise ValueError("Choose a valid subject for the mock test.")

        candidates = []
        seen_identifiers = set()
        for identifier, step, context in self._prepared_item_candidates(subject, "", "mcq"):
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

    def get_mock_test_capacity(self, subject):
        """Return the number of usable prepared MCQs across a full subject."""

        return len(self._mock_test_candidates(subject))

    def create_mock_test(self, subject_question_counts, duration_minutes, correct_marks, incorrect_marks):
        """Create a shuffled, mutable test with exact counts per subject."""

        if not isinstance(subject_question_counts, dict) or not subject_question_counts:
            raise ValueError("Choose at least one subject and a question count.")
        if not isinstance(duration_minutes, (int, float)) or isinstance(duration_minutes, bool) or duration_minutes <= 0:
            raise ValueError("Test duration must be greater than zero minutes.")
        if not isinstance(correct_marks, (int, float)) or isinstance(correct_marks, bool) or correct_marks <= 0:
            raise ValueError("Correct-answer marks must be greater than zero.")
        if not isinstance(incorrect_marks, (int, float)) or isinstance(incorrect_marks, bool) or incorrect_marks > 0:
            raise ValueError("Incorrect-answer marks must be zero or negative.")

        questions = []
        normalized_counts = {}
        for raw_subject, requested_count in subject_question_counts.items():
            subject = self._folder_name(raw_subject)
            if not isinstance(requested_count, int) or isinstance(requested_count, bool) or requested_count <= 0:
                raise ValueError(f"Choose a positive question count for {subject}.")
            candidates = self._mock_test_candidates(subject)
            if requested_count > len(candidates):
                raise ValueError(
                    f"{subject} has only {len(candidates)} prepared objective questions, "
                    f"but {requested_count} were requested."
                )
            normalized_counts[subject] = requested_count
            questions.extend(random.sample(candidates, requested_count))

        random.shuffle(questions)
        self.mock_test_counter += 1
        self.mock_test_session = {
            "id": self.mock_test_counter,
            "questions": questions,
            "answers": {},
            "subject_question_counts": normalized_counts,
            "duration_seconds": int(round(duration_minutes * 60)),
            "correct_marks": float(correct_marks),
            "incorrect_marks": float(incorrect_marks),
            "submitted": False,
            "result": None,
        }
        self.on_event("mock_test_started", questions=len(questions), subjects=tuple(normalized_counts))
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
