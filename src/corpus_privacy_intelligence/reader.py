from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import CorpusUnit


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


def iter_units(export_dir: Path, chunk_chars: int) -> Iterable[CorpusUnit]:
    sequence = 0
    for path, conversation in iter_conversations(export_dir):
        sequence += 1
        title = conversation.get("title") or "(untitled)"
        conversation_id = (
            conversation.get("id")
            or hashlib.sha1(f"{path.name}:{sequence}:{title}".encode()).hexdigest()[:16]
        )
        messages = extract_messages(conversation)
        if not messages:
            continue

        full_text = f"TITLE: {title}\n\n" + "\n\n".join(
            f"{message['role'].upper()}: {message['text']}" for message in messages
        )
        yield CorpusUnit(
            unit_id=f"{conversation_id}:conversation",
            source_file=path.name,
            conversation_id=conversation_id,
            title=title,
            unit_type="conversation",
            chunk_index=0,
            text=full_text,
        )

        for index, chunk in enumerate(chunk_messages(messages, chunk_chars), 1):
            yield CorpusUnit(
                unit_id=f"{conversation_id}:chunk:{index}",
                source_file=path.name,
                conversation_id=conversation_id,
                title=title,
                unit_type="chunk",
                chunk_index=index,
                text=f"TITLE: {title}\n\n{chunk}",
            )
