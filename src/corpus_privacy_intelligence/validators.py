from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .classifier import classify
from .models import CorpusUnit
from .pii import detect_identifiers
from .text import normalize_token, term_counter


@dataclass(frozen=True)
class ValidatorDecision:
    name: str
    label: str
    confidence: float
    reasons: list[str]


PRIVATE_LABEL = "private"
PUBLIC_LABEL = "public"
REVIEW_LABEL = "review"


STRICT_PRIVATE_PATTERNS = {
    "immigration": re.compile(
        r"\b(h-?1b|f-?1|visa|uscis|i-?140|i-?485|perm|ead|green card|stamping|rfe|petition)\b",
        re.I,
    ),
    "job_search": re.compile(
        r"\b(resume|cv|linkedin|recruiter|interview|job search|job application|cover letter|salary|job offer|layoff|workday|employer|hiring)\b",
        re.I,
    ),
    "health": re.compile(
        r"\b(health|medical|doctor|diagnosis|symptom|prescription|kidney|nephrologist|calorie|calories|supplement|sleep|weight|blood|pain|injury|cancer|disease|omega-?3|retinol|aga|minoxidil|finasteride)\b",
        re.I,
    ),
}

PUBLIC_CONTEXT_PATTERNS = {
    "technical": re.compile(
        r"\b(api|python|sql|docker|server|pipeline|automation|github|database|query|json|xml|code|deploy)\b",
        re.I,
    ),
    "product": re.compile(
        r"\b(compare|comparison|review|buying guide|product|device|price|option|recommendation)\b", re.I
    ),
    "creative": re.compile(r"\b(story|culture|creative|movie|game|design|article|blog|publish)\b", re.I),
    "infrastructure": re.compile(r"\b(router|network|nas|vps|firewall|backup|dns|domain|container)\b", re.I),
}

SEMANTIC_PRIVATE_TERMS = {
    "immigration": {
        "visa",
        "uscis",
        "petition",
        "stamping",
        "perm",
        "ead",
        "greencard",
        "lawyer",
        "attorney",
        "rfe",
        "i140",
        "i485",
        "f1",
        "h1b",
    },
    "job_search": {
        "resume",
        "linkedin",
        "recruiter",
        "interview",
        "salary",
        "layoff",
        "employer",
        "hiring",
        "workday",
        "indeed",
    },
    "health": {
        "health",
        "doctor",
        "medical",
        "diagnosis",
        "symptom",
        "medicine",
        "prescription",
        "kidney",
        "blood",
        "pain",
        "injury",
        "sleep",
        "weight",
        "calorie",
        "supplement",
        "minoxidil",
        "finasteride",
        "cancer",
        "disease",
        "retinol",
        "omega",
    },
}

SEMANTIC_PUBLIC_TERMS = {
    "technical": {
        "python",
        "sql",
        "docker",
        "api",
        "database",
        "server",
        "pipeline",
        "automation",
        "github",
        "query",
        "json",
        "code",
        "deploy",
        "script",
    },
    "product": {
        "compare",
        "comparison",
        "review",
        "product",
        "device",
        "buy",
        "price",
        "pricing",
        "option",
        "recommend",
        "value",
    },
    "general_explainer": {
        "explain",
        "guide",
        "tutorial",
        "overview",
        "learn",
        "concept",
        "framework",
        "strategy",
        "theory",
    },
}


def policy_classifier(unit: CorpusUnit) -> ValidatorDecision:
    result = classify(unit)
    if result.decision.startswith("exclude"):
        label = PRIVATE_LABEL
    elif result.decision == "public_candidate":
        label = PUBLIC_LABEL
    else:
        label = REVIEW_LABEL
    reasons = result.exclusion_reasons + result.identifier_hits
    if result.public_topics:
        reasons.extend(topic for topic, _ in result.public_topics[:2])
    confidence = min(0.99, max(0.50, result.score / 220))
    return ValidatorDecision("policy_classifier", label, confidence, reasons[:8])


def strict_detector(unit: CorpusUnit) -> ValidatorDecision:
    text = f"{unit.title}\n{unit.text}"
    identifier_hits = detect_identifiers(text)
    private_hits = [name for name, pattern in STRICT_PRIVATE_PATTERNS.items() if pattern.search(text)]
    public_hits = [name for name, pattern in PUBLIC_CONTEXT_PATTERNS.items() if pattern.search(text)]

    if identifier_hits:
        return ValidatorDecision("strict_detector", PRIVATE_LABEL, 0.98, identifier_hits)
    if len(private_hits) >= 2:
        return ValidatorDecision("strict_detector", PRIVATE_LABEL, 0.92, private_hits)
    if len(private_hits) == 1:
        return ValidatorDecision("strict_detector", PRIVATE_LABEL, 0.82, private_hits)
    if public_hits:
        return ValidatorDecision("strict_detector", PUBLIC_LABEL, 0.76, public_hits)
    return ValidatorDecision("strict_detector", REVIEW_LABEL, 0.50, [])


def semantic_score_classifier(unit: CorpusUnit) -> ValidatorDecision:
    text = f"{unit.title}\n{unit.text}"
    identifier_hits = detect_identifiers(text)
    if identifier_hits:
        return ValidatorDecision("semantic_score_classifier", PRIVATE_LABEL, 0.97, identifier_hits)

    phrase_private_hits = [name for name, pattern in STRICT_PRIVATE_PATTERNS.items() if pattern.search(text)]
    counts = term_counter(text)
    private_scores = {
        name: sum(counts.get(normalize_token(term), 0) for term in terms)
        for name, terms in SEMANTIC_PRIVATE_TERMS.items()
    }
    public_scores = {
        name: sum(counts.get(normalize_token(term), 0) for term in terms)
        for name, terms in SEMANTIC_PUBLIC_TERMS.items()
    }
    private_total = sum(private_scores.values())
    public_total = sum(public_scores.values())
    top_private = [name for name, value in private_scores.items() if value]
    top_public = [name for name, value in public_scores.items() if value]

    if phrase_private_hits:
        confidence = 0.86 if public_total else 0.92
        return ValidatorDecision("semantic_score_classifier", PRIVATE_LABEL, confidence, phrase_private_hits)
    if private_total >= 3 and private_total >= public_total * 0.25:
        confidence = min(0.95, 0.60 + private_total / max(private_total + public_total, 1) * 0.35)
        return ValidatorDecision("semantic_score_classifier", PRIVATE_LABEL, confidence, top_private)
    if public_total >= 5 and private_total <= 2:
        confidence = min(0.90, 0.55 + public_total / max(private_total + public_total, 1) * 0.30)
        return ValidatorDecision("semantic_score_classifier", PUBLIC_LABEL, confidence, top_public)
    if private_total > public_total:
        return ValidatorDecision("semantic_score_classifier", REVIEW_LABEL, 0.62, top_private + top_public)
    if public_total:
        return ValidatorDecision("semantic_score_classifier", PUBLIC_LABEL, 0.64, top_public)
    return ValidatorDecision("semantic_score_classifier", REVIEW_LABEL, 0.50, [])


def all_validator_decisions(unit: CorpusUnit) -> list[ValidatorDecision]:
    return [
        policy_classifier(unit),
        strict_detector(unit),
        semantic_score_classifier(unit),
    ]


def majority_label(decisions: list[ValidatorDecision]) -> str:
    counts = Counter(decision.label for decision in decisions)
    label, count = counts.most_common(1)[0]
    if count >= 2:
        return label
    return REVIEW_LABEL
