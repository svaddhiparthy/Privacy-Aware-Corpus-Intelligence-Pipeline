from __future__ import annotations

import re

PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone": re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    "card_like_number": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "api_secret": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"
    ),
    "identity_document_context": re.compile(
        r"\b(passport|driver'?s license|dl number|license number|a-number|alien number)\b", re.I
    ),
    "street_address_context": re.compile(
        r"\b\d{1,6}\s+[A-Za-z0-9.' -]{2,40}\s+"
        r"(street|st|road|rd|avenue|ave|drive|dr|lane|ln|court|ct|circle|cir|boulevard|blvd)\b",
        re.I,
    ),
}


def detect_identifiers(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]
