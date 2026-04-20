"""
Core JSON repair heuristics — no heavy deps, safe to bundle on a Worker.
"""

from __future__ import annotations

import json
import re


def repair_json(raw: str) -> tuple[str, list[str]]:
    """
    Attempt to repair malformed JSON.

    Returns (repaired_json_str, list_of_applied_fixes).
    Raises ValueError if the input cannot be salvaged.
    """
    fixes: list[str] = []
    text = raw.strip()

    # 1. Already valid — nothing to do
    if _try_parse(text) is not None:
        return text, fixes

    # 2. Strip trailing commas before ] or }
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    if cleaned != text:
        fixes.append("removed trailing commas")
        text = cleaned

    # 3. Replace single quotes used as string delimiters
    # Only replace when they clearly wrap a key or value
    single_quoted = re.sub(r"'([^']*)'", r'"\1"', text)
    if single_quoted != text:
        fixes.append("replaced single quotes with double quotes")
        text = single_quoted

    # 4. Unquoted keys  { key: "val" } → { "key": "val" }
    unquoted_key = re.sub(r'([{,]\s*)([A-Za-z_]\w*)(\s*:)', r'\1"\2"\3', text)
    if unquoted_key != text:
        fixes.append("quoted unquoted object keys")
        text = unquoted_key

    # 5. Python/JS literals → JSON literals
    literal_map = {"True": "true", "False": "false", "None": "null", "undefined": "null"}
    for src, dst in literal_map.items():
        pattern = rf'\b{src}\b'
        replaced = re.sub(pattern, dst, text)
        if replaced != text:
            fixes.append(f"replaced {src} → {dst}")
            text = replaced

    # 6. Truncated JSON — try to close open brackets/braces
    result = _try_parse(text)
    if result is None:
        text, extra_fixes = _close_open_brackets(text)
        fixes.extend(extra_fixes)

    result = _try_parse(text)
    if result is None:
        raise ValueError("Could not repair JSON")

    return text, fixes


def validate_json(raw: str) -> dict:
    """
    Return parsed object if valid, raise ValueError with a descriptive message otherwise.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at line {exc.lineno}, col {exc.colno}: {exc.msg}") from exc


def sanitize_json_output(raw_string: str) -> tuple[str, list[str]]:
    """
    Strip prose preambles and repair malformed control characters, then
    return valid JSON. Raises ValueError if the result cannot be parsed.

    Returns (sanitized_json_str, list_of_applied_fixes).
    """
    fixes: list[str] = []
    text = raw_string

    # 1. Replace literal \n \t \r escape sequences that appear outside strings
    #    (e.g. a model emitting \\n instead of a real newline inside a value)
    ctrl_cleaned = re.sub(r'\\([nrt])', lambda m: {"n": "\n", "r": "\r", "t": "\t"}[m.group(1)], text)
    if ctrl_cleaned != text:
        fixes.append("decoded escaped control characters (\\n/\\r/\\t)")
        text = ctrl_cleaned

    # 2. Remove actual unescaped control characters (0x00–0x1F except \n \r \t)
    #    that are illegal inside JSON strings
    no_ctrl = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    if no_ctrl != text:
        fixes.append("removed illegal control characters")
        text = no_ctrl

    # 3. Strip prose preamble — everything before the first { or [
    match = re.search(r'[{\[]', text)
    if match and match.start() > 0:
        fixes.append(f"stripped {match.start()}-char prose preamble")
        text = text[match.start():]

    # 4. Strip prose suffix — everything after the last } or ]
    last = max(text.rfind("}"), text.rfind("]"))
    if last != -1 and last < len(text) - 1:
        fixes.append(f"stripped {len(text) - last - 1}-char prose suffix")
        text = text[: last + 1]

    # 5. Delegate remaining structural issues to repair_json
    if _try_parse(text) is None:
        text, repair_fixes = repair_json(text)
        fixes.extend(repair_fixes)

    if _try_parse(text) is None:
        raise ValueError("Could not sanitize input into valid JSON")

    return text, fixes


# ── helpers ──────────────────────────────────────────────────────────────────

def _try_parse(text: str) -> object | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _close_open_brackets(text: str) -> tuple[str, list[str]]:
    fixes: list[str] = []
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()

    if stack:
        closing = "".join(reversed(stack))
        fixes.append(f"appended closing brackets: {closing!r}")
        text = text + closing

    return text, fixes
