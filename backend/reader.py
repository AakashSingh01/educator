"""Read-only access to notes and prepared learning items."""

from config.question_bank import QUESTION_BANK_DIFFICULTIES


class ReaderMixin:
    """Expose one exact topic folder without modifying course data."""

    def get_reader_topic(self, subject, relative_topic=""):
        subject = self._folder_name(subject)
        folder = self._topic_folder(subject, relative_topic)
        if not folder.is_dir():
            raise ValueError("The selected reading topic does not exist.")

        notes_path = folder / "notes.txt"
        try:
            notes = (
                notes_path.read_text(encoding="utf-8").strip()
                if notes_path.is_file()
                else ""
            )
        except OSError as error:
            raise ValueError(f"Could not read this topic's notes: {error}") from error

        children = sorted(
            child.name
            for child in folder.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
        item_groups = {"mcq": [], "subjective": [], "theory": []}
        for item_type in item_groups:
            for difficulty in QUESTION_BANK_DIFFICULTIES:
                bank = self._read_question_bank(folder, item_type, difficulty)
                if not bank:
                    continue
                item_groups[item_type].extend(
                    {**item, "difficulty": difficulty}
                    for item in bank["items"]
                    if isinstance(item, dict)
                )

        return {
            "subject": subject,
            "relative_topic": relative_topic,
            "label": subject if not relative_topic else f"{subject} / {relative_topic}",
            "notes": notes,
            "children": children,
            "objective": item_groups["mcq"],
            "subjective": item_groups["subjective"],
            "theory": item_groups["theory"],
        }
