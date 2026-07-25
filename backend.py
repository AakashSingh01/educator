import json
import random
import re
import shutil
from enum import Enum
from pathlib import Path

from learning_config import LEARNING_MODE_TYPES, TIMER_PRESETS, get_time_limit
from llm import LLMClient, OllamaListener

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
        self.llm: LLMClient = llm_client or OllamaListener()
        self.score=0
        self.events=[]
        self.answered_step_ids=set()
        self.ask_history=[]
        self.steps=[]
        self.learning_context=None
        self.learning_scope=""
        self.learning_types=("mcq", "subjective", "theory")
        self.timer_preset="Infinite"

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
    # A persisted stack makes the topic traversal depth-first and resumable.
    def _notes_progress_path(self, subject):
        return self.course_path / self._folder_name(subject) / ".notes_progress.json"

    def _read_progress_file(self, progress_path):
        if not progress_path.is_file():
            return None
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _load_notes_progress(self, subject):
        """Load only one subject's queue, migrating the previous shared format if needed."""
        progress = self._read_progress_file(self._notes_progress_path(subject))
        if progress is not None:
            return progress
        legacy = self._read_progress_file(self.course_path / ".notes_progress.json")
        session = legacy.get(subject) if isinstance(legacy, dict) else None
        return session if isinstance(session, dict) else None

    def _save_notes_progress(self, subject, session):
        progress_path = self._notes_progress_path(subject)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps(session, indent=2, sort_keys=True), encoding="utf-8"
        )
        # Move this subject out of the old course-wide progress file when present.
        legacy_path = self.course_path / ".notes_progress.json"
        legacy = self._read_progress_file(legacy_path)
        if isinstance(legacy, dict) and subject in legacy:
            legacy.pop(subject)
            if legacy:
                legacy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True), encoding="utf-8")
            else:
                legacy_path.unlink(missing_ok=True)

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

    def begin_notes_session(self, subject, restart=False):
        """Create or resume a subject's persisted depth-first notes plan."""
        subject = self._folder_name(subject)

        self.course_path.mkdir(parents=True, exist_ok=True)
        (self.course_path / subject).mkdir(exist_ok=True)
        progress = self._load_notes_progress(subject)
        if restart or progress is None:
            progress = {"queue": [""], "completed": []}
        self._save_notes_progress(subject, progress)
        return self.get_notes_progress(subject)

    def get_notes_progress(self, subject):
        session = self._load_notes_progress(subject)
        if not isinstance(session, dict):
            return None
        queue = session.get("queue")
        completed = session.get("completed")
        if not isinstance(queue, list) or not isinstance(completed, list):
            return None
        return {
            "queue": queue,
            "completed": completed,
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
            "notes": notes,
            "existing_subtopics": children,
        }

    def list_notes_topics(self, subject):
        """Return all visible topic folders for manual selection and editing."""
        root = self._topic_folder(subject, "")
        root.mkdir(parents=True, exist_ok=True)
        topics = [""]
        for folder in root.rglob("*"):
            if folder.is_dir():
                relative = folder.relative_to(root)
                if not any(part.startswith(".") for part in relative.parts):
                    topics.append(str(relative))
        return sorted(set(topics), key=lambda path: (len(Path(path).parts), path.casefold()))

    def select_notes_topic(self, subject, relative_topic):
        """Move a chosen existing topic to the top of the DFS stack."""
        if relative_topic not in self.list_notes_topics(subject):
            raise ValueError("Choose an existing topic folder.")
        session = self._load_notes_progress(subject)
        if session is None:
            raise ValueError("Start a notes plan before selecting a topic.")
        session["queue"] = [path for path in session["queue"] if path != relative_topic]
        session["queue"].insert(0, relative_topic)
        self._save_notes_progress(subject, session)

    def rename_subtopic(self, subject, parent_relative, old_name, new_name):
        """Rename one direct child folder and keep its saved progress paths valid."""
        old_name = self._folder_name(old_name)
        new_name = self._folder_name(new_name)
        parent = self._topic_folder(subject, parent_relative)
        source = parent / old_name
        target = parent / new_name
        if not source.is_dir():
            raise ValueError("The selected subtopic folder does not exist.")
        if target.exists():
            raise ValueError("A subtopic with the new name already exists.")
        source.rename(target)
        old_relative = str(Path(parent_relative) / old_name) if parent_relative else old_name
        new_relative = str(Path(parent_relative) / new_name) if parent_relative else new_name
        session = self._load_notes_progress(subject)
        if session:
            for field in ("queue", "completed"):
                session[field] = [
                    new_relative + path[len(old_relative):]
                    if path == old_relative or path.startswith(old_relative + "/") else path
                    for path in session[field]
                ]
            self._save_notes_progress(subject, session)

    def remove_subtopic(self, subject, parent_relative, subtopic_name):
        """Remove a confirmed direct subtopic folder and all of its nested notes."""
        name = self._folder_name(subtopic_name)
        folder = self._topic_folder(subject, parent_relative) / name
        if not folder.is_dir():
            raise ValueError("The selected subtopic folder does not exist.")
        relative = str(Path(parent_relative) / name) if parent_relative else name
        shutil.rmtree(folder)
        session = self._load_notes_progress(subject)
        if session:
            for field in ("queue", "completed"):
                session[field] = [
                    path for path in session[field]
                    if path != relative and not path.startswith(relative + "/")
                ]
            self._save_notes_progress(subject, session)

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

    def suggest_subtopics(self, subject, relative_topic, instruction=""):
        topic = self.get_current_notes_topic(subject)
        if not topic or topic["relative_path"] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        user_instruction = instruction.strip() if isinstance(instruction, str) else ""
        prompt = (
            f"Subject: {subject}\nTopic: {topic['label']}\nNotes:\n{topic['notes']}\n\n"
            f"Additional instruction: {user_instruction or 'None'}\n\n"
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
        """Confirm children, push them onto the stack, and move to the next DFS topic."""
        session = self._load_notes_progress(subject)
        if not isinstance(session, dict) or not session.get("queue") or session["queue"][0] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        selected_subtopics = selected_subtopics or []

        folder = self._topic_folder(subject, relative_topic)
        seen_names = set()
        known_path_cases = {path.casefold() for path in session["queue"] + session["completed"]}
        new_children = []
        for subtopic in selected_subtopics:
            name = self._folder_name(subtopic)
            if name.casefold() in seen_names:
                continue
            seen_names.add(name.casefold())
            child_relative = str(Path(relative_topic) / name) if relative_topic else name
            (folder / name).mkdir(parents=True, exist_ok=True)
            if child_relative.casefold() not in known_path_cases:
                new_children.append(child_relative)
                known_path_cases.add(child_relative.casefold())

        finished = session["queue"].pop(0)
        if finished not in session["completed"]:
            session["completed"].append(finished)
        # Push in reverse so the first selected child is processed next (DFS).
        for child_relative in reversed(new_children):
            session["queue"].insert(0, child_relative)
        self._save_notes_progress(subject, session)
        return self.get_notes_progress(subject)

    def start_course(self, category, scope="", allowed_types=None, timer_preset="Normal"):
        """Start a fresh, generated learning session for one subject."""
        allowed_types = tuple(allowed_types or LEARNING_MODE_TYPES)
        valid_types = {"mcq", "subjective", "theory"}
        if not allowed_types or not set(allowed_types).issubset(valid_types):
            raise ValueError("Choose at least one valid learning item type.")
        if timer_preset not in TIMER_PRESETS:
            raise ValueError("Choose a valid timer preset.")
        self.steps.clear()
        self.ask_history.clear()
        self.learning_context = self.select_learning_context(category, scope)
        self.learning_scope = scope
        self.learning_types = allowed_types
        self.timer_preset = timer_preset
        self.on_event("chapter_started", category=category)

    def get_learning_scopes(self, subject):
        """Return the full subject and every saved subtopic folder as selectable scopes."""
        root = self.course_path / self._folder_name(subject)
        if not root.is_dir():
            return [""]
        scopes = [""]
        for folder in root.rglob("*"):
            if folder.is_dir():
                relative = folder.relative_to(root)
                if not any(part.startswith(".") for part in relative.parts):
                    scopes.append(str(relative))
        return sorted(set(scopes), key=lambda path: (len(Path(path).parts), path.casefold()))

    def select_learning_context(self, subject, scope="", exclude_label=None):
        """Randomly choose one notes file from the chosen subject or subtopic scope."""
        root = self.course_path / self._folder_name(subject)
        if scope not in self.get_learning_scopes(subject):
            raise ValueError("Choose a valid subject or subtopic scope.")
        scope_folder = root / Path(scope)
        selected_notes_path = None
        fallback_notes_path = None
        notes_count = 0
        fallback_count = 0
        if scope_folder.is_dir():
            for notes_path in scope_folder.rglob("notes.txt"):
                relative = notes_path.relative_to(root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                try:
                    if notes_path.stat().st_size == 0:
                        continue
                except OSError:
                    continue
                relative_topic = notes_path.parent.relative_to(root)
                label = subject if not relative_topic.parts else f"{subject} / {relative_topic}"
                fallback_count += 1
                if random.randrange(fallback_count) == 0:
                    fallback_notes_path = notes_path
                if label == exclude_label:
                    continue
                notes_count += 1
                # Reservoir sampling keeps memory constant for large subject trees.
                if random.randrange(notes_count) == 0:
                    selected_notes_path = notes_path
        selected_notes_path = selected_notes_path or fallback_notes_path
        if selected_notes_path is None:
            label = subject if not scope else f"{subject} / {scope}"
            return {"label": label, "notes": ""}
        try:
            notes = selected_notes_path.read_text(encoding="utf-8").strip()
        except OSError:
            notes = ""
        relative_topic = selected_notes_path.parent.relative_to(root)
        label = subject if not relative_topic.parts else f"{subject} / {relative_topic}"
        return {"label": label, "notes": notes}

    def get_learning_context_label(self):
        return self.learning_context["label"] if self.learning_context else None

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
                '"correct_option":"option 2","explanation":"why the answer is correct"}. '
                "The correct_option must exactly copy one item from options; never use a number or an index."
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
            f"Selected study scope: {self.get_learning_context_label() or category}\n"
            f"Prepared notes for this scope:\n{self._learning_context_notes()}\n\n"
            f"Learner request: {thought.strip()}\n\n"
            f"Create exactly one {expected_type} learning item. {format_instructions[expected_type]} "
            f"{follow_up_instruction}"
            "Base the item on the prepared notes when they are available, and keep it within the selected study scope. "
            "Do not return theory, an explanation, or any other type when a question type is requested. "
            "Keep all content accurate, age-appropriate, and relevant."
        )
        system_prompt = "You are a helpful education assistant. Return valid JSON only; do not use Markdown fences."
        response = self.llm.chat(
            prompt,
            system_prompt=system_prompt,
        )
        step = self._parse_generated_step(response, expected_type)
        step["time_limit"] = get_time_limit(self.timer_preset, expected_type)
        self.steps.append(step)
        return len(self.steps) - 1

    def _learning_context_notes(self):
        if not self.learning_context or not self.learning_context.get("notes"):
            return "No saved notes are available; use the selected subject scope."
        # Keep prompts bounded while retaining enough detail for focused questions.
        return self.learning_context["notes"][:8000]

    def generate_initial_step(self, category):
        """Create a random first theory item or question for a subject."""
        return self._generate_random_step(
            category,
            "Start this learning session with an engaging introductory item for the subject.",
        )

    def generate_follow_up_step(self, category, comment):
        """Create a fresh item from a newly selected note in the current learning scope."""
        self.ask_history.clear()
        self.learning_context = self.select_learning_context(
            category,
            self.learning_scope,
            exclude_label=self.get_learning_context_label(),
        )
        return self._generate_random_step(
            category,
            "Create a new relevant learning item for this subject.",
        )

    def ask_about_result(self, category, step, question):
        """Answer a learner's counter-question using only the result-focused chat memory."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Enter a question before asking.")
        if not isinstance(step, dict) or step.get("type") not in {PageType.MCQ, PageType.SUBJECTIVE}:
            raise ValueError("Ask is available after a question has been submitted.")

        if step["type"] == PageType.MCQ:
            result_context = (
                f"Question: {step['question']}\n"
                f"Correct answer: {step['options'][step['answer']]}\n"
                f"Explanation: {step.get('explanation', '')}"
            )
        else:
            result_context = (
                f"Question: {step['question']}\n"
                f"Suggested answer: {step.get('sample_answer', '')}"
            )

        prompt = (
            f"Subject: {category}\nStudy scope: {self.get_learning_context_label() or category}\n"
            f"Result being discussed:\n{result_context}\n\n"
            f"Learner asks: {question.strip()}\n\n"
            'Return exactly JSON as {"answer":"a clear, concise helpful response"}. '
            "Answer the learner's counter-question directly and use the result context."
        )
        response = self.llm.chat(
            prompt,
            system_prompt="You are a helpful education assistant. Return valid JSON only.",
            history=self.ask_history[-4:],
        )
        try:
            response_text = response.strip() if isinstance(response, str) else response
            if isinstance(response_text, str) and response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            answer = json.loads(response_text).get("answer")
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return a valid answer. Please try again.") from error
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("The model returned an empty answer. Please try again.")

        self.ask_history.extend((
            {"role": "user", "content": question.strip()},
            {"role": "assistant", "content": answer.strip()},
        ))
        self.ask_history = self.ask_history[-4:]
        return answer.strip()

    def _generate_random_step(self, category, instruction, follow_up=False):
        return self.generate_step(
            category,
            instruction,
            follow_up=follow_up,
            expected_type=random.choice(self.learning_types),
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
            response_text = response.strip() if isinstance(response, str) else response
            if isinstance(response_text, str) and response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(response_text)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("The model did not return a valid lesson. Please try again.") from error
        if not isinstance(data, dict):
            raise ValueError("The model returned an invalid lesson format. Please try again.")

        step_type = {"objective": "mcq", "multiple_choice": "mcq", "short_answer": "subjective"}.get(
            data.get("type"), data.get("type")
        )
        if step_type == "theory" and expected_type in (None, "theory"):
            title = data.get("title")
            content = data.get("content") or data.get("notes") or data.get("explanation")
            if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
                return {"type": PageType.THEORY, "title": title.strip(), "content": content.strip()}

        if step_type == "mcq" and expected_type in (None, "mcq"):
            question = data.get("question")
            options = data.get("options")
            correct_option = (
                data.get("correct_option")
                or data.get("correct_answer")
                or data.get("correctAnswer")
                or data.get("answer_key")
                or data.get("correct")
                or data.get("answer")
            )
            explanation = data.get("explanation")
            valid_options = (
                isinstance(options, list)
                and len(options) == 4
                and all(isinstance(option, str) and option.strip() for option in options)
                and len({option.strip().casefold() for option in options}) == 4
            )
            cleaned_options = [option.strip() for option in options] if valid_options else []
            option_by_folded_text = {option.casefold(): option for option in cleaned_options}
            legacy_index = data.get("answer_index", data.get("answerIndex"))
            if correct_option is None and isinstance(legacy_index, int) and not isinstance(legacy_index, bool):
                if 0 <= legacy_index < len(cleaned_options):
                    correct_option = cleaned_options[legacy_index]
            if isinstance(correct_option, str):
                correct_option = option_by_folded_text.get(correct_option.strip().casefold(), correct_option.strip())
                if correct_option.upper() in {"A", "B", "C", "D"}:
                    correct_option = cleaned_options[ord(correct_option.upper()) - ord("A")]
            if (
                isinstance(question, str) and question.strip()
                and valid_options
                and isinstance(correct_option, str)
                and correct_option in cleaned_options
                and isinstance(explanation, str) and explanation.strip()
            ):
                return {
                    "type": PageType.MCQ,
                    "question": question.strip(),
                    "options": cleaned_options,
                    "answer": cleaned_options.index(correct_option),
                    "correct_option": correct_option,
                    "explanation": explanation.strip(),
                }

        if step_type == "subjective" and expected_type in (None, "subjective"):
            question = data.get("question")
            sample_answer = data.get("sample_answer") or data.get("model_answer") or data.get("answer")
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
        """Use the configured language model to assess a free-text answer."""
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
