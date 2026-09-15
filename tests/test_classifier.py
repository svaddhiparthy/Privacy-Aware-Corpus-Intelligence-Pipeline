from corpus_privacy_intelligence.classifier import classify
from corpus_privacy_intelligence.models import CorpusUnit


def unit(text: str) -> CorpusUnit:
    return CorpusUnit(
        unit_id="u1",
        source_file="conversations-000.json",
        conversation_id="c1",
        title="Sample",
        unit_type="conversation",
        chunk_index=0,
        text=text,
    )


def test_excludes_ssn_like_identifier():
    result = classify(unit("My SSN is 123-45-6789. Please remember it."))

    assert result.decision == "exclude_private_identifier"
    assert "ssn" in result.identifier_hits


def test_excludes_immigration_context():
    result = classify(unit("Discuss my H-1B visa stamping plan and USCIS petition details."))

    assert result.decision == "exclude_sensitive_domain"
    assert "immigration_private" in result.exclusion_reasons


def test_keeps_general_technical_content():
    text = """
    Build a Python ETL pipeline with Docker, JSON parsing, SQL storage,
    API ingestion, retry logic, deployment notes, and monitoring.
    """
    result = classify(unit(text))

    assert result.decision == "public_candidate"
    assert result.public_topics


def test_keeps_general_finance_explainer_without_private_identifier():
    text = """
    Compare credit card cashback structures, annual fees, travel points,
    insurance benefits, and redemption value for a general buying guide.
    """
    result = classify(unit(text))

    assert result.decision == "public_candidate"
    assert result.identifier_hits == []
