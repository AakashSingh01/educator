"""Composition root for the learning backend."""

from pathlib import Path

from llm import LLMClient, create_llm_client

from .learning import LearningSessionMixin
from .mock_test import MockTestMixin
from .notes import NotesPreparationMixin
from .question_bank import QuestionBankMixin


class LearningBackend(NotesPreparationMixin, QuestionBankMixin, LearningSessionMixin, MockTestMixin):
    """Backend facade used by Streamlit and worker processes."""

    def __init__(self, course_path=None, llm_client=None):
        project_path = Path(__file__).resolve().parent.parent
        self.course_path = project_path / "course" if course_path is None else Path(course_path)
        self.llm: LLMClient = llm_client or create_llm_client()
        self.score = 0
        self.events = []
        self.answered_step_ids = set()
        self.ask_history = []
        self.steps = []
        self.learning_context = None
        self.learning_scope = ""
        self.learning_boundary_label = None
        self.learning_types = ("mcq", "subjective", "theory")
        self.learning_type_cycle = []
        self.timer_preset = "Infinite"
        self.prepared_item_ids = set()
        self.mock_test_session = None
        self.mock_test_counter = 0

    def get_categories(self):
        if not self.course_path.is_dir():
            return []
        return sorted(
            folder.name
            for folder in self.course_path.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        )
