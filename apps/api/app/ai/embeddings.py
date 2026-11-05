import hashlib
import itertools
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9+#.]+")


class Embedder(Protocol):
    """Swap for a hosted embedding model without touching the profile service."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Dependency-free lexical embedder (hashed unigrams + bigrams, L2-normalised).

    Good enough to wire up and test the pipeline; replace with a semantic model
    in production. Vectors from different embedders are not comparable, so
    re-approve a profile after swapping.
    """

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        tokens = _TOKEN.findall(text.lower())
        grams = tokens + [f"{a} {b}" for a, b in itertools.pairwise(tokens)]
        vec = [0.0] * self.dim
        for gram in grams:
            h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest())
            vec[h % self.dim] += 1.0 if h >> 63 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]
