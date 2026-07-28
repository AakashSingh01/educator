"""Tolerant parsing helpers for structured model responses."""

import json
import re


_FENCED_BLOCK = re.compile(
    r"```(?:json|yaml)?\s*(.*?)```",
    flags=re.IGNORECASE | re.DOTALL,
)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_LATEX_COMMANDS_COLLIDING_WITH_JSON_ESCAPES = {
    "bar", "begin", "beta", "boxed", "mathbf",
    "frac",
    "nabla", "neq", "not", "nu",
    "rho", "right", "rightarrow", "rfloor", "mathrm",
    "tan", "text", "tfrac", "theta", "therefore", "times",
}
def _repair_json_string_backslashes(candidate):
    """Escape raw LaTeX backslashes without altering JSON syntax."""

    repaired = []
    inside_string = False
    index = 0
    while index < len(candidate):
        character = candidate[index]
        if character == '"':
            preceding = 0
            cursor = index - 1
            while cursor >= 0 and candidate[cursor] == "\\":
                preceding += 1
                cursor -= 1
            if preceding % 2 == 0:
                inside_string = not inside_string
            repaired.append(character)
            index += 1
            continue
        if character != "\\" or not inside_string:
            repaired.append(character)
            index += 1
            continue

        following = candidate[index + 1:index + 2]
        if not following:
            repaired.append("\\\\")
            index += 1
            continue
        if following == "\\" or following in {'"', "/"}:
            repaired.extend((character, following))
            index += 2
            continue
        if following == "u" and re.match(r"^[0-9a-fA-F]{4}$", candidate[index + 2:index + 6]):
            repaired.append(character)
            index += 1
            continue
        if following in {"b", "f", "n", "r", "t"}:
            command_match = re.match(r"[A-Za-z]+", candidate[index + 1:])
            command = command_match.group(0) if command_match else following
            if command not in _LATEX_COMMANDS_COLLIDING_WITH_JSON_ESCAPES:
                repaired.append(character)
                index += 1
                continue
        repaired.append("\\\\")
        index += 1
    return "".join(repaired)


def _decode_json_candidate(candidate):
    candidate = candidate.strip().lstrip("\ufeff")
    if not candidate:
        raise json.JSONDecodeError("Empty response", candidate, 0)

    repaired = _repair_json_string_backslashes(candidate)
    versions = tuple(dict.fromkeys((
        repaired,
        _TRAILING_COMMA.sub(r"\1", repaired),
        candidate,
        _TRAILING_COMMA.sub(r"\1", candidate),
    )))
    for text in versions:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value

    # Prefer the repaired version when extracting JSON from surrounding prose;
    # otherwise a valid nested array could be mistaken for the intended root.
    decoder = json.JSONDecoder()
    for text in reversed(versions):
        for index, character in enumerate(text):
            if character not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            return value
    raise json.JSONDecodeError("No JSON value found", candidate, 0)


def parse_json_response(response):
    """Parse JSON despite Markdown fences, surrounding prose, or trailing commas."""

    if isinstance(response, (dict, list)):
        return response
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="replace")
    if not isinstance(response, str):
        raise ValueError("The model response is not JSON text.")

    candidates = [match.group(1) for match in _FENCED_BLOCK.finditer(response)]
    candidates.append(response)
    last_error = None
    for candidate in candidates:
        try:
            return _decode_json_candidate(candidate)
        except json.JSONDecodeError as error:
            last_error = error
    raise ValueError("The model response does not contain valid JSON.") from last_error


def parse_json_object(response):
    """Parse a structured response and require a JSON object at the root."""

    value = parse_json_response(response)
    if not isinstance(value, dict):
        raise ValueError("The model response must be a JSON object.")
    return value
