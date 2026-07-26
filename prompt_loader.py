"""Load parameterized model prompts from the prompts directory."""

import json
from functools import lru_cache
from pathlib import Path
from string import Template


PROMPTS_PATH = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=None)
def _load_prompt_file(name):
    path = PROMPTS_PATH / f"{name}.yaml"
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"Could not load prompt '{name}': {error}") from error
    try:
        # Every prompt file is JSON syntax, which is valid YAML 1.2. This avoids
        # adding a runtime dependency while keeping prompts portable YAML files.
        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Prompt '{name}' is not valid YAML/JSON.") from error
    if not isinstance(data, dict) or not isinstance(data.get("prompt"), str):
        raise ValueError(f"Prompt '{name}' must define a prompt string.")
    return data


def render_prompt(name, **context):
    """Return the rendered prompt and optional system prompt for one YAML file."""
    data = _load_prompt_file(name)
    try:
        prompt = Template(data["prompt"]).substitute(**context)
        system = Template(data.get("system", "")).substitute(**context)
    except KeyError as error:
        raise ValueError(f"Prompt '{name}' is missing context for {error}.") from error
    return prompt, system or None
