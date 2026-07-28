"""Central configuration for the language-model provider.

Set ``EDUCATOR_LLM_PROVIDER`` to either ``ollama`` or ``gemini``.  Secrets are
read from the environment so an API key is never stored with the project.
"""

import os

from app_config import load_project_env


def _integer_setting(name, default, minimum=1, maximum=None):
    """Read a bounded integer setting without making a bad .env value crash the app."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    value = max(minimum, value)
    return min(value, maximum) if maximum is not None else value


load_project_env()


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT_SECONDS = _integer_setting("OLLAMA_TIMEOUT_SECONDS", 60)

# Configure these only when EDUCATOR_LLM_PROVIDER=gemini. Keep the API key
# in the environment, for example: export GEMINI_API_KEY="...". GOOGLE_API_KEY
# is also accepted for compatibility with Google's standard SDK examples.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_TIMEOUT_SECONDS = _integer_setting("GEMINI_TIMEOUT_SECONDS", 120)
# This is a hard ceiling. Individual short tasks request smaller limits.
GEMINI_MAX_OUTPUT_TOKENS = _integer_setting(
    "GEMINI_MAX_OUTPUT_TOKENS",
    4096,
    minimum=256,
    maximum=32768,
)
# Smaller structured tasks use these provider-independent ceilings.
LEARNING_ITEM_MAX_OUTPUT_TOKENS = _integer_setting(
    "LEARNING_ITEM_MAX_OUTPUT_TOKENS", 1800, minimum=256
)
RESULT_FOLLOW_UP_MAX_OUTPUT_TOKENS = _integer_setting(
    "RESULT_FOLLOW_UP_MAX_OUTPUT_TOKENS", 1200, minimum=256
)
SUBJECTIVE_ASSESSMENT_MAX_OUTPUT_TOKENS = _integer_setting(
    "SUBJECTIVE_ASSESSMENT_MAX_OUTPUT_TOKENS", 800, minimum=256
)
NOTES_MAX_OUTPUT_TOKENS = _integer_setting(
    "NOTES_MAX_OUTPUT_TOKENS", 3600, minimum=256
)
SUBTOPIC_SUGGESTIONS_MAX_OUTPUT_TOKENS = _integer_setting(
    "SUBTOPIC_SUGGESTIONS_MAX_OUTPUT_TOKENS", 800, minimum=256
)
NOTES_CONTEXT_CHAR_LIMIT = _integer_setting(
    "NOTES_CONTEXT_CHAR_LIMIT", 6000, minimum=1000
)
GEMINI_USE_GOOGLE_SEARCH = os.getenv("GEMINI_USE_GOOGLE_SEARCH", "false").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
LLM_PROVIDER = os.getenv(
    "EDUCATOR_LLM_PROVIDER",
    "gemini" if GEMINI_API_KEY else "ollama",
).strip().casefold()
