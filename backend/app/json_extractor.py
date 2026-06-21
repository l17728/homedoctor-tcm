"""Shared JSON extraction utility — balanced brace matching for LLM responses.

Replaces fragile `re.search(r'\\{[^}]+\\}')` which truncates nested JSON.
"""


def extract_json(text: str) -> dict | list | None:
    """Extract the first JSON object/array from text using balanced brace matching.

    Handles nested objects: {"a": {"b": 1}} correctly.
    Returns parsed JSON or None if not found.
    """
    import json

    if not text:
        return None

    text = text.strip()

    brace_start = text.find("{")
    bracket_start = text.find("[")

    if brace_start == -1 and bracket_start == -1:
        return None
    if brace_start == -1:
        start_char, end_char, start = "[", "]", bracket_start
    elif bracket_start == -1:
        start_char, end_char, start = "{", "}", brace_start
    elif brace_start < bracket_start:
        start_char, end_char, start = "{", "}", brace_start
    else:
        start_char, end_char, start = "[", "]", bracket_start

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    other = text.find(start_char, i + 1)
                    if other != -1:
                        return extract_json(text[other:])
                    break

    return None
