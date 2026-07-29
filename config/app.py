"""Application-wide environment configuration."""

import os
from pathlib import Path


PROJECT_PATH = Path(__file__).resolve().parent.parent


def load_project_env():
    """Load simple KEY=VALUE settings from the project-local .env file."""

    env_path = PROJECT_PATH / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value.strip().strip("'\""))


load_project_env()


def get_course_path():
    """Return the configured course directory with a project-local fallback."""

    configured_path = os.getenv("COURSE_PATH", "").strip()
    if not configured_path:
        return PROJECT_PATH / "course"

    course_path = Path(configured_path).expanduser()
    if not course_path.is_absolute():
        course_path = PROJECT_PATH / course_path
    return course_path.resolve()
