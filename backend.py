import json
import random
import re
from enum import Enum
from pathlib import Path

from llm import OllamaListener

class PageType(Enum):
    CATEGORY="category"
    THEORY="theory"
    MCQ="mcq"
    SUBJECTIVE="subjective"
    END="end"

class LearningBackend:
    def __init__(self, course_path=None, llm_client=None):
        project_path = Path(__file__).resolve().parent
        self.course_path = project_path / "course" if course_path is None else Path(course_path)
        self.llm = llm_client or OllamaListener()
        self.score=0
        self.events=[]
        self.answered_step_ids=set()
        self.conversation_history=[]
        self.steps=[]

    def get_categories(self):
        """Return visible subject folders from the configured course directory."""
        if not self.course_path.is_dir():
            return []
        return sorted(
            folder.name
            for folder in self.course_path.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        )

    # Notes preparation -------------------------------------------------
    # A persisted FIFO queue makes the topic traversal breadth-first and resumable.
    def _notes_progress_path(self):
        return self.course_path / ".notes_progress.json"

    def _load_notes_progress(self):
        progress_path = self._notes_progress_path()
        if not progress_path.is_file():
            return {}
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_notes_progress(self, progress):
        self.course_path.mkdir(parents=True, exist_ok=True)
        self._notes_progress_path().write_text(
            json.dumps(progress, indent=2, sort_keys=True), encoding="utf-8"
        )

    @staticmethod
    def _folder_name(name):
        if not isinstance(name, str):
            raise ValueError("A topic name is required.")
        clean_name = name.strip()
        if not clean_name or clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name:
            raise ValueError("Topic names cannot be empty or contain path separators.")
        if clean_name.startswith("."):
            raise ValueError("Topic names cannot start with a dot.")
        return clean_name

    def begin_notes_session(self, subject, max_depth=2, restart=False):
        """Create or resume a subject's persisted notes-preparation queue."""
        subject = self._folder_name(subject)
        try:
            max_depth = max(0, int(max_depth))
        except (TypeError, ValueError) as error:
            raise ValueError("Maximum depth must be a whole number.") from error

        self.course_path.mkdir(parents=True, exist_ok=True)
        (self.course_path / subject).mkdir(exist_ok=True)
        progress = self._load_notes_progress()
        if restart or subject not in progress:
            progress[subject] = {"queue": [""], "completed": [], "max_depth": max_depth}
        self._save_notes_progress(progress)
        return self.get_notes_progress(subject)

    def get_notes_progress(self, subject):
        session = self._load_notes_progress().get(subject)
        if not isinstance(session, dict):
            return None
        queue = session.get("queue")
        completed = session.get("completed")
        if not isinstance(queue, list) or not isinstance(completed, list):
            return None
        return {
            "queue": queue,
            "completed": completed,
            "max_depth": session.get("max_depth", 2),
        }

    def _topic_folder(self, subject, relative_topic):
        subject = self._folder_name(subject)
        if not isinstance(relative_topic, str):
            raise ValueError("Invalid topic path.")
        relative_path = Path(relative_topic)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Invalid topic path.")
        folder = (self.course_path / subject / relative_path).resolve()
        root = (self.course_path / subject).resolve()
        if folder != root and root not in folder.parents:
            raise ValueError("Invalid topic path.")
        return folder

    def get_current_notes_topic(self, subject):
        progress = self.get_notes_progress(subject)
        if not progress or not progress["queue"]:
            return None
        relative_topic = progress["queue"][0]
        folder = self._topic_folder(subject, relative_topic)
        folder.mkdir(parents=True, exist_ok=True)
        notes_path = folder / "notes.txt"
        try:
            notes = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else ""
        except OSError as error:
            raise ValueError(f"Could not read notes for this topic: {error}") from error
        children = sorted(
            child.name for child in folder.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
        return {
            "relative_path": relative_topic,
            "label": subject if not relative_topic else f"{subject} / {relative_topic}",
            "depth": len(Path(relative_topic).parts) if relative_topic else 0,
            "notes": notes,
            "existing_subtopics": children,
            "max_depth": progress["max_depth"],
        }

    def generate_topic_notes(self, subject, relative_topic, instruction=""):
        topic = self.get_current_notes_topic(subject)
        if not topic or topic["relative_path"] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        user_instruction = instruction.strip() if isinstance(instruction, str) else ""
        prompt = (
            f"Subject: {subject}\nTopic path: {topic['label']}\n"
            f"Additional learner instruction: {user_instruction or 'None'}\n\n"
            "Write clear, self-contained study notes for this topic. Return exactly JSON as "
            '{"notes":"..."}. Use concise Markdown-style headings and examples where useful. '
            "Cover only this topic's overview, core ideas, terminology, and relationships. Do not explain "
            "likely child subtopics in depth; they will have their own notes files."
        )
        response = self.llm.chat(
            prompt,
            system_prompt="You write accurate, concise educational notes. Return valid JSON only.",
        )
        try:
            notes = json.loads(response).get("notes")
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return valid notes. Please try again.") from error
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("The model returned empty notes. Please try again.")
        return notes.strip()

    def save_topic_notes(self, subject, relative_topic, notes):
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("Notes cannot be empty.")
        folder = self._topic_folder(subject, relative_topic)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            (folder / "notes.txt").write_text(notes.strip() + "\n", encoding="utf-8")
        except OSError as error:
            raise ValueError(f"Could not save notes: {error}") from error

    def suggest_subtopics(self, subject, relative_topic):
        topic = self.get_current_notes_topic(subject)
        if not topic or topic["relative_path"] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        prompt = (
            f"Subject: {subject}\nTopic: {topic['label']}\nNotes:\n{topic['notes']}\n\n"
            "Suggest 3 to 8 direct subtopics for a study-notes folder structure. Return exactly JSON as "
            '{"subtopics":["Topic one","Topic two"]}. Suggest only direct children, not grandchildren, '
            "and avoid duplicates or topics already adequately covered in the parent notes."
        )
        response = self.llm.chat(
            prompt,
            system_prompt="You design concise, non-overlapping educational topic outlines. Return valid JSON only.",
        )
        try:
            subtopics = json.loads(response).get("subtopics")
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return valid subtopics. Please try again.") from error
        if not isinstance(subtopics, list):
            raise ValueError("The model returned invalid subtopics. Please try again.")
        cleaned = []
        for subtopic in subtopics[:8]:
            try:
                name = self._folder_name(subtopic)
            except ValueError:
                continue
            if name.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(name)
        if not cleaned:
            raise ValueError("The model did not suggest usable subtopics. Please try again.")
        return cleaned

    def complete_notes_topic(self, subject, relative_topic, selected_subtopics):
        """Confirm children, enqueue them at the end, and move to the next BFS topic."""
        progress = self._load_notes_progress()
        session = progress.get(subject)
        if not isinstance(session, dict) or not session.get("queue") or session["queue"][0] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        max_depth = session.get("max_depth", 2)
        depth = len(Path(relative_topic).parts) if relative_topic else 0
        selected_subtopics = selected_subtopics or []
        if depth >= max_depth:
            selected_subtopics = []

        folder = self._topic_folder(subject, relative_topic)
        seen_names = set()
        known_path_cases = {path.casefold() for path in session["queue"] + session["completed"]}
        for subtopic in selected_subtopics:
            name = self._folder_name(subtopic)
            if name.casefold() in seen_names:
                continue
            seen_names.add(name.casefold())
            child_relative = str(Path(relative_topic) / name) if relative_topic else name
            (folder / name).mkdir(parents=True, exist_ok=True)
            if child_relative.casefold() not in known_path_cases:
                session["queue"].append(child_relative)
                known_path_cases.add(child_relative.casefold())

        finished = session["queue"].pop(0)
        if finished not in session["completed"]:
            session["completed"].append(finished)
        progress[subject] = session
        self._save_notes_progress(progress)
        return self.get_notes_progress(subject)

    def start_course(self, category):
        """Start a fresh, generated learning session for one subject."""
        self.steps.clear()
        self.conversation_history.clear()
        self.on_event("chapter_started", category=category)

    def generate_step(self, category, thought, follow_up=False, expected_type=None):
        """Create and store one theory explanation or practice question from a learner prompt."""
        if not isinstance(thought, str) or not thought.strip():
            raise ValueError("Enter what you would like to learn or practise.")

        expected_type = expected_type or self._expected_step_type(thought)
        format_instructions = {
            "theory": (
                'Return exactly {"type":"theory","title":"short title",'
                '"content":"clear concise explanation"}.'
            ),
            "mcq": (
                'Return exactly {"type":"mcq","question":"question",'
                '"options":["option 1","option 2","option 3","option 4"],'
                '"answer_index":0,"explanation":"why the answer is correct"}.'
            ),
            "subjective": (
                'Return exactly {"type":"subjective","question":"question",'
                '"sample_answer":"a concise model answer"}.'
            ),
        }
        follow_up_instruction = (
            "This is a follow-up item, so make it different from the previous item while staying on the same topic. "
            if follow_up else ""
        )
        prompt = (
            f"Subject: {category}\n"
            f"Learner request: {thought.strip()}\n\n"
            f"Create exactly one {expected_type} learning item. {format_instructions[expected_type]} "
            f"{follow_up_instruction}"
            "Do not return theory, an explanation, or any other type when a question type is requested. "
            "Keep all content accurate, age-appropriate, and relevant."
        )
        system_prompt = "You are a helpful education assistant. Return valid JSON only; do not use Markdown fences."
        # Keep two complete learner/model turns so follow-up questions have context.
        response = self.llm.chat(
            prompt,
            system_prompt=system_prompt,
            history=self.conversation_history[-4:],
        )
        step = self._parse_generated_step(response, expected_type)
        self.steps.append(step)
        self.conversation_history.extend((
            {"role": "user", "content": thought.strip()},
            {"role": "assistant", "content": self._step_memory(step)},
        ))
        self.conversation_history = self.conversation_history[-4:]
        return len(self.steps) - 1

    def generate_initial_step(self, category):
        """Create a random first theory item or question for a subject."""
        return self._generate_random_step(
            category,
            "Start this learning session with an engaging introductory item for the subject.",
        )

    def generate_follow_up_step(self, category, comment):
        """Use an optional learner comment, or create a random related next item."""
        if isinstance(comment, str) and comment.strip():
            return self.generate_step(category, comment, follow_up=True)
        return self._generate_random_step(
            category,
            "Continue with a different, relevant learning item for this subject.",
            follow_up=True,
        )

    def _generate_random_step(self, category, instruction, follow_up=False):
        return self.generate_step(
            category,
            instruction,
            follow_up=follow_up,
            expected_type=random.choice(("theory", "mcq", "subjective")),
        )

    @staticmethod
    def _expected_step_type(thought):
        question_pattern = r"\b(?:questions?|quizzes|practice|tests?|exercises?|problems?|similar)\b"
        if re.search(question_pattern, thought, flags=re.IGNORECASE):
            return random.choice(("mcq", "subjective"))
        return "theory"

    @staticmethod
    def _parse_generated_step(response, expected_type=None):
        try:
            data = json.loads(response)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return a valid lesson. Please try again.") from error
        if not isinstance(data, dict):
            raise ValueError("The model returned an invalid lesson format. Please try again.")

        step_type = data.get("type")
        if step_type == "theory" and expected_type in (None, "theory"):
            title = data.get("title")
            content = data.get("content")
            if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
                return {"type": PageType.THEORY, "title": title.strip(), "content": content.strip()}

        if step_type == "mcq" and expected_type in (None, "mcq"):
            question = data.get("question")
            options = data.get("options")
            answer_index = data.get("answer_index")
            explanation = data.get("explanation")
            valid_options = (
                isinstance(options, list)
                and len(options) == 4
                and all(isinstance(option, str) and option.strip() for option in options)
                and len({option.strip().casefold() for option in options}) == 4
            )
            if (
                isinstance(question, str) and question.strip()
                and valid_options
                and isinstance(answer_index, int) and not isinstance(answer_index, bool)
                and 0 <= answer_index < len(options)
                and isinstance(explanation, str) and explanation.strip()
            ):
                return {
                    "type": PageType.MCQ,
                    "question": question.strip(),
                    "options": [option.strip() for option in options],
                    "answer": answer_index,
                    "explanation": explanation.strip(),
                }

        if step_type == "subjective" and expected_type in (None, "subjective"):
            question = data.get("question")
            sample_answer = data.get("sample_answer")
            if (
                isinstance(question, str) and question.strip()
                and isinstance(sample_answer, str) and sample_answer.strip()
            ):
                return {
                    "type": PageType.SUBJECTIVE,
                    "question": question.strip(),
                    "sample_answer": sample_answer.strip(),
                }

        raise ValueError("The model returned an incomplete lesson. Please try again.")

    @staticmethod
    def _step_memory(step):
        """Create compact context that lets the next request refer to this item."""
        if step["type"] == PageType.THEORY:
            return f"Theory: {step['title']}. {step['content']}"
        if step["type"] == PageType.MCQ:
            correct_answer = step["options"][step["answer"]]
            return (
                f"Question: {step['question']} Correct answer: {correct_answer}. "
                f"Explanation: {step['explanation']}"
            )
        return f"Question: {step['question']} Suggested answer: {step['sample_answer']}"

    def first_step(self):
        return 0

    def get_step(self,index):
        if not isinstance(index, int) or index < 0 or index >= len(self.steps):
            return {"type":PageType.END}
        return self.steps[index]

    def next_step(self,index):
        if not isinstance(index, int):
            return len(self.steps)
        return min(index + 1, len(self.steps))

    def check_answer(self,step,selected):
        if not isinstance(step, dict) or step.get("type") != PageType.MCQ:
            return False
        options = step.get("options")
        answer = step.get("answer")
        if not isinstance(options, list) or not isinstance(selected, int):
            return False
        if not 0 <= selected < len(options):
            return False
        return selected == answer

    def evaluate_subjective_answer(self, category, step, answer):
        """Use Ollama to assess a free-text answer against the generated model answer."""
        if not isinstance(step, dict) or step.get("type") != PageType.SUBJECTIVE:
            raise ValueError("This is not a subjective question.")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Enter an answer before submitting.")

        prompt = (
            f"Subject: {category}\n"
            f"Question: {step['question']}\n"
            f"Model answer: {step['sample_answer']}\n"
            f"Learner answer: {answer.strip()}\n\n"
            "Assess whether the learner answer is substantively correct. Accept equivalent wording and do not "
            "penalize minor grammar or spelling errors. Return exactly this JSON object: "
            '{"correct":true,"feedback":"brief helpful feedback"}. '
            "Set correct to false when the answer is missing a key idea or is incorrect."
        )
        response = self.llm.chat(
            prompt,
            system_prompt="You are a fair educational assessor. Return valid JSON only; do not use Markdown fences.",
            history=self.conversation_history[-4:],
        )
        try:
            result = json.loads(response)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model could not assess this answer. Please try again.") from error

        correct = result.get("correct") if isinstance(result, dict) else None
        feedback = result.get("feedback") if isinstance(result, dict) else None
        if not isinstance(correct, bool) or not isinstance(feedback, str) or not feedback.strip():
            raise ValueError("The model returned an invalid assessment. Please try again.")
        return {"correct": correct, "feedback": feedback.strip()}

    def on_event(self,event,**kwargs):
        self.events.append({"event":event,**kwargs})
        if event=="answer_submitted":
            sid=kwargs.get("step_id",0)
            step=self.get_step(sid)
            if (
                step.get("type") == PageType.MCQ
                and sid not in self.answered_step_ids
                and self.check_answer(step, kwargs.get("answer"))
                and kwargs.get("correct")
            ):
                self.score+=1
            if step.get("type") == PageType.MCQ:
                self.answered_step_ids.add(sid)
        elif event=="time_expired":
            print(f"Timeout on step {kwargs.get('step_id')}")
        elif event=="chapter_started":
            self.score=0
            self.answered_step_ids.clear()
        elif event=="chapter_closed":
            print("Chapter closed")
        return {"score":self.score,"events":len(self.events)}

    def analytics(self):
        return {"score":self.score,"total_events":len(self.events)}
