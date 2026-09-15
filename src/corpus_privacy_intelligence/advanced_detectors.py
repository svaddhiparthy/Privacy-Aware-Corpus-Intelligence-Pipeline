from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .classifier import classify
from .models import CorpusUnit
from .pii import detect_identifiers
from .text import compact_preview, term_counter
from .validators import PRIVATE_LABEL, PUBLIC_LABEL, REVIEW_LABEL, semantic_score_classifier, strict_detector


@dataclass(frozen=True)
class DetectorResult:
    name: str
    label: str
    confidence: float
    reasons: list[str]
    metadata: dict[str, Any]


def policy_detector(unit: CorpusUnit) -> DetectorResult:
    result = classify(unit)
    if result.decision.startswith("exclude"):
        label = PRIVATE_LABEL
    elif result.decision == "public_candidate":
        label = PUBLIC_LABEL
    else:
        label = REVIEW_LABEL
    return DetectorResult(
        name="policy",
        label=label,
        confidence=min(0.99, max(0.50, result.score / 220)),
        reasons=(
            result.exclusion_reasons
            + result.identifier_hits
            + [topic for topic, _ in result.public_topics[:2]]
        )[:10],
        metadata={"score": result.score, "decision": result.decision},
    )


def strict_rule_detector(unit: CorpusUnit) -> DetectorResult:
    result = strict_detector(unit)
    return DetectorResult(result.name, result.label, result.confidence, result.reasons, {})


def semantic_rule_detector(unit: CorpusUnit) -> DetectorResult:
    result = semantic_score_classifier(unit)
    return DetectorResult(result.name, result.label, result.confidence, result.reasons, {})


class PresidioDetector:
    def __init__(self) -> None:
        self.available = False
        self.error = ""
        self.analyzer = None
        try:
            from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

            self.analyzer = AnalyzerEngine()
            self._add_custom_recognizers(Pattern, PatternRecognizer)
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on optional runtime packages
            self.error = str(exc)

    def _add_custom_recognizers(self, Pattern, PatternRecognizer) -> None:
        custom = [
            PatternRecognizer(
                supported_entity="IMMIGRATION_CONTEXT",
                patterns=[
                    Pattern(
                        name="immigration_terms",
                        regex=r"\b(h-?1b|f-?1|uscis|i-?140|i-?485|perm|ead|green card|stamping|rfe|visa petition)\b",
                        score=0.75,
                    )
                ],
            ),
            PatternRecognizer(
                supported_entity="JOB_SEARCH_CONTEXT",
                patterns=[
                    Pattern(
                        name="job_search_terms",
                        regex=r"\b(resume|cv|linkedin|recruiter|interview|job search|job application|cover letter|salary|job offer|layoff|workday)\b",
                        score=0.72,
                    )
                ],
            ),
            PatternRecognizer(
                supported_entity="PRIVATE_HEALTH_CONTEXT",
                patterns=[
                    Pattern(
                        name="health_terms",
                        regex=r"\b(diagnosis|symptom|prescription|nephrologist|kidney|cancer|calories|supplement|minoxidil|finasteride|medical record)\b",
                        score=0.72,
                    )
                ],
            ),
        ]
        for recognizer in custom:
            self.analyzer.registry.add_recognizer(recognizer)

    def analyze(self, unit: CorpusUnit) -> DetectorResult:
        if not self.available:
            return DetectorResult("presidio", REVIEW_LABEL, 0.0, ["unavailable"], {"error": self.error})
        text = f"{unit.title}\n{unit.text[:18000]}"
        results = self.analyzer.analyze(text=text, language="en")
        entities = Counter(result.entity_type for result in results if result.score >= 0.45)
        hard_private_entities = {
            "PHONE_NUMBER",
            "EMAIL_ADDRESS",
            "CREDIT_CARD",
            "US_SSN",
            "US_DRIVER_LICENSE",
            "US_PASSPORT",
            "IMMIGRATION_CONTEXT",
            "JOB_SEARCH_CONTEXT",
            "PRIVATE_HEALTH_CONTEXT",
        }
        review_entities = {"LOCATION", "PERSON", "DATE_TIME", "NRP"}
        hits = [entity for entity, count in entities.items() if entity in hard_private_entities and count]
        if hits:
            confidence = min(0.98, 0.62 + len(hits) * 0.07)
            return DetectorResult(
                "presidio", PRIVATE_LABEL, confidence, hits[:10], {"entities": dict(entities)}
            )
        review_hits = [
            entity for entity, count in entities.items() if entity in review_entities and count >= 3
        ]
        if review_hits:
            return DetectorResult(
                "presidio", REVIEW_LABEL, 0.55, review_hits[:10], {"entities": dict(entities)}
            )
        if len(term_counter(text)) >= 10:
            return DetectorResult("presidio", PUBLIC_LABEL, 0.58, [], {"entities": dict(entities)})
        return DetectorResult("presidio", REVIEW_LABEL, 0.50, [], {"entities": dict(entities)})


class SpacyDetector:
    def __init__(self) -> None:
        self.available = False
        self.error = ""
        self.nlp = None
        try:
            import spacy

            try:
                self.nlp = spacy.load("en_core_web_sm")
            except Exception:
                self.nlp = spacy.blank("en")
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on optional runtime packages
            self.error = str(exc)

    def analyze(self, unit: CorpusUnit) -> DetectorResult:
        if not self.available:
            return DetectorResult("spacy", REVIEW_LABEL, 0.0, ["unavailable"], {"error": self.error})
        text = f"{unit.title}\n{unit.text[:12000]}"
        doc = self.nlp(text)
        entities = Counter(ent.label_ for ent in doc.ents)
        identifier_hits = detect_identifiers(text)
        sensitive_context = re.findall(
            r"\b(h-?1b|uscis|resume|recruiter|interview|diagnosis|prescription|cancer|nephrologist|salary)\b",
            text,
            flags=re.I,
        )
        if identifier_hits or sensitive_context:
            reasons = identifier_hits + sorted({value.lower() for value in sensitive_context})
            return DetectorResult("spacy", PRIVATE_LABEL, 0.78, reasons[:10], {"entities": dict(entities)})
        if sum(entities.values()) >= 12:
            return DetectorResult(
                "spacy", REVIEW_LABEL, 0.55, ["many_entities"], {"entities": dict(entities)}
            )
        return DetectorResult("spacy", PUBLIC_LABEL, 0.58, [], {"entities": dict(entities)})


def make_advanced_detectors() -> list[Any]:
    return [
        policy_detector,
        strict_rule_detector,
        semantic_rule_detector,
        PresidioDetector().analyze,
        SpacyDetector().analyze,
    ]


def preview_for_report(unit: CorpusUnit) -> str:
    return compact_preview(re.sub(r"\b(USER|ASSISTANT|TOOL|SYSTEM):\s*", "", unit.text), 420)
