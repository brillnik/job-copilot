"""Runs the real local model; skipped when it cannot be loaded (e.g. offline)."""

import pytest

from app.ai.embeddings import FastEmbedEmbedder

DOCS = [
    "Built Kafka pipelines processing 2M events/day",
    "Led migration of Postgres to Aurora",
    "Mentored four junior engineers",
]


@pytest.fixture(scope="module")
def emb():
    e = FastEmbedEmbedder()
    try:
        e.embed_documents(["warmup"])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"model unavailable: {exc}")
    return e


@pytest.mark.parametrize(
    "query,expected",
    [("event streaming", 0), ("database migration", 1), ("people management", 2)],
)
def test_semantic_match_without_shared_keywords(emb, query, expected):
    docs = emb.embed_documents(DOCS)
    (q,) = emb.embed_queries([query])
    scores = [sum(a * b for a, b in zip(q, d)) for d in docs]
    assert scores.index(max(scores)) == expected
