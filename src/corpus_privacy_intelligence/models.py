from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusUnit:
    unit_id: str
    source_file: str
    conversation_id: str
    title: str
    unit_type: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class Classification:
    unit_id: str
    source_file: str
    conversation_id: str
    title: str
    unit_type: str
    chunk_index: int
    decision: str
    score: float
    char_count: int
    token_count: int
    cleaned_terms: list[str]
    top_terms: list[tuple[str, int]]
    public_topics: list[tuple[str, int]]
    exclusion_reasons: list[str]
    identifier_hits: list[str]
    freshness: str
    needs_fact_check: bool
    preview: str
