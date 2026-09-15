from __future__ import annotations

import math
from collections import Counter

from .models import Classification, CorpusUnit
from .pii import detect_identifiers
from .taxonomy import FACT_CHECK_TOPICS, PUBLIC_TAXONOMY, SENSITIVE_DOMAIN_TERMS
from .text import compact_preview, normalize_token, term_counter


def term_score(text_l: str, counts: Counter[str], terms: list[str]) -> int:
    score = 0
    for term in terms:
        term_l = term.lower()
        if " " in term_l or "-" in term_l:
            score += text_l.count(term_l)
        else:
            score += counts.get(normalize_token(term_l), 0)
    return score


def classify_public_topics(text: str, counts: Counter[str]) -> list[tuple[str, int]]:
    text_l = text.lower()
    scores = []
    for topic, terms in PUBLIC_TAXONOMY.items():
        score = term_score(text_l, counts, terms)
        if score:
            scores.append((topic, score))
    return sorted(scores, key=lambda item: (-item[1], item[0]))[:4]


def classify_sensitive_domains(text: str, counts: Counter[str]) -> list[str]:
    text_l = text.lower()
    return [reason for reason, terms in SENSITIVE_DOMAIN_TERMS.items() if term_score(text_l, counts, terms)]


def title_sensitive_reasons(title: str) -> list[str]:
    title_l = title.lower()
    reasons = []
    for reason, terms in SENSITIVE_DOMAIN_TERMS.items():
        for term in terms:
            if term.lower() in title_l:
                reasons.append(reason)
                break
    return reasons


def freshness(topics: list[tuple[str, int]], text: str, counts: Counter[str]) -> tuple[str, bool]:
    topic_names = {topic for topic, _ in topics}
    current_terms = [
        "2024",
        "2025",
        "2026",
        "latest",
        "current",
        "today",
        "price",
        "pricing",
        "law",
        "policy",
        "version",
    ]
    needs_check = bool(topic_names & FACT_CHECK_TOPICS) or bool(
        term_score(text.lower(), counts, current_terms)
    )
    return ("needs_current_fact_check", True) if needs_check else ("evergreen_candidate", False)


def score_unit(
    char_count: int, token_count: int, topics: list[tuple[str, int]], top_terms: list[tuple[str, int]]
) -> float:
    score = min(math.log10(max(char_count, 10)) * 18, 72)
    score += min(token_count / 35, 35)
    score += min(sum(value for _, value in topics), 80)
    score += min(len(top_terms), 30)
    return round(score, 2)


def classify(unit: CorpusUnit) -> Classification:
    counts = term_counter(unit.text)
    cleaned_terms = sorted(counts)
    top_terms = counts.most_common(25)
    topics = classify_public_topics(unit.text, counts)
    exclusions = sorted(
        set(classify_sensitive_domains(unit.text, counts) + title_sensitive_reasons(unit.title))
    )
    identifiers = detect_identifiers(unit.text)
    fresh_label, needs_fact_check = freshness(topics, unit.text, counts)
    score = score_unit(len(unit.text), sum(counts.values()), topics, top_terms)

    if identifiers:
        decision = "exclude_private_identifier"
    elif exclusions:
        decision = "exclude_sensitive_domain"
    elif not topics or sum(counts.values()) < 10:
        decision = "skip_low_signal"
    else:
        decision = "public_candidate"

    return Classification(
        unit_id=unit.unit_id,
        source_file=unit.source_file,
        conversation_id=unit.conversation_id,
        title=unit.title,
        unit_type=unit.unit_type,
        chunk_index=unit.chunk_index,
        decision=decision,
        score=score,
        char_count=len(unit.text),
        token_count=sum(counts.values()),
        cleaned_terms=cleaned_terms[:350],
        top_terms=top_terms,
        public_topics=topics,
        exclusion_reasons=exclusions,
        identifier_hits=identifiers,
        freshness=fresh_label,
        needs_fact_check=needs_fact_check,
        preview=compact_preview(unit.text),
    )
