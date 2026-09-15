from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .models import Classification
from .pipeline import primary_topic, rows_as_dicts


def write_outputs(
    out_dir: Path,
    public_rows: list[Classification],
    excluded_rows: list[Classification],
    skipped_rows: list[Classification],
    summary: dict[str, object],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "public_candidates.json", rows_as_dicts(public_rows))
    write_json(out_dir / "excluded_private.json", rows_as_dicts(excluded_rows))
    write_json(out_dir / "skipped_low_signal.json", rows_as_dicts(skipped_rows[:2000]))
    write_json(out_dir / "scan_summary.json", summary)
    write_public_markdown(out_dir / "public_candidates.md", public_rows)
    write_excluded_markdown(out_dir / "excluded_private.md", excluded_rows)
    write_topic_summary(out_dir / "topic_summary.md", public_rows, excluded_rows, summary)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def md_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def write_public_markdown(path: Path, rows: list[Classification]) -> None:
    rows = sorted(rows, key=lambda row: (-row.score, row.title.lower(), row.chunk_index))
    lines = [
        "# Public Candidate Catalog",
        "",
        "These units passed the privacy gate. They still need normal editorial review before publication.",
        "",
        "| # | Score | Title | Unit | Topics | Freshness | Source |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, 1):
        unit = row.unit_type if row.unit_type == "conversation" else f"chunk {row.chunk_index}"
        topics = ", ".join(topic for topic, _ in row.public_topics[:3])
        lines.append(
            f"| {index} | {row.score:.2f} | {md_escape(row.title)} | {unit} | "
            f"{md_escape(topics)} | {row.freshness} | {row.source_file} |"
        )

    lines.extend(["", "## Reviewer Preview", ""])
    for index, row in enumerate(rows[:100], 1):
        terms = ", ".join(term for term, _ in row.top_terms[:15])
        topics = ", ".join(topic for topic, _ in row.public_topics[:3])
        lines.extend(
            [
                f"### {index}. {row.title}",
                f"- Unit: {row.unit_type} {row.chunk_index if row.unit_type == 'chunk' else ''}".rstrip(),
                f"- Topics: {topics}",
                f"- Terms: {terms}",
                f"- Preview: {md_escape(row.preview)}",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_excluded_markdown(path: Path, rows: list[Classification]) -> None:
    rows = sorted(rows, key=lambda row: (row.decision, row.title.lower(), row.chunk_index))
    lines = [
        "# Excluded Private Catalog",
        "",
        "These units were removed because they matched private identifiers or sensitive personal domains.",
        "",
        "| # | Decision | Title | Unit | Reasons | Identifier Hits | Source |",
        "|---:|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, 1):
        unit = row.unit_type if row.unit_type == "conversation" else f"chunk {row.chunk_index}"
        lines.append(
            f"| {index} | {row.decision} | {md_escape(row.title)} | {unit} | "
            f"{md_escape(', '.join(row.exclusion_reasons))} | "
            f"{md_escape(', '.join(row.identifier_hits))} | {row.source_file} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_topic_summary(
    path: Path,
    public_rows: list[Classification],
    excluded_rows: list[Classification],
    summary: dict[str, object],
) -> None:
    by_topic: dict[str, list[Classification]] = defaultdict(list)
    for row in public_rows:
        by_topic[primary_topic(row)].append(row)

    lines = [
        "# Topic Summary",
        "",
        "## Public Candidate Counts",
        "",
        "| Topic | Units | Example Titles |",
        "|---|---:|---|",
    ]
    for topic, rows in sorted(by_topic.items(), key=lambda item: (-len(item[1]), item[0])):
        examples = "; ".join(sorted({row.title for row in rows})[:5])
        lines.append(f"| {md_escape(topic)} | {len(rows)} | {md_escape(examples)} |")

    lines.extend(["", "## Exclusion Counts", ""])
    for reason, count in dict(summary.get("exclusion_reason_counts", {})).items():
        lines.append(f"- {reason}: {count}")

    lines.extend(
        [
            "",
            "## Draft Review Schedule",
            "",
            "| # | Date | Title | Primary Topic | Pre-Publish Action |",
            "|---:|---|---|---|---|",
        ]
    )
    start = datetime(2026, 5, 6)
    scheduled = sorted(
        public_rows, key=lambda row: (not row.needs_fact_check, -row.score, row.title.lower())
    )[:156]
    for index, row in enumerate(scheduled, 1):
        date = (start + timedelta(days=7 * (index - 1))).strftime("%Y-%m-%d")
        action = "Fact-check, then write" if row.needs_fact_check else "Write as evergreen"
        lines.append(
            f"| {index} | {date} | {md_escape(row.title)} | {md_escape(primary_topic(row))} | {action} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
