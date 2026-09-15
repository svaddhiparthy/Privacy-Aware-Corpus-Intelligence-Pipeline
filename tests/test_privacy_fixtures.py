"""Synthetic privacy fixtures: the regression gate.

The project's own roadmap named this as the right control, so it is built rather than listed.
Every fixture is invented. If a policy or taxonomy edit ever lets a private fixture through to
public output, or starts excluding the legitimate public near-misses, this fails the build.

The near-miss cases matter as much as the leaks: broad terms like finance, health, technology
and immigration must not become blanket filters on educational content.
"""

import pytest

from conftest import make_unit
from corpus_privacy_intelligence.classifier import classify

MUST_NEVER_BE_PUBLIC = [
    ("ssn", "My SSN is 123-45-6789, keep it somewhere safe."),
    ("email", "You can reach me directly at first.last@example.com any time."),
    ("phone", "My mobile is 555-867-5309 if the booking changes."),
    ("card", "Use card 4111 1111 1111 1111 for the subscription."),
    ("api_key", "The key is sk-abcdefghijklmnopqrstuvwxyz123456, do not share it."),
    ("passport", "I need to renew my passport before the trip next month."),
    ("address", "Deliver it to 1600 Pennsylvania Avenue on Tuesday."),
    ("immigration", "Help me prepare for my H-1B stamping interview and the USCIS petition."),
    ("health", "My nephrologist changed my prescription after the kidney diagnosis."),
    ("job_search", "Review my resume and cover letter before I send it to the recruiter."),
]

MUST_STAY_AVAILABLE = [
    (
        "data_engineering",
        "Design notes for validating CSV inputs, normalizing timestamps, checking schema "
        "drift, and writing clean aggregate reports from a local batch pipeline.",
    ),
    (
        "finance_explainer",
        "How does compound interest actually work, and why does the compounding period "
        "change the effective annual rate on a savings account?",
    ),
    (
        "infrastructure",
        "Comparing mini PC options for a home lab running Docker containers, with notes on "
        "power draw, thermals, and network throughput under sustained load.",
    ),
]

# Engineering vocabulary that overlaps the health taxonomy. Bare tokens "health", "lab",
# "sleep", "weight" and "pain" used to exclude every one of these, which silently cost real
# public candidates in a corpus full of infrastructure and machine-learning material.
ENGINEERING_HOMONYMS = [
    ("home_lab", "Comparing mini PC options for a home lab running Docker containers."),
    ("sleep_mode", "Configure the server to enter sleep mode after idle timeout and wake on LAN."),
    ("weight_matrix", "How do you initialise the weight matrix in a neural network layer?"),
    ("pain_point", "The biggest pain point in this API is inconsistent pagination."),
    ("health_check", "Add a container health check endpoint so the orchestrator can restart it."),
]

# The same words in an actual health context must still be excluded.
GENUINE_HEALTH = [
    ("diagnosis", "My nephrologist changed my prescription after the kidney diagnosis."),
    ("lab_results", "My lab results came back and the creatinine number went up again."),
    ("weight_loss", "Tracking my weight loss and calories after the doctor visit."),
    ("sleep_apnea", "Discussing my sleep apnea study and the prescription that followed."),
    ("mental_health", "Notes from my mental health appointment and the medication change."),
    ("chronic_pain", "Managing chronic pain after the injury and what the doctor advised."),
]


@pytest.mark.parametrize("name,text", MUST_NEVER_BE_PUBLIC, ids=[n for n, _ in MUST_NEVER_BE_PUBLIC])
def test_private_fixture_never_reaches_public_output(name, text):
    decision = classify(make_unit(text)).decision
    assert decision != "public_candidate", f"{name} leaked to public output"


@pytest.mark.parametrize("name,text", MUST_NEVER_BE_PUBLIC, ids=[n for n, _ in MUST_NEVER_BE_PUBLIC])
def test_private_fixture_records_why(name, text):
    """An exclusion with no reason cannot be reviewed or calibrated later."""
    result = classify(make_unit(text))
    assert result.identifier_hits or result.exclusion_reasons


@pytest.mark.parametrize("name,text", MUST_STAY_AVAILABLE, ids=[n for n, _ in MUST_STAY_AVAILABLE])
def test_public_near_miss_is_not_excluded(name, text):
    """Broad vocabulary must not become a blanket filter on educational content."""
    decision = classify(make_unit(text)).decision
    assert not decision.startswith("exclude"), f"{name} was excluded as a false positive"


def test_curated_output_never_carries_the_raw_identifier():
    """The classification of a private unit must not itself republish the identifier."""
    secret = "123-45-6789"
    result = classify(make_unit(f"My SSN is {secret} and I need help with a form."))
    assert secret not in " ".join(result.identifier_hits)
    assert secret not in " ".join(result.exclusion_reasons)
    assert secret not in " ".join(result.cleaned_terms)


@pytest.mark.parametrize("name,text", ENGINEERING_HOMONYMS, ids=[n for n, _ in ENGINEERING_HOMONYMS])
def test_engineering_vocabulary_is_not_read_as_health(name, text):
    """Regression guard for the bare-token calibration defect."""
    result = classify(make_unit(text))
    assert "private_health" not in result.exclusion_reasons, f"{name} was excluded as private health"


@pytest.mark.parametrize("name,text", GENUINE_HEALTH, ids=[n for n, _ in GENUINE_HEALTH])
def test_real_health_context_is_still_excluded(name, text):
    """Calibrating the homonyms must not blunt genuine health detection."""
    result = classify(make_unit(text))
    assert result.decision.startswith("exclude"), f"{name} leaked"
    assert "private_health" in result.exclusion_reasons
