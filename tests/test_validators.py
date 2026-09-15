"""The three full-corpus validators and the majority vote between them.

These pin the behaviour the project page describes: identifiers and sensitive domains
override public usefulness, ambiguity routes to review rather than to a risky binary label,
and the policy classifier maps the pipeline's four decisions onto three validator labels.
"""

import pytest

from conftest import make_unit
from corpus_privacy_intelligence.validators import (
    PRIVATE_LABEL,
    PUBLIC_LABEL,
    REVIEW_LABEL,
    ValidatorDecision,
    all_validator_decisions,
    majority_label,
    policy_classifier,
    semantic_score_classifier,
    strict_detector,
)

VALIDATORS = [policy_classifier, strict_detector, semantic_score_classifier]

TECHNICAL = (
    "Design notes for validating CSV inputs, normalizing timestamps, checking schema drift, "
    "and writing clean aggregate reports from a local pipeline."
)
IDENTIFIER = "My SSN is 123-45-6789 and you can email me at first.last@example.com."
IMMIGRATION = "Walk me through my H-1B stamping appointment and the USCIS petition receipt."


@pytest.mark.parametrize("validator", VALIDATORS, ids=lambda v: v.__name__)
def test_hard_identifier_is_private_for_every_validator(validator):
    assert validator(make_unit(IDENTIFIER)).label == PRIVATE_LABEL


@pytest.mark.parametrize("validator", VALIDATORS, ids=lambda v: v.__name__)
def test_every_validator_returns_a_known_label(validator):
    label = validator(make_unit(TECHNICAL)).label
    assert label in {PUBLIC_LABEL, PRIVATE_LABEL, REVIEW_LABEL}


@pytest.mark.parametrize("validator", VALIDATORS, ids=lambda v: v.__name__)
def test_every_validator_names_itself_and_bounds_confidence(validator):
    decision = validator(make_unit(TECHNICAL))
    assert decision.name
    assert 0.0 <= decision.confidence <= 1.0


@pytest.mark.parametrize("validator", VALIDATORS, ids=lambda v: v.__name__)
def test_private_decisions_carry_reasons(validator):
    """A label without evidence cannot be audited, which is the whole premise."""
    decision = validator(make_unit(IDENTIFIER))
    assert decision.reasons


class TestPolicyClassifier:
    def test_technical_content_is_public(self):
        assert policy_classifier(make_unit(TECHNICAL)).label == PUBLIC_LABEL

    def test_sensitive_domain_overrides_usefulness(self):
        assert policy_classifier(make_unit(IMMIGRATION)).label == PRIVATE_LABEL

    def test_low_signal_text_maps_to_review_not_public(self):
        """policy_classifier maps skip_low_signal to review. The published counts rely on it."""
        assert policy_classifier(make_unit("ok thanks")).label == REVIEW_LABEL


class TestStrictDetector:
    def test_identifier_beats_everything(self):
        assert strict_detector(make_unit(IDENTIFIER)).label == PRIVATE_LABEL

    def test_unknown_text_routes_to_review_rather_than_public(self):
        assert strict_detector(make_unit("A short neutral sentence.")).label == REVIEW_LABEL


class TestSemanticScoreClassifier:
    def test_identifier_beats_everything(self):
        assert semantic_score_classifier(make_unit(IDENTIFIER)).label == PRIVATE_LABEL

    def test_empty_text_is_review(self):
        assert semantic_score_classifier(make_unit("")).label == REVIEW_LABEL


class TestMajorityLabel:
    @staticmethod
    def decision(label):
        return ValidatorDecision("x", label, 0.9, [])

    def test_two_of_three_wins(self):
        labels = [PUBLIC_LABEL, PUBLIC_LABEL, PRIVATE_LABEL]
        assert majority_label([self.decision(x) for x in labels]) == PUBLIC_LABEL

    def test_unanimous_wins(self):
        labels = [PRIVATE_LABEL] * 3
        assert majority_label([self.decision(x) for x in labels]) == PRIVATE_LABEL

    def test_three_way_split_falls_back_to_review(self):
        labels = [PUBLIC_LABEL, PRIVATE_LABEL, REVIEW_LABEL]
        assert majority_label([self.decision(x) for x in labels]) == REVIEW_LABEL


def test_all_validator_decisions_runs_the_published_three():
    decisions = all_validator_decisions(make_unit(TECHNICAL))
    assert [d.name for d in decisions] == [
        "policy_classifier",
        "strict_detector",
        "semantic_score_classifier",
    ]
