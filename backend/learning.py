"""Prepared-item learning sessions, answers, and result follow-ups."""

import random
import re
from pathlib import Path

from config.learning import LEARNING_MODE_TYPES, TIMER_PRESETS, get_time_limit
from config.llm import (
    LEARNING_ITEM_MAX_OUTPUT_TOKENS,
    RESULT_FOLLOW_UP_MAX_OUTPUT_TOKENS,
    SUBJECTIVE_ASSESSMENT_MAX_OUTPUT_TOKENS,
)
from prompt_loader import render_prompt
from config.question_bank import QUESTION_BANK_DIFFICULTIES
from response_parsing import parse_json_object

from .models import PageType


class LearningSessionMixin:
    @staticmethod
    def _is_within_scope(relative_topic, scope):
        """Return whether a notes folder is the chosen scope or one of its children."""

        if not scope:
            return True
        selected_scope = Path(scope)
        return relative_topic == selected_scope or selected_scope in relative_topic.parents

    def start_course(self, category, scope="", allowed_types=None, timer_preset="Normal"):
        allowed_types = tuple(allowed_types or LEARNING_MODE_TYPES)
        valid_types = {"mcq", "subjective", "theory"}
        if not allowed_types or not set(allowed_types).issubset(valid_types):
            raise ValueError("Choose at least one valid learning item type.")
        if timer_preset not in TIMER_PRESETS:
            raise ValueError("Choose a valid timer preset.")
        if scope not in self.get_learning_scopes(category):
            raise ValueError("Choose a valid subject or subtopic scope.")
        available_types = self.get_prepared_item_types(category, scope)
        missing_types = [item_type for item_type in allowed_types if item_type not in available_types]
        if missing_types:
            labels = {"mcq": "objective questions", "subjective": "subjective questions", "theory": "theory cards"}
            raise ValueError(
                f"No prepared {', '.join(labels[item_type] for item_type in missing_types)} are available for this area. "
                "Run Question Preparation from Notes first."
            )
        self.steps.clear()
        self.ask_history.clear()
        self.learning_context = self.select_learning_context(category, scope)
        self.learning_scope = scope
        self.learning_boundary_label = category if not scope else f"{category} / {scope}"
        self.learning_types = allowed_types
        self.learning_type_cycle = []
        self.prepared_item_ids.clear()
        self.timer_preset = timer_preset
        self.on_event("chapter_started", category=category)

    def get_learning_scopes(self, subject):
        root = (self.course_path / self._folder_name(subject)).resolve()
        if not root.is_dir():
            return [""]
        scopes = [""]
        for folder in root.rglob("*"):
            if folder.is_dir():
                relative = folder.relative_to(root)
                if not any(part.startswith(".") for part in relative.parts):
                    scopes.append(str(relative))
        return sorted(set(scopes), key=lambda path: (len(Path(path).parts), path.casefold()))

    def get_direct_learning_subtopics(self, subject, scope=""):
        root = (self.course_path / self._folder_name(subject)).resolve()
        folder = root / Path(scope)
        if not folder.is_dir():
            return []
        return sorted(child.name for child in folder.iterdir() if child.is_dir() and not child.name.startswith("."))

    def _prepared_step_from_item(self, item_type, item, time_limit):
        if not isinstance(item, dict):
            return None
        if item_type == "subjective":
            question, answer = item.get("question"), item.get("answer")
            if isinstance(question, str) and question.strip() and isinstance(answer, str) and answer.strip():
                return {"type": PageType.SUBJECTIVE, "question": question.strip(), "sample_answer": answer.strip(), "time_limit": time_limit, "difficulty": item.get("difficulty")}
            return None
        if item_type == "theory":
            title, content = item.get("title"), item.get("content")
            if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
                return {"type": PageType.THEORY, "title": title.strip(), "content": content.strip(), "time_limit": time_limit, "difficulty": item.get("difficulty")}
            return None
        question, options = item.get("question"), item.get("options")
        correct_option, explanation = item.get("correct_option"), item.get("explanation")
        if not (
            isinstance(question, str) and question.strip() and isinstance(options, list) and len(options) == 4
            and all(isinstance(option, str) and option.strip() for option in options)
            and len({option.strip().casefold() for option in options}) == 4
            and isinstance(correct_option, str) and correct_option.strip()
            and isinstance(explanation, str) and explanation.strip()
        ):
            return None
        options = [option.strip() for option in options]
        option_map = {option.casefold(): option for option in options}
        correct_option = option_map.get(correct_option.strip().casefold(), correct_option.strip())
        if correct_option not in options:
            return None
        return {
            "type": PageType.MCQ, "question": question.strip(), "options": options,
            "answer": options.index(correct_option), "correct_option": correct_option,
            "explanation": explanation.strip(), "reason": item.get("reason", ""),
            "time_limit": time_limit, "difficulty": item.get("difficulty"),
        }

    def _prepared_item_candidates(self, subject, scope, item_type):
        subject = self._folder_name(subject)
        root = (self.course_path / subject).resolve()
        if scope not in self.get_learning_scopes(subject):
            return
        scope_folder = self._topic_folder(subject, scope)
        if not scope_folder.is_dir():
            return
        for notes_path in scope_folder.rglob("notes.txt"):
            relative_topic = notes_path.parent.relative_to(root)
            if any(part.startswith(".") for part in relative_topic.parts):
                continue
            if not self._is_within_scope(relative_topic, scope):
                continue
            try:
                notes = notes_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not notes:
                continue
            source_hash = self._notes_hash(notes)
            label = subject if not relative_topic.parts else f"{subject} / {relative_topic}"
            for difficulty in QUESTION_BANK_DIFFICULTIES:
                bank = self._read_question_bank(notes_path.parent, item_type, difficulty, source_hash)
                if not bank:
                    continue
                for index, item in enumerate(bank["items"]):
                    step = self._prepared_step_from_item(item_type, item, get_time_limit(self.timer_preset, item_type))
                    if step is None:
                        continue
                    step["difficulty"] = difficulty
                    yield (
                        f"{item_type}:{self._question_bank_path(notes_path.parent, item_type, difficulty)}:{index}",
                        step,
                        {"label": label, "notes": notes},
                    )

    def get_prepared_item_types(self, subject, scope=""):
        return {
            item_type for item_type in ("mcq", "subjective", "theory")
            if next(self._prepared_item_candidates(subject, scope, item_type), None) is not None
        }

    def _select_prepared_step(self, subject, item_type):
        selected = fallback = None
        unseen_count = fallback_count = 0
        for identifier, step, context in self._prepared_item_candidates(subject, self.learning_scope, item_type):
            fallback_count += 1
            if random.randrange(fallback_count) == 0:
                fallback = (identifier, step, context)
            if identifier in self.prepared_item_ids:
                continue
            unseen_count += 1
            if random.randrange(unseen_count) == 0:
                selected = (identifier, step, context)
        if selected is None and fallback is not None:
            self.prepared_item_ids = {identifier for identifier in self.prepared_item_ids if not identifier.startswith(f"{item_type}:")}
            selected = fallback
        if selected is None:
            return None
        identifier, step, context = selected
        self.prepared_item_ids.add(identifier)
        self.learning_context = context
        return step

    def select_learning_context(self, subject, scope="", exclude_label=None):
        root = (self.course_path / self._folder_name(subject)).resolve()
        if scope not in self.get_learning_scopes(subject):
            raise ValueError("Choose a valid subject or subtopic scope.")
        scope_folder = root / Path(scope)
        selected_notes_path = fallback_notes_path = None
        notes_count = fallback_count = 0
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
                if not self._is_within_scope(relative_topic, scope):
                    continue
                label = subject if not relative_topic.parts else f"{subject} / {relative_topic}"
                fallback_count += 1
                if random.randrange(fallback_count) == 0:
                    fallback_notes_path = notes_path
                if label == exclude_label:
                    continue
                notes_count += 1
                if random.randrange(notes_count) == 0:
                    selected_notes_path = notes_path
        selected_notes_path = selected_notes_path or fallback_notes_path
        if selected_notes_path is None:
            return {"label": subject if not scope else f"{subject} / {scope}", "notes": ""}
        try:
            notes = selected_notes_path.read_text(encoding="utf-8").strip()
        except OSError:
            notes = ""
        relative_topic = selected_notes_path.parent.relative_to(root)
        return {"label": subject if not relative_topic.parts else f"{subject} / {relative_topic}", "notes": notes}

    def get_learning_context_label(self):
        return self.learning_context["label"] if self.learning_context else None

    def get_learning_boundary_label(self):
        return self.learning_boundary_label

    def generate_step(self, category, thought, follow_up=False, expected_type=None):
        if not isinstance(thought, str) or not thought.strip():
            raise ValueError("Enter what you would like to learn or practise.")
        expected_type = expected_type or self._expected_step_type(thought)
        prompt, system_prompt = render_prompt(
            f"generated_{expected_type}",
            category=category,
            boundary=self.get_learning_boundary_label() or category,
            context_label=self.get_learning_context_label() or category,
            notes=self._learning_context_notes(),
            thought=thought.strip(),
            follow_up="This is a follow-up item, so make it different from the previous item while staying on the same topic. " if follow_up else "",
        )
        step = self._parse_generated_step(
            self.llm.chat(
                prompt,
                system_prompt=system_prompt,
                max_output_tokens=LEARNING_ITEM_MAX_OUTPUT_TOKENS,
            ),
            expected_type,
        )
        step["time_limit"] = get_time_limit(self.timer_preset, expected_type)
        self.steps.append(step)
        return len(self.steps) - 1

    def _learning_context_notes(self):
        if not self.learning_context or not self.learning_context.get("notes"):
            return "No saved notes are available; use the selected subject scope."
        return self.learning_context["notes"][:8000]

    def generate_initial_step(self, category):
        return self._generate_random_step(category, "Start this learning session with an engaging introductory item for the subject.")

    def generate_follow_up_step(self, category, comment):
        self.ask_history.clear()
        return self._generate_random_step(category, "Show another prepared learning item for this subject.")

    def ask_about_result(self, category, step, question):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Enter a question before asking.")
        if not isinstance(step, dict) or step.get("type") not in {PageType.MCQ, PageType.SUBJECTIVE}:
            raise ValueError("Ask is available after a question has been submitted.")
        if step["type"] == PageType.MCQ:
            result_context = f"Question: {step['question']}\nCorrect answer: {step['options'][step['answer']]}\nExplanation: {step.get('explanation', '')}"
        else:
            result_context = f"Question: {step['question']}\nSuggested answer: {step.get('sample_answer', '')}"
        prompt, system_prompt = render_prompt(
            "result_follow_up", category=category, scope=self.get_learning_context_label() or category,
            result_context=result_context, question=question.strip(),
        )
        try:
            response = self.llm.chat(
                prompt,
                system_prompt=system_prompt,
                history=self.ask_history[-4:],
                max_output_tokens=RESULT_FOLLOW_UP_MAX_OUTPUT_TOKENS,
                use_grounding=False,
            )
            answer = parse_json_object(response).get("answer")
        except ValueError as error:
            raise ValueError("The model did not return a valid answer. Please try again.") from error
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("The model returned an empty answer. Please try again.")
        self.ask_history.extend(({"role": "user", "content": question.strip()}, {"role": "assistant", "content": answer.strip()}))
        self.ask_history = self.ask_history[-4:]
        return answer.strip()

    def _generate_random_step(self, category, instruction, follow_up=False):
        expected_type = self._next_learning_type()
        try:
            step = self._select_prepared_step(category, expected_type)
            if step is None:
                raise ValueError("This prepared item is unavailable or its notes have changed. Run Question Preparation again for this learning area.")
            self.steps.append(step)
            return len(self.steps) - 1
        except Exception:
            self.learning_type_cycle.insert(0, expected_type)
            raise

    def _next_learning_type(self):
        if not self.learning_type_cycle:
            self.learning_type_cycle = list(self.learning_types)
            random.shuffle(self.learning_type_cycle)
        return self.learning_type_cycle.pop()

    @staticmethod
    def _expected_step_type(thought):
        if re.search(r"\b(?:questions?|quizzes|practice|tests?|exercises?|problems?|similar)\b", thought, flags=re.IGNORECASE):
            return random.choice(("mcq", "subjective"))
        return "theory"

    @staticmethod
    def _parse_generated_step(response, expected_type=None):
        try:
            data = parse_json_object(response)
        except ValueError as error:
            raise ValueError("The model did not return a valid lesson. Please try again.") from error
        step_type = {"objective": "mcq", "multiple_choice": "mcq", "short_answer": "subjective"}.get(data.get("type"), data.get("type"))
        if step_type == "theory" and expected_type in (None, "theory"):
            title, content = data.get("title"), data.get("content") or data.get("notes") or data.get("explanation")
            if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
                return {"type": PageType.THEORY, "title": title.strip(), "content": content.strip()}
        if step_type == "mcq" and expected_type in (None, "mcq"):
            question, options = data.get("question"), data.get("options")
            correct_option = data.get("correct_option") or data.get("correct_answer") or data.get("correctAnswer") or data.get("answer_key") or data.get("correct") or data.get("answer")
            explanation = data.get("explanation")
            valid_options = isinstance(options, list) and len(options) == 4 and all(isinstance(option, str) and option.strip() for option in options) and len({option.strip().casefold() for option in options}) == 4
            cleaned_options = [option.strip() for option in options] if valid_options else []
            option_by_text = {option.casefold(): option for option in cleaned_options}
            legacy_index = data.get("answer_index", data.get("answerIndex"))
            if correct_option is None and isinstance(legacy_index, int) and not isinstance(legacy_index, bool) and 0 <= legacy_index < len(cleaned_options):
                correct_option = cleaned_options[legacy_index]
            if isinstance(correct_option, str):
                correct_option = option_by_text.get(correct_option.strip().casefold(), correct_option.strip())
                if correct_option.upper() in {"A", "B", "C", "D"}:
                    correct_option = cleaned_options[ord(correct_option.upper()) - ord("A")]
            if isinstance(question, str) and question.strip() and valid_options and isinstance(correct_option, str) and correct_option in cleaned_options and isinstance(explanation, str) and explanation.strip():
                return {"type": PageType.MCQ, "question": question.strip(), "options": cleaned_options, "answer": cleaned_options.index(correct_option), "correct_option": correct_option, "explanation": explanation.strip()}
        if step_type == "subjective" and expected_type in (None, "subjective"):
            question = data.get("question")
            sample_answer = data.get("sample_answer") or data.get("model_answer") or data.get("answer")
            if isinstance(question, str) and question.strip() and isinstance(sample_answer, str) and sample_answer.strip():
                return {"type": PageType.SUBJECTIVE, "question": question.strip(), "sample_answer": sample_answer.strip()}
        raise ValueError("The model returned an incomplete lesson. Please try again.")

    @staticmethod
    def _step_memory(step):
        if step["type"] == PageType.THEORY:
            return f"Theory: {step['title']}. {step['content']}"
        if step["type"] == PageType.MCQ:
            return f"Question: {step['question']} Correct answer: {step['options'][step['answer']]}. Explanation: {step['explanation']}"
        return f"Question: {step['question']} Suggested answer: {step['sample_answer']}"

    def first_step(self):
        return 0

    def get_step(self, index):
        if not isinstance(index, int) or index < 0 or index >= len(self.steps):
            return {"type": PageType.END}
        return self.steps[index]

    def next_step(self, index):
        return len(self.steps) if not isinstance(index, int) else min(index + 1, len(self.steps))

    def check_answer(self, step, selected):
        if not isinstance(step, dict) or step.get("type") != PageType.MCQ:
            return False
        options, answer = step.get("options"), step.get("answer")
        return isinstance(options, list) and isinstance(selected, int) and 0 <= selected < len(options) and selected == answer

    def evaluate_subjective_answer(self, category, step, answer):
        if not isinstance(step, dict) or step.get("type") != PageType.SUBJECTIVE:
            raise ValueError("This is not a subjective question.")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Enter an answer before submitting.")
        prompt, system_prompt = render_prompt(
            "subjective_assessment", category=category, question=step["question"],
            model_answer=step["sample_answer"], learner_answer=answer.strip(),
        )
        try:
            result = parse_json_object(
                self.llm.chat(
                    prompt,
                    system_prompt=system_prompt,
                    max_output_tokens=SUBJECTIVE_ASSESSMENT_MAX_OUTPUT_TOKENS,
                    use_grounding=False,
                )
            )
        except ValueError as error:
            raise ValueError("The model could not assess this answer. Please try again.") from error
        score = result.get("score") if isinstance(result, dict) else None
        feedback = result.get("feedback") if isinstance(result, dict) else None
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= score <= 10
            or not isinstance(feedback, str)
            or not feedback.strip()
        ):
            raise ValueError("The model returned an invalid assessment. Please try again.")
        score = round(float(score), 1)
        return {"score": score, "correct": score >= 5, "feedback": feedback.strip()}

    def on_event(self, event, **kwargs):
        self.events.append({"event": event, **kwargs})
        if event == "answer_submitted":
            step_id = kwargs.get("step_id", 0)
            step = self.get_step(step_id)
            if step.get("type") == PageType.MCQ and step_id not in self.answered_step_ids and self.check_answer(step, kwargs.get("answer")) and kwargs.get("correct"):
                self.score += 1
            if step.get("type") == PageType.MCQ:
                self.answered_step_ids.add(step_id)
        elif event == "time_expired":
            print(f"Timeout on step {kwargs.get('step_id')}")
        elif event == "chapter_started":
            self.score = 0
            self.answered_step_ids.clear()
        elif event == "chapter_closed":
            print("Chapter closed")
        return {"score": self.score, "events": len(self.events)}

    def analytics(self):
        return {"score": self.score, "total_events": len(self.events)}
