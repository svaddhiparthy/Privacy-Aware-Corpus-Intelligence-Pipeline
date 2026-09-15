"""Fail if the aggregates published anywhere disagree with the artifact of record.

The public project page states corpus counts, per-validator comparisons and agreement
percentages. Those numbers used to live only in the page's HTML, which meant nothing stopped
them from drifting away from the pipeline, and nothing let a reader check them.

This script asserts the artifact is internally consistent and agrees with the committed
validation document. CI runs it on every change.

Usage:
    python scripts/check_published_numbers.py
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = PROJECT_ROOT / "docs" / "artifacts" / "corpus_run" / "summary.json"
VALIDATION_DOC = PROJECT_ROOT / "docs" / "advanced_non_llm_validation.md"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    if not SUMMARY.exists():
        sys.exit(f"missing artifact of record: {SUMMARY}")
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))

    corpus = data["corpus"]
    total = corpus["units_scanned"]
    parts = corpus["public_candidates"] + corpus["excluded_units"] + corpus["skipped_low_signal"]
    check(
        parts == total,
        f"corpus split does not sum: {parts} != {total}",
    )

    topics = data["public_topic_groups"]
    check(
        len(topics) == corpus["public_topic_groups"],
        f"topic group count mismatch: {len(topics)} listed, " f"{corpus['public_topic_groups']} declared",
    )
    topic_units = sum(t["units"] for t in topics)
    check(
        topic_units <= corpus["public_candidates"],
        f"topic units {topic_units} exceed public candidates {corpus['public_candidates']}",
    )

    # Every full-corpus validator must account for exactly the whole corpus.
    for name, counts in data["full_corpus_validators"].items():
        if name.startswith("_"):
            continue
        got = counts["public"] + counts["private"] + counts["review"]
        check(got == total, f"full-corpus validator {name} sums to {got}, expected {total}")

    # The policy classifier maps skip_low_signal to review, so its review count is fixed.
    policy = data["full_corpus_validators"]["policy_classifier"]
    check(
        policy["public"] == corpus["public_candidates"],
        f"policy_classifier public {policy['public']} != pipeline public " f"{corpus['public_candidates']}",
    )
    check(
        policy["private"] == corpus["excluded_units"],
        f"policy_classifier private {policy['private']} != pipeline excluded " f"{corpus['excluded_units']}",
    )
    check(
        policy["review"] == corpus["skipped_low_signal"],
        f"policy_classifier review {policy['review']} != pipeline skipped "
        f"{corpus['skipped_low_signal']}; policy_classifier() maps skip_low_signal to review",
    )

    # Every sample validator must account for exactly the sample.
    sample = data["sample_validators"]
    size = sample["sample_size"]
    for name, counts in sample.items():
        if name.startswith("_") or name == "sample_size":
            continue
        got = counts["public"] + counts["private"] + counts["review"]
        check(got == size, f"sample validator {name} sums to {got}, expected {size}")

    # The sample table is committed in the validation doc; the artifact must match it.
    doc = VALIDATION_DOC.read_text(encoding="utf-8")
    for name in ("policy", "strict_detector", "semantic_score_classifier", "presidio", "spacy"):
        key = "policy_classifier" if name == "policy" else name
        row = re.search(rf"^\|\s*{re.escape(name)}\s*\|(.+)$", doc, re.MULTILINE)
        if not row:
            failures.append(f"{name} row not found in {VALIDATION_DOC.name}")
            continue
        nums = [int(x) for x in re.findall(r"\d+", row.group(1))]
        expected = [sample[key]["public"], sample[key]["private"], sample[key]["review"]]
        check(
            nums[:3] == expected,
            f"{name}: doc says {nums[:3]}, artifact says {expected}",
        )

    agreement = data["agreement"]
    check(
        abs(
            agreement["unanimous_pct"]
            + agreement["two_to_one_pct"]
            + agreement["three_way_split_pct"]
            - 99.99
        )
        < 0.02,
        "agreement split does not total 100 percent: "
        f"{agreement['unanimous_pct']} + {agreement['two_to_one_pct']} + "
        f"{agreement['three_way_split_pct']}",
    )

    if failures:
        print("published numbers are inconsistent:\n")
        for failure in failures:
            print("  -", failure)
        sys.exit(1)
    print(f"published numbers are consistent ({total:,} units, sample of {size})")


if __name__ == "__main__":
    main()
