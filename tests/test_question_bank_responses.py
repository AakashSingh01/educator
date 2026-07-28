import unittest

from backend.question_bank import QuestionBankMixin
from response_parsing import parse_json_response


class QuestionBankResponseTests(unittest.TestCase):
    def test_repairs_unescaped_latex_commands_in_json(self):
        response = r'{"question":"Find $\theta$ from $\frac{1}{2}$."}'

        parsed = parse_json_response(response)

        self.assertEqual(
            parsed["question"],
            r"Find $\theta$ from $\frac{1}{2}$.",
        )

    def test_accepts_named_difficulty_wrappers(self):
        response = {
            "questions": {
                "Easy Questions": ["One", "Two"],
                "Medium Items": ["Three", "Four"],
                "Hard": ["Five", "Six"],
            }
        }

        self.assertEqual(
            QuestionBankMixin._difficulty_entries(response, "easy"),
            ["One", "Two"],
        )

    def test_accepts_flat_items_with_extended_difficulty_labels(self):
        response = {
            "items": [
                {"difficulty": "Easy level", "question": "One"},
                {"difficulty": "Hard question", "question": "Two"},
            ]
        }

        self.assertEqual(
            QuestionBankMixin._difficulty_entries(response, "hard"),
            [{"difficulty": "Hard question", "question": "Two"}],
        )


if __name__ == "__main__":
    unittest.main()
