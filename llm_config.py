"""Central configuration for the language-model provider.

Set ``EDUCATOR_LLM_PROVIDER`` to either ``ollama`` or ``gemini``.  Secrets are
read from the environment so an API key is never stored with the project.
"""

import os
from pathlib import Path


def _load_project_env():
    """Load simple KEY=VALUE settings from the project-local .env file."""

    env_path = Path(__file__).with_name(".env")
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


_load_project_env()


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

# Configure these only when EDUCATOR_LLM_PROVIDER=gemini. Keep the API key
# in the environment, for example: export GEMINI_API_KEY="...". GOOGLE_API_KEY
# is also accepted for compatibility with Google's standard SDK examples.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))
GEMINI_USE_GOOGLE_SEARCH = os.getenv("GEMINI_USE_GOOGLE_SEARCH", "true").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
LLM_PROVIDER = os.getenv(
    "EDUCATOR_LLM_PROVIDER",
    "gemini" if GEMINI_API_KEY else "ollama",
).strip().casefold()
