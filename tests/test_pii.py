"""Direct identifier detection, one case per category.

Every example is synthetic. The point of these tests is that a policy edit cannot quietly
stop detecting a whole identifier class, which is the failure mode that would leak the
corpus.
"""

import pytest

from corpus_privacy_intelligence.pii import PATTERNS, detect_identifiers

POSITIVES = [
    ("ssn", "My SSN is 123-45-6789 for the form."),
    ("email", "Reach me at first.last@example.com about it."),
    ("phone", "Call 555-867-5309 when you land."),
    ("card_like_number", "The card number is 4111 1111 1111 1111."),
    ("api_secret", "token sk-abcdefghijklmnopqrstuvwxyz123456"),
    ("identity_document_context", "I need to renew my passport before travel."),
    ("street_address_context", "Ship it to 1600 Pennsylvania Avenue please."),
]


@pytest.mark.parametrize("category,text", POSITIVES)
def test_each_identifier_category_is_detected(category, text):
    assert category in detect_identifiers(text)


def test_every_declared_pattern_has_a_positive_test():
    """A new pattern without a test would be an untested privacy control."""
    covered = {category for category, _ in POSITIVES}
    assert covered == set(PATTERNS), f"untested patterns: {set(PATTERNS) - covered}"


@pytest.mark.parametrize(
    "text",
    [
        "Design notes for validating CSV inputs and normalizing timestamps.",
        "Comparing two laptop models for a home lab build.",
        "How does a database index actually speed up a lookup?",
        "",
    ],
)
def test_clean_technical_text_has_no_identifiers(text):
    assert detect_identifiers(text) == []


def test_detects_multiple_categories_at_once():
    found = detect_identifiers("Email me at a@b.com or call 555-867-5309.")
    assert "email" in found
    assert "phone" in found


def test_version_numbers_are_not_mistaken_for_identifiers():
    """A regression guard: release notes should not read as card numbers."""
    assert detect_identifiers("Upgrade from 1.2.3 to 1.2.4 today.") == []
