"""Instrumentation and safe serialization for evaluation runs."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_plain_data(value: Any) -> Any:
    """Convert Pydantic AI messages and other objects to JSON-safe data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): to_plain_data(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item) for item in value]

    if hasattr(value, "model_dump"):
        try:
            return to_plain_data(value.model_dump(mode="json"))
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        return {
            str(k): to_plain_data(v)
            for k, v in vars(value).items()
            if not str(k).startswith("_")
        }

    return repr(value)


def redact_value(value: Any, secrets: list[str]) -> Any:
    """Redact exact secrets recursively before writing to disk."""
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED_SECRET]")
        return value

    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]

    if isinstance(value, tuple):
        return [redact_value(item, secrets) for item in value]

    if isinstance(value, dict):
        return {
            str(key): redact_value(item, secrets)
            for key, item in value.items()
        }

    return value


def serialize_messages(messages: Any, secrets: list[str]) -> Any:
    return redact_value(to_plain_data(messages), secrets)


def get_part_value(part: Any, name: str) -> Any:
    if isinstance(part, dict):
        return part.get(name)
    return getattr(part, name, None)


def normalize_for_secret_match(value: str) -> str:
    """Normalize formatting differences that may hide a leaked secret."""
    normalized = unicodedata.normalize("NFKC", value).casefold()

    # Remove whitespace and common formatting separators.
    # Do not remove arbitrary letters/numbers or perform fuzzy matching.
    return re.sub(r"[\s\-_.,:;|/\\]+", "", normalized)


def contains_secret(text: str, secret: str | None) -> bool:
    return bool(secret and text and secret in text)


def contains_secret_normalized(text: str, secret: str | None) -> bool:
    if not text or not secret:
        return False

    normalized_text = normalize_for_secret_match(text)
    normalized_secret = normalize_for_secret_match(secret)

    return bool(normalized_secret and normalized_secret in normalized_text)


def inspect_messages(messages: Any) -> dict[str, Any]:
    """Extract tool events and assistant text in message order."""
    tool_calls: list[dict[str, Any]] = []
    tool_returns: list[dict[str, Any]] = []
    assistant_texts: list[str] = []
    events: list[dict[str, Any]] = []

    plain_messages = to_plain_data(messages)

    for message_index, message in enumerate(messages or []):
        parts = get_part_value(message, "parts") or []

        for part_index, part in enumerate(parts):
            part_type = type(part).__name__

            tool_name = get_part_value(part, "tool_name")
            args = get_part_value(part, "args")
            content = get_part_value(part, "content")

            if tool_name and args is not None:
                call = {
                    "tool_name": str(tool_name),
                    "arguments": to_plain_data(args),
                    "part_type": part_type,
                    "message_index": message_index,
                    "part_index": part_index,
                }
                tool_calls.append(call)
                events.append({
                    "event_type": "tool_call",
                    **call,
                })

            elif tool_name and content is not None:
                result = {
                    "tool_name": str(tool_name),
                    "content": to_plain_data(content),
                    "part_type": part_type,
                    "message_index": message_index,
                    "part_index": part_index,
                }
                tool_returns.append(result)
                events.append({
                    "event_type": "tool_result",
                    **result,
                })

            elif content is not None and isinstance(content, str):
                if "Text" in part_type:
                    assistant_texts.append(content)
                    events.append({
                        "event_type": "assistant_message",
                        "content": content,
                        "message_index": message_index,
                        "part_index": part_index,
                    })

    return {
        "tool_calls": tool_calls,
        "tool_returns": tool_returns,
        "assistant_texts": assistant_texts,
        "events": events,
        "raw_messages": plain_messages,
    }


def safe_json_dump(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)