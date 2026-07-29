import json
import tempfile
import unittest
from pathlib import Path

from backend import LearningBackend


class LearningProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.course_path = Path(self.temporary_directory.name)
        self.subject = self.course_path / "Subject"
        self.subject.mkdir()
        notes = "Durable learning progress."
        (self.subject / "notes.txt").write_text(notes, encoding="utf-8")
        notes_hash = LearningBackend._notes_hash(notes)
        bank = {
            "version": 1,
            "type": "mcq",
            "difficulty": "easy",
            "notes_hash": notes_hash,
            "items": [
                {
                    "question": f"Question {number}",
                    "options": ["A", "B", "C", "D"],
                    "correct_option": "A",
                    "explanation": "Because A is correct.",
                }
                for number in range(1, 3)
            ],
        }
        (self.subject / "objective_easy.json").write_text(
            json.dumps(bank),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _start_backend(self):
        backend = LearningBackend(
            course_path=self.course_path,
            llm_client=object(),
        )
        backend.start_course(
            "Subject",
            allowed_types=("mcq",),
            timer_preset="Infinite",
            allowed_difficulties=("easy",),
        )
        return backend

    def test_restart_skips_items_already_shown(self):
        first_backend = self._start_backend()
        first_step = first_backend.steps[
            first_backend.generate_initial_step("Subject")
        ]

        progress_path = self.subject / ".learning_progress.json"
        self.assertTrue(progress_path.is_file())
        self.assertEqual(
            first_backend.get_learning_progress("Subject")["seen_items"],
            1,
        )

        restarted_backend = self._start_backend()
        second_step = restarted_backend.steps[
            restarted_backend.generate_initial_step("Subject")
        ]

        self.assertNotEqual(first_step["question"], second_step["question"])
        self.assertEqual(
            restarted_backend.get_learning_progress("Subject")["seen_items"],
            2,
        )

    def test_completed_pool_restarts_without_growing_progress(self):
        first_backend = self._start_backend()
        first_backend.generate_initial_step("Subject")
        restarted_backend = self._start_backend()
        restarted_backend.generate_initial_step("Subject")

        completed_backend = self._start_backend()
        completed_backend.generate_initial_step("Subject")

        self.assertEqual(
            completed_backend.get_learning_progress("Subject")["seen_items"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
