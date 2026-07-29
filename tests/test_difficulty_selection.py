import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend import LearningBackend


class DifficultySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        course_path = Path(self.temporary_directory.name)
        self.subject = course_path / "Maths"
        self.subject.mkdir()
        notes = "Prepared arithmetic notes."
        (self.subject / "notes.txt").write_text(notes, encoding="utf-8")
        notes_hash = hashlib.sha256(notes.encode("utf-8")).hexdigest()

        for difficulty in ("easy", "medium", "hard"):
            data = {
                "version": 1,
                "type": "mcq",
                "difficulty": difficulty,
                "notes_hash": notes_hash,
                "items": [{
                    "question": f"{difficulty.title()} question",
                    "options": ["A", "B", "C", "D"],
                    "correct_option": "A",
                    "explanation": f"{difficulty.title()} explanation",
                }],
            }
            (self.subject / f"objective_{difficulty}.json").write_text(
                json.dumps(data),
                encoding="utf-8",
            )

        self.backend = LearningBackend(
            course_path=course_path,
            llm_client=object(),
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_learning_session_uses_only_selected_difficulty(self):
        self.backend.start_course(
            "Maths",
            allowed_types=("mcq",),
            timer_preset="Normal",
            allowed_difficulties=("hard",),
        )

        step_index = self.backend.generate_initial_step("Maths")
        step = self.backend.get_step(step_index)

        self.assertEqual(step["difficulty"], "hard")
        self.assertEqual(step["question"], "Hard question")

    def test_mock_test_capacity_and_questions_use_selected_difficulties(self):
        self.assertEqual(
            self.backend.get_mock_test_capacity(
                "Maths",
                difficulties=("medium", "hard"),
            ),
            2,
        )

        test = self.backend.create_mock_test(
            {"Maths": 2},
            duration_minutes=30,
            correct_marks=4,
            incorrect_marks=-1,
            difficulties=("medium", "hard"),
        )

        self.assertEqual(test["difficulties"], ("medium", "hard"))
        self.assertEqual(
            {question["difficulty"] for question in test["questions"]},
            {"medium", "hard"},
        )

    def test_empty_or_unknown_difficulty_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "difficulty"):
            self.backend.start_course(
                "Maths",
                allowed_types=("mcq",),
                allowed_difficulties=(),
            )
        with self.assertRaisesRegex(ValueError, "difficulty"):
            self.backend.get_mock_test_capacity(
                "Maths",
                difficulties=("expert",),
            )


if __name__ == "__main__":
    unittest.main()
