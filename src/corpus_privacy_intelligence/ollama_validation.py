from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from .reports import md_escape

LABELS = {"public", "private", "review"}


def build_prompt(row: dict[str, Any]) -> str:
    labels = row.get("labels", {})
    reasons = row.get("reasons", {})
    preview = re.sub(r"\s+", " ", row.get("preview", "")).strip()[:1800]
    preview = re.sub(r"\b(USER|ASSISTANT|TOOL|SYSTEM):\s*", "", preview)
    return f"""
You are classifying a text excerpt for privacy-safe publishing.

Policy:
- private: contains private identifiers, personal health, immigration/visa/legal-status, resume/job-search/recruiter/interview/salary/employer-specific career material, or direct personal account/contact details.
- public: general technical, product, vehicle, finance explainer, cooking, culture, tutorial, or creative content with no private personal context.
- review: ambiguous, mixed, or too little context.

Privacy overrides usefulness. If a text has both public value and private personal material, choose private or review.
Do not treat transcript role labels such as USER, ASSISTANT, or TOOL as private identifiers.
Do not treat public figures, company names, product names, or general place names as private identifiers by themselves.
Do not mark general technical workplace concepts as private unless the excerpt is about a person's resume, job search, recruiter, interview, salary, employer-specific situation, or private account.
Do not mark general vehicle, travel, product, movie, food, culture, or how-to questions private unless there is personal contact, account, legal, health, immigration, or job-search context.

Return only JSON with this exact shape:
{{"label":"public|private|review","confidence":0.0,"reason":"short reason"}}

Title: {row.get("title", "")}
Unit: {row.get("unit_type", "")} {row.get("chunk_index", "")}
Local classifier labels: {json.dumps(labels, ensure_ascii=False)}
Local classifier reasons: {json.dumps(reasons, ensure_ascii=False)}
Excerpt:
{preview}
""".strip()


def call_ollama(model: str, prompt: str, host: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": 120,
        },
    }
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"label": "review", "confidence": 0.0, "reason": f"ollama_error: {exc}"}

    text = raw.get("response", "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        parsed = (
            json.loads(match.group(0))
            if match
            else {"label": "review", "confidence": 0.0, "reason": text[:120]}
        )

    label = str(parsed.get("label", "review")).strip().lower()
    if label not in LABELS:
        label = "review"
    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return {
        "label": label,
        "confidence": confidence,
        "reason": str(parsed.get("reason", ""))[:300],
    }


def majority_from_local(labels: dict[str, str]) -> str:
    counts = Counter(labels.values())
    if not counts:
        return "review"
    label, count = counts.most_common(1)[0]
    return label if count >= 2 else "review"


def write_markdown(path: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# Ollama Disagreement Validation",
        "",
        (
            "This pass uses a local Ollama model to classify saved disagreement cases. It is an additional "
            "local semantic check, not a source of truth by itself."
        ),
        "",
        f"Model: `{summary['model']}`",
        f"Items classified: {summary['items_classified']}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]
    for key, value in summary["counts"].items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Results",
            "",
            "| # | Title | Local Majority | Ollama | Confidence | Agreement | Reason |",
            "|---:|---|---|---|---:|---|---|",
        ]
    )
    for index, row in enumerate(results, 1):
        lines.append(
            f"| {index} | {md_escape(row['title'])} | {row['local_majority']} | "
            f"{row['ollama_label']} | {row['ollama_confidence']:.2f} | "
            f"{row['agreement']} | {md_escape(row['ollama_reason'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(out_dir: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    (out_dir / "ollama_validation_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "ollama_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_markdown(out_dir / "ollama_validation_report.md", results, summary)


def build_summary(
    model: str, input_path: Path, items_available: int, results: list[dict[str, Any]]
) -> dict[str, Any]:
    counts = Counter()
    counts.update(f"ollama_{row['ollama_label']}" for row in results)
    counts.update(f"local_{row['local_majority']}" for row in results)
    counts.update(row["agreement"] for row in results)
    return {
        "model": model,
        "input_path": str(input_path),
        "items_available": items_available,
        "items_classified": len(results),
        "counts": dict(counts),
    }


def run(input_path: Path, out_dir: Path, model: str, host: str, limit: int, timeout: int) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    selected = rows[:limit] if limit else rows
    results_path = out_dir / "ollama_validation_results.json"
    results = []
    if results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
    completed = {row.get("unit_id") for row in results}

    for row in selected:
        if row.get("unit_id") in completed:
            continue
        local_majority = majority_from_local(row.get("labels", {}))
        ollama = call_ollama(model, build_prompt(row), host, timeout)
        agreement = "agree" if ollama["label"] == local_majority else "disagree"
        results.append(
            {
                "unit_id": row.get("unit_id"),
                "title": row.get("title"),
                "unit_type": row.get("unit_type"),
                "chunk_index": row.get("chunk_index"),
                "source_file": row.get("source_file"),
                "local_labels": row.get("labels", {}),
                "local_majority": local_majority,
                "ollama_label": ollama["label"],
                "ollama_confidence": ollama["confidence"],
                "ollama_reason": ollama["reason"],
                "agreement": agreement,
            }
        )
        summary = build_summary(model, input_path, len(rows), results)
        write_outputs(out_dir, results, summary)

    summary = build_summary(model, input_path, len(rows), results)
    write_outputs(out_dir, results, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate disagreement cases with a local Ollama model.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    summary = run(args.input, args.out_dir, args.model, args.host, args.limit, args.timeout)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
