"""The weighted ensemble router.

This is the function the project page calls the Ensemble Router, and it had no test. The
routing rule it encodes is the product decision: a strong private signal wins outright, a
public verdict needs a clear margin, and anything else becomes review rather than a guess.
"""

from corpus_privacy_intelligence.advanced_detectors import DetectorResult
from corpus_privacy_intelligence.advanced_validation import weighted_ensemble
from corpus_privacy_intelligence.validators import PRIVATE_LABEL, PUBLIC_LABEL, REVIEW_LABEL


def result(name: str, label: str, confidence: float = 0.9) -> DetectorResult:
    return DetectorResult(name, label, confidence, [], {})


class TestPrivateWins:
    def test_presidio_alone_can_carry_private(self):
        """Presidio has the highest weight because it is purpose-built for PII."""
        label, _ = weighted_ensemble([result("presidio", PRIVATE_LABEL, 0.99)])
        assert label == PRIVATE_LABEL

    def test_unanimous_private_is_private(self):
        detectors = [
            result("policy", PRIVATE_LABEL),
            result("strict_detector", PRIVATE_LABEL),
            result("semantic_score_classifier", PRIVATE_LABEL),
        ]
        assert weighted_ensemble(detectors)[0] == PRIVATE_LABEL

    def test_private_beats_a_public_majority(self):
        """Privacy overrides usefulness, even when more detectors say public."""
        detectors = [
            result("presidio", PRIVATE_LABEL, 0.99),
            result("policy", PRIVATE_LABEL, 0.95),
            result("spacy", PUBLIC_LABEL, 0.60),
            result("semantic_score_classifier", PUBLIC_LABEL, 0.60),
        ]
        assert weighted_ensemble(detectors)[0] == PRIVATE_LABEL


class TestPublicNeedsAMargin:
    def test_unanimous_confident_public_is_public(self):
        detectors = [
            result("policy", PUBLIC_LABEL, 0.95),
            result("strict_detector", PUBLIC_LABEL, 0.90),
            result("semantic_score_classifier", PUBLIC_LABEL, 0.90),
        ]
        assert weighted_ensemble(detectors)[0] == PUBLIC_LABEL

    def test_one_weak_public_vote_is_not_enough(self):
        assert weighted_ensemble([result("spacy", PUBLIC_LABEL, 0.50)])[0] != PUBLIC_LABEL


class TestAmbiguityBecomesReview:
    def test_no_signal_is_review(self):
        assert weighted_ensemble([])[0] == REVIEW_LABEL

    def test_split_opinion_is_review(self):
        detectors = [
            result("policy", PUBLIC_LABEL, 0.60),
            result("spacy", REVIEW_LABEL, 0.55),
            result("presidio", REVIEW_LABEL, 0.55),
        ]
        assert weighted_ensemble(detectors)[0] == REVIEW_LABEL

    def test_zero_confidence_detectors_do_not_vote(self):
        """A detector that could not run must not tilt the route."""
        with_silent = weighted_ensemble(
            [result("policy", PUBLIC_LABEL, 0.95), result("presidio", PRIVATE_LABEL, 0.0)]
        )
        without = weighted_ensemble([result("policy", PUBLIC_LABEL, 0.95)])
        assert with_silent == without


class TestContract:
    def test_returns_a_known_label_and_a_bounded_confidence(self):
        label, confidence = weighted_ensemble([result("policy", PUBLIC_LABEL, 0.9)])
        assert label in {PUBLIC_LABEL, PRIVATE_LABEL, REVIEW_LABEL}
        assert 0.0 <= confidence <= 1.0

    def test_is_deterministic(self):
        detectors = [result("policy", PUBLIC_LABEL, 0.9), result("spacy", REVIEW_LABEL, 0.6)]
        assert weighted_ensemble(detectors) == weighted_ensemble(detectors)
