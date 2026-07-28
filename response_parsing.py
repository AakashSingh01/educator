"""Tolerant parsing helpers for structured model responses."""

import json
import re


_FENCED_BLOCK = re.compile(
    r"```(?:json|yaml)?\s*(.*?)```",
    flags=re.IGNORECASE | re.DOTALL,
)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_UNESCAPED_LATEX_COMMAND = re.compile(
    r"(?<!\\)\\(?=(?:"
    r"alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|phi|omega|"
    r"frac|dfrac|tfrac|sqrt|sum|prod|int|lim|infty|partial|nabla|"
    r"sin|cos|tan|cot|sec|csc|log|ln|exp|"
    r"cdot|times|div|pm|mp|leq?|geq?|neq|approx|equiv|"
    r"begin|end|left|right|text|mathrm|mathbf|mathbb|mathcal|operatorname|"
    r"overline|underline|hat|bar|vec"
    r")\b)"
)


def _repair_latex_backslashes(candidate):
    """Escape common raw LaTeX commands inside otherwise valid JSON strings."""

    return _UNESCAPED_LATEX_COMMAND.sub(r"\\\\", candidate)


def _decode_json_candidate(candidate):
    candidate = candidate.strip().lstrip("\ufeff")
    if not candidate:
        raise json.JSONDecodeError("Empty response", candidate, 0)

    repaired = _repair_latex_backslashes(candidate)
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
