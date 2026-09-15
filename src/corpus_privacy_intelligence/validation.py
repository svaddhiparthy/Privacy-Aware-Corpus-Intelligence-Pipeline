from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .classifier import classify
from .models import CorpusUnit
from .reader import chunk_messages, extract_messages, iter_conversations
from .reports import md_escape
from .validators import all_validator_decisions, majority_label


def iter_validation_units(export_dir: Path, chunk_chars: int):
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
        full_unit = CorpusUnit(
            unit_id=f"{conversation_id}:conversation",
            source_file=path.name,
            conversation_id=conversation_id,
            title=title,
            unit_type="conversation",
            chunk_index=0,
            text=full_text,
        )
        yield full_unit

        if classify(full_unit).decision.startswith("exclude"):
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


def agreement_key(labels: list[str]) -> str:
    unique = sorted(set(labels))
    if len(unique) == 1:
        return "unanimous"
    if len(unique) == 2:
        return "two_to_one"
    return "three_way_split"


def run_validation(
    export_dir: Path, out_dir: Path, chunk_chars: int, max_disagreements: int
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    validator_counts: dict[str, Counter[str]] = defaultdict(Counter)
    majority_counts: Counter[str] = Counter()
    agreement_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    disagreements: list[dict[str, object]] = []
    total = 0

    for unit in iter_validation_units(export_dir, chunk_chars):
        total += 1
        decisions = all_validator_decisions(unit)
        labels = [decision.label for decision in decisions]
        for decision in decisions:
            validator_counts[decision.name][decision.label] += 1
        majority = majority_label(decisions)
        majority_counts[majority] += 1
        agreement_counts[agreement_key(labels)] += 1

        for i in range(len(decisions)):
            for j in range(i + 1, len(decisions)):
                same = decisions[i].label == decisions[j].label
                pair_counts[
                    f"{decisions[i].name}__{decisions[j].name}__{'agree' if same else 'disagree'}"
                ] += 1

        if len(set(labels)) > 1 and len(disagreements) < max_disagreements:
            disagreements.append(
                {
                    "unit_id": unit.unit_id,
                    "title": unit.title,
                    "unit_type": unit.unit_type,
                    "chunk_index": unit.chunk_index,
                    "source_file": unit.source_file,
                    "labels": {decision.name: decision.label for decision in decisions},
                    "confidences": {decision.name: decision.confidence for decision in decisions},
                    "reasons": {decision.name: decision.reasons for decision in decisions},
                    "preview": unit.text.replace("\n", " ")[:420],
                }
            )

    summary = {
        "units_validated": total,
        "validator_counts": {name: dict(counts) for name, counts in validator_counts.items()},
        "majority_counts": dict(majority_counts),
        "agreement_counts": dict(agreement_counts),
        "pair_counts": dict(pair_counts),
    }
    (out_dir / "automated_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "automated_validation_disagreements.json").write_text(
        json.dumps(disagreements, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_markdown(out_dir / "automated_validation_report.md", summary, disagreements)
    return summary


def write_markdown(path: Path, summary: dict[str, object], disagreements: list[dict[str, object]]) -> None:
    total = int(summary["units_validated"])
    lines = [
        "# Automated Classifier Validation Report",
        "",
        (
            "This report compares three automated classifiers over the same corpus units. It does not use "
            "manual labels."
        ),
        "",
        f"Units validated: {total}",
        "",
        "## Validator Counts",
        "",
        "| Validator | Public | Private | Review |",
        "|---|---:|---:|---:|",
    ]
    for name, counts in summary["validator_counts"].items():
        lines.append(
            f"| {name} | {counts.get('public', 0)} | {counts.get('private', 0)} | {counts.get('review', 0)} |"
        )

    lines.extend(["", "## Majority Vote", "", "| Label | Units | Percent |", "|---|---:|---:|"])
    for label, count in summary["majority_counts"].items():
        lines.append(f"| {label} | {count} | {count / total * 100:.2f}% |")

    lines.extend(["", "## Agreement", "", "| Agreement Type | Units | Percent |", "|---|---:|---:|"])
    for label, count in summary["agreement_counts"].items():
        lines.append(f"| {label} | {count} | {count / total * 100:.2f}% |")

    lines.extend(["", "## Sample Disagreements", ""])
    lines.append("| # | Title | Unit | Labels | Reasons | Preview |")
    lines.append("|---:|---|---|---|---|---|")
    for index, row in enumerate(disagreements[:150], 1):
        unit = row["unit_type"] if row["unit_type"] == "conversation" else f"chunk {row['chunk_index']}"
        labels = "; ".join(f"{name}: {label}" for name, label in row["labels"].items())
        reasons = "; ".join(
            f"{name}: {', '.join(values[:4])}" for name, values in row["reasons"].items() if values
        )
        lines.append(
            f"| {index} | {md_escape(row['title'])} | {unit} | {md_escape(labels)} | "
            f"{md_escape(reasons)} | {md_escape(row['preview'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run automated multi-classifier validation.")
    parser.add_argument("--export-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--chunk-chars", type=int, default=9000)
    parser.add_argument("--max-disagreements", type=int, default=500)
    args = parser.parse_args()
    summary = run_validation(args.export_dir, args.out_dir, args.chunk_chars, args.max_disagreements)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
