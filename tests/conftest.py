"""Shared fixtures.

Every example here is synthetic. No text from the real corpus appears in this repository.
"""

from corpus_privacy_intelligence.models import CorpusUnit


def make_unit(text: str, title: str = "Sample", unit_id: str = "u1") -> CorpusUnit:
    return CorpusUnit(
        unit_id=unit_id,
        source_file="conversations-000.json",
        conversation_id="c1",
        title=title,
        unit_type="conversation",
        chunk_index=0,
        text=text,
    )
