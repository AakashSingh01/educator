"""Reusable question and theory-card bank generation."""

import hashlib
import json
import pickle
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from prompt_loader import render_prompt
from question_bank_config import (
    PREPARATION_OUTPUT_ATTEMPTS,
    PREPARATION_WORKERS,
    QUESTION_BANK_DIFFICULTIES,
    QUESTION_BANK_FILES,
    QUESTION_BANK_ITEMS_PER_DIFFICULTY,
    QUESTION_BANK_NOTES_CHAR_LIMIT,
    QUESTION_BANK_OBJECTIVE_MAX_OUTPUT_TOKENS,
    QUESTION_BANK_OUTLINE_MAX_OUTPUT_TOKENS,
    QUESTION_BANK_SUBJECTIVE_MAX_OUTPUT_TOKENS,
    QUESTION_BANK_THEORY_MAX_OUTPUT_TOKENS,
    QUESTION_BANK_VERSION,
)
from response_parsing import parse_json_response


class QuestionBankMixin:
    @staticmethod
    def _notes_hash(notes):
        return hashlib.sha256(notes.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalise_item_text(value):
        return re.sub(r"\s+", " ", value.strip()).casefold() if isinstance(value, str) else ""

    @staticmethod
    def _json_response(response, error_message):
        try:
            data = parse_json_response(response)
        except ValueError as error:
            raise ValueError(error_message) from error
        if isinstance(data, list):
            return {"items": data}
        if not isinstance(data, dict):
            raise ValueError(error_message)
        return data

    @staticmethod
    def _response_items(data):
        """Accept common wrappers used by otherwise valid structured responses."""

        if not isinstance(data, dict):
            return None
        for key in ("items", "questions", "cards", "results", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = value.get("items")
                if isinstance(nested, list):
                    return nested
        return None

    @staticmethod
    def _item_field(item, key):
        aliases = {
            "question": ("question", "question_text", "stem", "text"),
            "title": ("title", "heading", "topic", "text"),
            "answer": ("answer", "model_answer", "sample_answer", "response"),
            "content": ("content", "description", "explanation", "answer"),
            "options": ("options", "choices", "answers"),
            "correct_option": (
                "correct_option",
                "correct_answer",
                "answer_key",
                "correct",
                "answer",
            ),
            "explanation": ("explanation", "rationale", "answer_explanation"),
            "reason": ("reason", "distractor_explanation", "incorrect_options_reason"),
        }
        if not isinstance(item, dict):
            return None
        for alias in aliases.get(key, (key,)):
            value = item.get(alias)
            if value is not None:
                return value
        return None

    @classmethod
    def _outline_text(cls, entry, item_type):
        if isinstance(entry, str):
            return entry.strip()
        if not isinstance(entry, dict):
            return ""
        preferred_keys = {
            "subjective": ("question", "text", "title"),
            "mcq": ("question", "stem", "text"),
            "theory": ("title", "heading", "text"),
        }
        for key in preferred_keys[item_type]:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _difficulty_entries(cls, data, difficulty):
        items = None
        for wrapper in ("items", "questions", "cards", "results", "data"):
            candidate = data.get(wrapper)
            if isinstance(candidate, (list, dict)):
                items = candidate
                break
        if isinstance(items, list):
            grouped = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = cls._normalise_item_text(item.get("difficulty"))
                if label == difficulty or label.startswith(f"{difficulty} "):
                    grouped.append(item)
            return grouped or None
        source = items if isinstance(items, dict) else data
        for key, entries in source.items():
            label = cls._normalise_item_text(key)
            if label == difficulty or label.startswith(f"{difficulty} "):
                return entries
        return None

    @staticmethod
    def _clean_objective_options(options):
        if isinstance(options, dict):
            labelled = [
                options.get(letter) or options.get(letter.casefold())
                for letter in ("A", "B", "C", "D")
            ]
            options = labelled if all(labelled) else list(options.values())
        if isinstance(options, list):
            cleaned = []
            for option in options:
                if isinstance(option, dict):
                    option = (
                        option.get("text")
                        or option.get("option")
                        or option.get("value")
                    )
                if not isinstance(option, str) or not option.strip():
                    return None
                cleaned.append(option.strip())
            if len(cleaned) == 4 and len({item.casefold() for item in cleaned}) == 4:
                return cleaned
        return None

    @classmethod
    def _resolve_correct_option(cls, correct, options):
        if isinstance(correct, int) and not isinstance(correct, bool):
            if correct == 0:
                return options[0]
            if 1 <= correct <= len(options):
                return options[correct - 1]
            return None
        if not isinstance(correct, str) or not correct.strip():
            return None

        value = correct.strip()
        option_map = {option.casefold(): option for option in options}
        if value.casefold() in option_map:
            return option_map[value.casefold()]

        label_match = re.match(
            r"^(?:option|answer)?\s*([A-D])(?:\s*[\).:\-]\s*|\s*$)",
            value,
            flags=re.IGNORECASE,
        )
        if label_match:
            return options[ord(label_match.group(1).upper()) - ord("A")]
        if value in {"1", "2", "3", "4"}:
            return options[int(value) - 1]
        numbered_match = re.match(
            r"^(?:option|answer)?\s*([1-4])(?:\s*[\).:\-]\s*|\s*$)",
            value,
            flags=re.IGNORECASE,
        )
        if numbered_match:
            return options[int(numbered_match.group(1)) - 1]

        def without_label(text):
            return re.sub(
                r"^(?:option\s*)?[A-D]\s*[\).:\-]\s*",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip().casefold()

        unlabelled_options = {without_label(option): option for option in options}
        return unlabelled_options.get(without_label(value))

    def _retry_preparation_output(self, create, error_message):
        last_error = None
        for _ in range(PREPARATION_OUTPUT_ATTEMPTS):
            try:
                return create()
            except ValueError as error:
                last_error = error
        detail = str(last_error) if last_error else "No usable response was returned."
        raise ValueError(f"{error_message} Last response issue: {detail}") from last_error

    def _question_bank_path(self, folder, item_type, difficulty):
        return folder / QUESTION_BANK_FILES[item_type][difficulty]

    def _read_question_bank(self, folder, item_type, difficulty, source_hash=None):
        path = self._question_bank_path(folder, item_type, difficulty)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return None
        if data.get("version") != QUESTION_BANK_VERSION:
            return None
        if data.get("type") != item_type or data.get("difficulty") != difficulty:
            return None
        if source_hash is not None and data.get("notes_hash") != source_hash:
            return None
        return data

    def _write_question_bank(
        self, folder, item_type, difficulty, subject, relative_topic, notes_hash, items, items_per_difficulty
    ):
        data = {
            "version": QUESTION_BANK_VERSION,
            "type": item_type,
            "difficulty": difficulty,
            "subject": subject,
            "topic": relative_topic,
            "notes_hash": notes_hash,
            "items_per_difficulty": items_per_difficulty,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        path = self._question_bank_path(folder, item_type, difficulty)
        temporary_path = path.with_suffix(".tmp")
        try:
            temporary_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary_path.replace(path)
        except OSError as error:
            raise ValueError(f"Could not save prepared {item_type} items: {error}") from error

    def list_question_bank_topics(self, subject, scope=""):
        subject = self._folder_name(subject)
        if scope not in self.get_learning_scopes(subject):
            raise ValueError("Choose a valid subject or subtopic scope.")
        root = (self.course_path / subject).resolve()
        scope_folder = self._topic_folder(subject, scope)
        requested_relative = Path(scope) if scope else None
        if not scope_folder.is_dir():
            return []
        topics = []
        for notes_path in scope_folder.rglob("notes.txt"):
            try:
                relative = notes_path.parent.relative_to(root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            if requested_relative and relative != requested_relative and requested_relative not in relative.parents:
                continue
            topics.append("" if relative == Path(".") else str(relative))
        return sorted(set(topics), key=lambda path: (len(Path(path).parts), path.casefold()))

    def _generate_question_bank_outlines(self, subject, relative_topic, notes, item_type, items_per_difficulty):
        topic_label = subject if not relative_topic else f"{subject} / {relative_topic}"
        descriptions = {
            "subjective": "short subjective questions that require a concise written answer",
            "mcq": "multiple-choice question stems, without options or answers",
            "theory": "theory-card headings that invite a concise explanatory card",
        }
        total_items = items_per_difficulty * len(QUESTION_BANK_DIFFICULTIES)
        outline_schema = json.dumps({
            difficulty: [f"item {number}" for number in range(1, items_per_difficulty + 1)]
            for difficulty in QUESTION_BANK_DIFFICULTIES
        })

        def create():
            prompt, system_prompt = render_prompt(
                "question_bank_outlines",
                subject=subject,
                topic_label=topic_label,
                notes=notes[:QUESTION_BANK_NOTES_CHAR_LIMIT],
                total_items=total_items,
                description=descriptions[item_type],
                items_per_difficulty=items_per_difficulty,
                outline_schema=outline_schema,
            )
            data = self._json_response(
                self.llm.chat(
                    prompt,
                    system_prompt=system_prompt,
                    max_output_tokens=QUESTION_BANK_OUTLINE_MAX_OUTPUT_TOKENS,
                    use_grounding=False,
                ),
                "The model did not return valid distinct item outlines.",
            )
            cleaned = {}
            seen = set()
            for difficulty in QUESTION_BANK_DIFFICULTIES:
                entries = self._difficulty_entries(data, difficulty)
                if not isinstance(entries, list):
                    raise ValueError("The model did not return all requested outlines.")
                values = []
                for entry in entries:
                    value = self._outline_text(entry, item_type)
                    normalised = self._normalise_item_text(value)
                    if not normalised or normalised in seen:
                        continue
                    seen.add(normalised)
                    values.append(value)
                    if len(values) == items_per_difficulty:
                        break
                if len(values) != items_per_difficulty:
                    raise ValueError(
                        f"The model returned only {len(values)} usable "
                        f"{difficulty} outline(s); {items_per_difficulty} were requested."
                    )
                cleaned[difficulty] = values
            return cleaned

        return self._retry_preparation_output(create, "The model could not prepare distinct item outlines.")

    def _generate_subjective_answers(self, subject, relative_topic, notes, difficulty, questions):
        def create():
            prompt, system_prompt = render_prompt(
                "question_bank_subjective_answers",
                subject=subject,
                topic_label=subject if not relative_topic else f"{subject} / {relative_topic}",
                notes=notes[:QUESTION_BANK_NOTES_CHAR_LIMIT],
                difficulty=difficulty.title(),
                item_count=len(questions),
                questions=json.dumps(questions, ensure_ascii=False),
            )
            data = self._json_response(
                self.llm.chat(
                    prompt,
                    system_prompt=system_prompt,
                    max_output_tokens=QUESTION_BANK_SUBJECTIVE_MAX_OUTPUT_TOKENS,
                    use_grounding=False,
                ),
                "The model did not return valid subjective answers.",
            )
            return self._match_batch_items(
                self._response_items(data),
                questions,
                "question",
                ("answer",),
            )

        return self._retry_preparation_output(create, "The model could not prepare all subjective answers. Please run it again.")

    def _generate_objective_answers(self, subject, relative_topic, notes, difficulty, questions):
        def create():
            prompt, system_prompt = render_prompt(
                "question_bank_objective_answers",
                subject=subject,
                topic_label=subject if not relative_topic else f"{subject} / {relative_topic}",
                notes=notes[:QUESTION_BANK_NOTES_CHAR_LIMIT],
                difficulty=difficulty.title(),
                item_count=len(questions),
                questions=json.dumps(questions, ensure_ascii=False),
            )
            data = self._json_response(
                self.llm.chat(
                    prompt,
                    system_prompt=system_prompt,
                    max_output_tokens=QUESTION_BANK_OBJECTIVE_MAX_OUTPUT_TOKENS,
                    use_grounding=False,
                ),
                "The model did not return valid objective answers.",
            )
            items = self._match_batch_items(
                self._response_items(data),
                questions,
                "question",
                ("options", "correct_option", "explanation", "reason"),
            )
            for item in items:
                options = self._clean_objective_options(item["options"])
                if options is None:
                    raise ValueError("The model returned invalid objective options.")
                item["options"] = options
                correct = self._resolve_correct_option(item["correct_option"], options)
                if correct is None:
                    raise ValueError("The model returned an objective answer outside its options.")
                item["correct_option"] = correct
            return items

        return self._retry_preparation_output(create, "The model could not prepare all objective answers. Please run it again.")

    def _generate_theory_cards(self, subject, relative_topic, notes, difficulty, titles):
        def create():
            prompt, system_prompt = render_prompt(
                "question_bank_theory_cards",
                subject=subject,
                topic_label=subject if not relative_topic else f"{subject} / {relative_topic}",
                notes=notes[:QUESTION_BANK_NOTES_CHAR_LIMIT],
                difficulty=difficulty.title(),
                item_count=len(titles),
                titles=json.dumps(titles, ensure_ascii=False),
            )
            data = self._json_response(
                self.llm.chat(
                    prompt,
                    system_prompt=system_prompt,
                    max_output_tokens=QUESTION_BANK_THEORY_MAX_OUTPUT_TOKENS,
                    use_grounding=False,
                ),
                "The model did not return valid theory cards.",
            )
            return self._match_batch_items(
                self._response_items(data),
                titles,
                "title",
                ("content",),
            )

        return self._retry_preparation_output(create, "The model could not prepare all theory cards. Please run it again.")

    def _match_batch_items(self, items, requested_texts, text_key, required_keys):
        if not isinstance(items, list) or len(items) < len(requested_texts):
            raise ValueError("The model did not return the requested batch.")
        items = items[:len(requested_texts)]
        expected = {self._normalise_item_text(text): text for text in requested_texts}
        matched = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("The model returned an invalid batch item.")
            item_key = self._normalise_item_text(self._item_field(item, text_key))
            if item_key in expected and item_key not in matched:
                matched[item_key] = item

        if set(matched) == set(expected):
            ordered_items = [
                matched[self._normalise_item_text(text)]
                for text in requested_texts
            ]
        else:
            # Gemini sometimes adds numbering or lightly rewrites the repeated
            # question/title. Preserve the original text and match by the
            # requested order instead of paying for another identical batch.
            ordered_items = items

        cleaned_items = []
        for requested_text, item in zip(requested_texts, ordered_items):
            cleaned = {text_key: requested_text}
            for required_key in required_keys:
                value = self._item_field(item, required_key)
                if required_key == "options":
                    cleaned[required_key] = value
                    continue
                if required_key == "reason" and (
                    not isinstance(value, str) or not value.strip()
                ):
                    value = self._item_field(item, "explanation")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("The model returned an incomplete batch item.")
                cleaned[required_key] = value.strip()
            cleaned_items.append(cleaned)
        return cleaned_items

    def prepare_topic_question_bank(self, subject, relative_topic="", overwrite=False):
        folder = self._topic_folder(subject, relative_topic)
        try:
            notes = (folder / "notes.txt").read_text(encoding="utf-8").strip()
        except OSError as error:
            return {"topic": relative_topic, "status": "skipped", "message": f"Could not read notes: {error}"}
        if not notes:
            return {"topic": relative_topic, "status": "skipped", "message": "No notes.txt content"}
        notes_hash = self._notes_hash(notes)
        files_to_write = {
            item_type: [
                difficulty for difficulty in QUESTION_BANK_DIFFICULTIES
                if overwrite or self._read_question_bank(folder, item_type, difficulty, notes_hash) is None
            ]
            for item_type in QUESTION_BANK_FILES
        }
        if not any(files_to_write.values()):
            return {"topic": relative_topic, "status": "cached", "files": 0}

        generated_files = 0
        for item_type in ("subjective", "mcq", "theory"):
            missing_difficulties = files_to_write[item_type]
            if not missing_difficulties:
                continue
            completed_items = completed_item_count = last_error = None
            for items_per_difficulty in QUESTION_BANK_ITEMS_PER_DIFFICULTY:
                try:
                    outlines = self._generate_question_bank_outlines(subject, relative_topic, notes, item_type, items_per_difficulty)
                    prepared_items = {}
                    for difficulty in missing_difficulties:
                        if item_type == "subjective":
                            prepared_items[difficulty] = self._generate_subjective_answers(subject, relative_topic, notes, difficulty, outlines[difficulty])
                        elif item_type == "mcq":
                            prepared_items[difficulty] = self._generate_objective_answers(subject, relative_topic, notes, difficulty, outlines[difficulty])
                        else:
                            prepared_items[difficulty] = self._generate_theory_cards(subject, relative_topic, notes, difficulty, outlines[difficulty])
                    completed_items, completed_item_count = prepared_items, items_per_difficulty
                    break
                except ValueError as error:
                    last_error = error
            if completed_items is None:
                detail = str(last_error) if last_error else "No usable model response was returned."
                raise ValueError(
                    f"The model could not complete the minimum six {item_type} items "
                    f"for this topic. Last response issue: {detail}"
                ) from last_error
            for difficulty, items in completed_items.items():
                self._write_question_bank(folder, item_type, difficulty, subject, relative_topic, notes_hash, items, completed_item_count)
                generated_files += 1
        return {"topic": relative_topic, "status": "generated", "files": generated_files}

    def prepare_question_banks(self, subject, scope="", max_workers=PREPARATION_WORKERS, overwrite=False, progress_callback=None):
        subject = self._folder_name(subject)
        topics = self.list_question_bank_topics(subject, scope)
        summary = {"subject": subject, "scope": scope, "topics": len(topics), "generated": 0, "cached": 0, "skipped": [], "failed": [], "workers": 1, "parallel_fallback": None}
        if not topics:
            summary["skipped"].append({"topic": scope, "message": "No notes.txt files were found."})
            if callable(progress_callback):
                try:
                    progress_callback(0, 0, summary["skipped"][0])
                except Exception:
                    pass
            return summary

        def report_progress(completed, result):
            if callable(progress_callback):
                try:
                    progress_callback(completed, len(topics), result)
                except Exception:
                    pass

        try:
            workers = max(1, int(max_workers))
        except (TypeError, ValueError):
            workers = 1
        workers = min(workers, len(topics))
        use_processes = workers > 1
        if use_processes:
            try:
                pickle.dumps(self.llm)
            except Exception:
                use_processes = False
                summary["parallel_fallback"] = "The configured AI client cannot be shared with worker processes; used one worker instead."

        def run_sequentially():
            results = []
            for topic in topics:
                started_at = perf_counter()
                try:
                    result = self.prepare_topic_question_bank(subject, topic, overwrite)
                except Exception as error:
                    result = {"topic": topic, "status": "failed", "message": str(error)}
                result["elapsed_seconds"] = perf_counter() - started_at
                results.append(result)
                report_progress(len(results), result)
            return results

        results = []
        if use_processes:
            summary["workers"] = workers
            try:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(_prepare_question_bank_worker, str(self.course_path), subject, topic, self.llm, overwrite): topic for topic in topics}
                    for future in as_completed(futures):
                        topic = futures[future]
                        try:
                            result = future.result()
                        except Exception as error:
                            result = {"topic": topic, "status": "failed", "message": str(error)}
                        results.append(result)
                        report_progress(len(results), result)
            except (OSError, RuntimeError) as error:
                summary["workers"] = 1
                summary["parallel_fallback"] = f"Parallel preparation was unavailable ({error}); used one worker instead."
                results = run_sequentially()
        else:
            results = run_sequentially()

        for result in results:
            if result.get("status") == "generated":
                summary["generated"] += 1
            elif result.get("status") == "cached":
                summary["cached"] += 1
            elif result.get("status") == "skipped":
                summary["skipped"].append(result)
            else:
                summary["failed"].append(result)
        return summary


def _prepare_question_bank_worker(course_path, subject, relative_topic, llm_client, overwrite):
    from .core import LearningBackend

    started_at = perf_counter()
    backend = LearningBackend(course_path=Path(course_path), llm_client=llm_client)
    result = backend.prepare_topic_question_bank(subject, relative_topic, overwrite)
    result["elapsed_seconds"] = perf_counter() - started_at
    return result
