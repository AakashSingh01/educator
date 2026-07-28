"""Persisted notes planning, editing, and subtopic management."""

import json
import shutil
from pathlib import Path

from llm_config import (
    NOTES_CONTEXT_CHAR_LIMIT,
    NOTES_MAX_OUTPUT_TOKENS,
    SUBTOPIC_SUGGESTIONS_MAX_OUTPUT_TOKENS,
)
from prompt_loader import render_prompt
from response_parsing import parse_json_object


class NotesPreparationMixin:
    """Methods used to build and maintain a subject's notes tree."""

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
        progress = self._read_progress_file(self._notes_progress_path(subject))
        if progress is not None:
            return progress
        legacy = self._read_progress_file(self.course_path / ".notes_progress.json")
        session = legacy.get(subject) if isinstance(legacy, dict) else None
        return session if isinstance(session, dict) else None

    def _save_notes_progress(self, subject, session):
        progress_path = self._notes_progress_path(subject)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(session, indent=2, sort_keys=True), encoding="utf-8")
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
        return {"queue": queue, "completed": completed}

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
        children = sorted(child.name for child in folder.iterdir() if child.is_dir() and not child.name.startswith("."))
        return {
            "relative_path": relative_topic,
            "label": subject if not relative_topic else f"{subject} / {relative_topic}",
            "notes": notes,
            "existing_subtopics": children,
        }

    def list_notes_topics(self, subject):
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
        if relative_topic not in self.list_notes_topics(subject):
            raise ValueError("Choose an existing topic folder.")
        session = self._load_notes_progress(subject)
        if session is None:
            raise ValueError("Start a notes plan before selecting a topic.")
        session["queue"] = [path for path in session["queue"] if path != relative_topic]
        session["queue"].insert(0, relative_topic)
        self._save_notes_progress(subject, session)

    def rename_subtopic(self, subject, parent_relative, old_name, new_name):
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
        name = self._folder_name(subtopic_name)
        folder = self._topic_folder(subject, parent_relative) / name
        if not folder.is_dir():
            raise ValueError("The selected subtopic folder does not exist.")
        relative = str(Path(parent_relative) / name) if parent_relative else name
        shutil.rmtree(folder)
        session = self._load_notes_progress(subject)
        if session:
            for field in ("queue", "completed"):
                session[field] = [path for path in session[field] if path != relative and not path.startswith(relative + "/")]
            self._save_notes_progress(subject, session)

    def generate_topic_notes(self, subject, relative_topic, instruction=""):
        topic = self.get_current_notes_topic(subject)
        if not topic or topic["relative_path"] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        prompt, system_prompt = render_prompt(
            "notes_topic",
            subject=subject,
            topic_label=topic["label"],
            instruction=instruction.strip() if isinstance(instruction, str) and instruction.strip() else "None",
        )
        response = self.llm.chat(
            prompt,
            system_prompt=system_prompt,
            max_output_tokens=NOTES_MAX_OUTPUT_TOKENS,
            use_grounding=False,
        )
        try:
            notes = parse_json_object(response).get("notes")
        except ValueError as error:
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
        prompt, system_prompt = render_prompt(
            "subtopic_suggestions",
            subject=subject,
            topic_label=topic["label"],
            notes=topic["notes"][:NOTES_CONTEXT_CHAR_LIMIT],
            instruction=instruction.strip() if isinstance(instruction, str) and instruction.strip() else "None",
        )
        response = self.llm.chat(
            prompt,
            system_prompt=system_prompt,
            max_output_tokens=SUBTOPIC_SUGGESTIONS_MAX_OUTPUT_TOKENS,
            use_grounding=False,
        )
        try:
            subtopics = parse_json_object(response).get("subtopics")
        except ValueError as error:
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
        session = self._load_notes_progress(subject)
        if not isinstance(session, dict) or not session.get("queue") or session["queue"][0] != relative_topic:
            raise ValueError("This topic is no longer the current notes task.")
        folder = self._topic_folder(subject, relative_topic)
        seen_names = set()
        known_paths = {path.casefold() for path in session["queue"] + session["completed"]}
        new_children = []
        for subtopic in selected_subtopics or []:
            name = self._folder_name(subtopic)
            if name.casefold() in seen_names:
                continue
            seen_names.add(name.casefold())
            child_relative = str(Path(relative_topic) / name) if relative_topic else name
            (folder / name).mkdir(parents=True, exist_ok=True)
            if child_relative.casefold() not in known_paths:
                new_children.append(child_relative)
                known_paths.add(child_relative.casefold())
        finished = session["queue"].pop(0)
        if finished not in session["completed"]:
            session["completed"].append(finished)
        for child_relative in reversed(new_children):
            session["queue"].insert(0, child_relative)
        self._save_notes_progress(subject, session)
        return self.get_notes_progress(subject)
