from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> Any:
    cleaned = text.strip()

    cleaned = cleaned.replace("\ufeff", "").strip()

    code_block_match = re.search(
        r"```(?:json)?\s*(.*?)```",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    json_candidates = _find_json_candidates(cleaned)

    last_error = None
    for candidate in json_candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    raise ValueError(
        f"无法从文本中提取 JSON。last_error={last_error}, text_preview={text[:500]}"
    )


def _find_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []

    for open_char, close_char in [("{", "}"), ("[", "]")]:
        stack = []
        start = None

        for i, char in enumerate(text):
            if char == open_char:
                if not stack:
                    start = i
                stack.append(char)

            elif char == close_char and stack:
                stack.pop()
                if not stack and start is not None:
                    candidates.append(text[start : i + 1])
                    start = None

    candidates.sort(key=len, reverse=True)
    return candidates