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

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue

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

            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    return None
