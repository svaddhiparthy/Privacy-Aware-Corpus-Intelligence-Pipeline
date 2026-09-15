from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .advanced_detectors import DetectorResult, make_advanced_detectors, preview_for_report
from .models import CorpusUnit
from .reader import chunk_messages, extract_messages, iter_conversations
from .reports import md_escape
from .validators import PRIVATE_LABEL, PUBLIC_LABEL, REVIEW_LABEL


def iter_units(export_dir: Path, chunk_chars: int, limit: int = 0):
    count = 0
    for path, conversation in iter_conversations(export_dir):
        title = conversation.get("title") or "(untitled)"
        conversation_id = conversation.get("id") or f"{path.stem}:{count}"
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
        count += 1
        if limit and count >= limit:
            return
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
            count += 1
            if limit and count >= limit:
                return


def weighted_ensemble(results: list[DetectorResult]) -> tuple[str, float]:
    weights = {
        "policy": 1.0,
        "strict_detector": 0.9,
        "semantic_score_classifier": 0.8,
        "presidio": 1.2,
        "spacy": 0.8,
    }
    scores = Counter()
    for result in results:
        if result.confidence == 0:
            continue
        scores[result.label] += weights.get(result.name, 0.75) * result.confidence
    if scores[PRIVATE_LABEL] >= 1.15:
        total = sum(scores.values()) or 1
        return PRIVATE_LABEL, round(scores[PRIVATE_LABEL] / total, 4)
    if scores[PUBLIC_LABEL] > scores[PRIVATE_LABEL] and scores[PUBLIC_LABEL] >= 1.25:
        total = sum(scores.values()) or 1
        return PUBLIC_LABEL, round(scores[PUBLIC_LABEL] / total, 4)
    return REVIEW_LABEL, round((scores[REVIEW_LABEL] + 0.25) / (sum(scores.values()) + 0.25), 4)


def run(export_dir: Path, out_dir: Path, chunk_chars: int, limit: int) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    detectors = make_advanced_detectors()
    rows = []
    detector_counts: dict[str, Counter[str]] = {}
    ensemble_counts = Counter()
    agreement_counts = Counter()

    for unit in iter_units(export_dir, chunk_chars, limit):
        results = [detector(unit) for detector in detectors]
        for result in results:
            detector_counts.setdefault(result.name, Counter())[result.label] += 1
        label, confidence = weighted_ensemble(results)
        ensemble_counts[label] += 1
        labels = [result.label for result in results if result.confidence > 0]
        agreement_counts["unanimous" if len(set(labels)) == 1 else "mixed"] += 1
        rows.append(
            {
                "unit_id": unit.unit_id,
                "title": unit.title,
                "unit_type": unit.unit_type,
                "chunk_index": unit.chunk_index,
                "source_file": unit.source_file,
                "ensemble_label": label,
                "ensemble_confidence": confidence,
                "detectors": [
                    {
                        "name": result.name,
                        "label": result.label,
                        "confidence": result.confidence,
                        "reasons": result.reasons,
                        "metadata": result.metadata,
                    }
                    for result in results
                ],
                "preview": preview_for_report(unit),
            }
        )

    summary = {
        "units_analyzed": len(rows),
        "chunk_chars": chunk_chars,
        "limit": limit,
        "detector_counts": {name: dict(counts) for name, counts in detector_counts.items()},
        "ensemble_counts": dict(ensemble_counts),
        "agreement_counts": dict(agreement_counts),
    }
    write_outputs(out_dir, rows, summary)
    return summary


def write_outputs(out_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    (out_dir / "advanced_validation_results.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "advanced_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = [
        "# Advanced Free Non-LLM Validation Report",
        "",
        (
            "This report combines the current policy classifier, strict rules, semantic scoring, optional "
            "Presidio, and optional spaCy."
        ),
        "",
        f"Units analyzed: {summary['units_analyzed']}",
        "",
        "## Detector Counts",
        "",
        "| Detector | Public | Private | Review |",
        "|---|---:|---:|---:|",
    ]
    for name, counts in summary["detector_counts"].items():
        lines.append(
            f"| {name} | {counts.get(PUBLIC_LABEL, 0)} | "
            f"{counts.get(PRIVATE_LABEL, 0)} | {counts.get(REVIEW_LABEL, 0)} |"
        )
    lines.extend(["", "## Ensemble Counts", "", "| Label | Count |", "|---|---:|"])
    for label, count in summary["ensemble_counts"].items():
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "## Sample Rows",
            "",
            "| # | Title | Unit | Ensemble | Detectors | Preview |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for index, row in enumerate(rows[:150], 1):
        unit = row["unit_type"] if row["unit_type"] == "conversation" else f"chunk {row['chunk_index']}"
        detectors = "; ".join(f"{d['name']}={d['label']}" for d in row["detectors"])
        lines.append(
            f"| {index} | {md_escape(row['title'])} | {unit} | "
            f"{row['ensemble_label']} ({row['ensemble_confidence']:.2f}) | "
            f"{md_escape(detectors)} | {md_escape(row['preview'])} |"
        )
    (out_dir / "advanced_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run advanced free non-LLM detector validation.")
    parser.add_argument("--export-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--chunk-chars", type=int, default=9000)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    summary = run(args.export_dir, args.out_dir, args.chunk_chars, args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
