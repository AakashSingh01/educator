import json
import tempfile
import unittest
from pathlib import Path

from backend import LearningBackend


def _bank(item_type, difficulty, items):
    return {
        "version": 1,
        "type": item_type,
        "difficulty": difficulty,
        "items": items,
    }


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.course_path = Path(self.temporary_directory.name)
        self.subject = self.course_path / "Maths"
        self.child = self.subject / "Algebra"
        self.sibling = self.subject / "Geometry"
        self.child.mkdir(parents=True)
        self.sibling.mkdir()
        (self.subject / "notes.txt").write_text("Parent-only notes", encoding="utf-8")
        (self.child / "notes.txt").write_text("Child notes with $x^2$.", encoding="utf-8")
        (self.sibling / "notes.txt").write_text("Sibling-only notes", encoding="utf-8")
        (self.subject / "objective_easy.json").write_text(
            json.dumps(_bank("mcq", "easy", [{
                "question": "Parent question",
                "options": ["1", "2", "3", "4"],
                "correct_option": "1",
                "explanation": "Parent explanation",
            }])),
            encoding="utf-8",
        )
        (self.child / "subjective_hard.json").write_text(
            json.dumps(_bank("subjective", "hard", [{
                "question": "Child question",
                "answer": "Child answer",
            }])),
            encoding="utf-8",
        )
        self.backend = LearningBackend(
            course_path=self.course_path,
            llm_client=object(),
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_reads_only_the_exact_selected_topic(self):
        topic = self.backend.get_reader_topic("Maths", "Algebra")

        self.assertEqual(topic["notes"], "Child notes with $x^2$.")
        self.assertEqual([item["question"] for item in topic["subjective"]], ["Child question"])
        self.assertEqual(topic["objective"], [])
        self.assertNotIn("Parent-only notes", topic["notes"])
        self.assertNotIn("Sibling-only notes", topic["notes"])

    def test_returns_only_direct_child_folders(self):
        topic = self.backend.get_reader_topic("Maths")

        self.assertEqual(topic["children"], ["Algebra", "Geometry"])
        self.assertEqual([item["question"] for item in topic["objective"]], ["Parent question"])

    def test_rejects_paths_outside_the_subject(self):
        with self.assertRaises(ValueError):
            self.backend.get_reader_topic("Maths", "../Geometry")


if __name__ == "__main__":
    unittest.main()
