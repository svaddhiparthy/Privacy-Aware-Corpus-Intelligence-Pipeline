from __future__ import annotations

import re
from collections import Counter

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "for",
    "from",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "him",
    "his",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "ours",
    "please",
    "she",
    "should",
    "so",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "too",
    "us",
    "use",
    "used",
    "using",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "chatgpt",
    "gpt",
    "help",
    "need",
    "want",
    "make",
    "create",
    "give",
    "tell",
    "also",
    "like",
    "one",
    "two",
    "new",
    "old",
    "get",
    "got",
    "thing",
    "things",
    "good",
    "bad",
    "best",
    "better",
}


def normalize_token(token: str) -> str:
    token = token.lower().strip("'._-")
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-']{1,}|[A-Za-z]", text)
    normalized = []
    for token in raw_tokens:
        value = normalize_token(token)
        if len(value) < 3 or value in STOPWORDS or value.isdigit():
            continue
        normalized.append(value)
    return normalized


def term_counter(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def compact_preview(text: str, limit: int = 360) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]
