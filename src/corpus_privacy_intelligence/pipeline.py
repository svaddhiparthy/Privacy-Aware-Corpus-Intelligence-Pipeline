from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .classifier import classify
from .models import Classification, CorpusUnit
from .reader import chunk_messages, extract_messages, iter_conversations


def run_pipeline(export_dir: Path, min_public_score: float, chunk_chars: int) -> dict[str, object]:
    public_rows: list[Classification] = []
    excluded_rows: list[Classification] = []
    skipped_rows: list[Classification] = []
    unit_count = 0

    for path, conversation in iter_conversations(export_dir):
        title = conversation.get("title") or "(untitled)"
        conversation_id = conversation.get("id") or f"{path.stem}:{unit_count}"
        messages = extract_messages(conversation)
        if not messages:
            continue

        full_text = f"TITLE: {title}\n\n" + "\n\n".join(
            f"{message['role'].upper()}: {message['text']}" for message in messages
        )
        unit = CorpusUnit(
            unit_id=f"{conversation_id}:conversation",
            source_file=path.name,
            conversation_id=conversation_id,
            title=title,
            unit_type="conversation",
            chunk_index=0,
            text=full_text,
        )
        unit_count += 1
        result = classify(unit)
        if result.decision == "public_candidate" and result.score >= min_public_score:
            public_rows.append(result)
        elif result.decision.startswith("exclude"):
            excluded_rows.append(result)
            for index, chunk in enumerate(chunk_messages(messages, chunk_chars), 1):
                chunk_unit = CorpusUnit(
                    unit_id=f"{conversation_id}:chunk:{index}",
                    source_file=path.name,
                    conversation_id=conversation_id,
                    title=title,
                    unit_type="chunk",
                    chunk_index=index,
                    text=f"TITLE: {title}\n\n{chunk}",
                )
                unit_count += 1
                chunk_result = classify(chunk_unit)
                if chunk_result.decision == "public_candidate" and chunk_result.score >= min_public_score:
                    public_rows.append(chunk_result)
                elif chunk_result.decision.startswith("exclude"):
                    excluded_rows.append(chunk_result)
                else:
                    skipped_rows.append(chunk_result)
        else:
            skipped_rows.append(result)

    return {
        "unit_count": unit_count,
        "public": public_rows,
        "excluded": excluded_rows,
        "skipped": skipped_rows,
        "summary": build_summary(unit_count, public_rows, excluded_rows, skipped_rows),
    }


def build_summary(
    unit_count: int,
    public_rows: list[Classification],
    excluded_rows: list[Classification],
    skipped_rows: list[Classification],
) -> dict[str, object]:
    return {
        "units_scanned": unit_count,
        "public_candidate_units": len(public_rows),
        "excluded_units": len(excluded_rows),
        "skipped_units": len(skipped_rows),
        "public_topic_counts": dict(Counter(primary_topic(row) for row in public_rows)),
        "exclusion_reason_counts": dict(
            Counter(reason for row in excluded_rows for reason in row.exclusion_reasons)
        ),
        "identifier_hit_counts": dict(Counter(hit for row in excluded_rows for hit in row.identifier_hits)),
    }


def primary_topic(row: Classification) -> str:
    return row.public_topics[0][0] if row.public_topics else "Unclassified"


def rows_as_dicts(rows: list[Classification]) -> list[dict[str, object]]:
    return [asdict(row) for row in rows]
