from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def message_text(message: dict[str, Any] | None) -> str:
    if not message:
        return ""
    parts = (message.get("content") or {}).get("parts") or []
    text_parts = []
    for part in parts:
        if isinstance(part, str):
            text_parts.append(part)
        elif isinstance(part, dict) and part.get("text"):
            text_parts.append(str(part["text"]))
    return "\n".join(text_parts)


def extract_messages(conversation: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for node in (conversation.get("mapping") or {}).values():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        text = message_text(message)
        if not text.strip():
            continue
        role = ((message.get("author") or {}).get("role") or "unknown") if message else "unknown"
        created = message.get("create_time") if message else ""
        rows.append({"role": role, "text": text, "created": str(created or "")})
    rows.sort(key=lambda row: row["created"])
    return rows


def chunk_messages(messages: list[dict[str, str]], target_chars: int) -> list[str]:
    chunks = []
    current = []
    size = 0
    for message in messages:
        text = f"{message['role'].upper()}: {message['text']}"
        if current and size + len(text) > target_chars:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        current.append(text)
        size += len(text)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def iter_conversations(export_dir: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    for path in sorted(export_dir.glob("conversations-*.json")):
        data = load_json(path)
        if not isinstance(data, list):
            continue
        for conversation in data:
            yield path, conversation
