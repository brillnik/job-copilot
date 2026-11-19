import hashlib
import itertools
import math
import re
from functools import lru_cache
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9+#.]+")


class Embedder(Protocol):
    """Swap for a hosted embedding model without touching the profile service.

    Vectors must be unit length (search uses a dot product). `name` identifies the
    vector space: stored vectors from a different name are re-embedded on use.
    `min_score` is the similarity below which a match is noise for this model.
    """

    name: str
    min_score: float

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Dependency-free lexical embedder (hashed unigrams + bigrams, L2-normalised).

    Good enough to wire up and test the pipeline; replace with a semantic model
    in production. Vectors from different embedders are not comparable, so
    re-approve a profile after swapping.
    """

    name = "hashing-512"
    min_score = 0.05

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


@lru_cache(maxsize=1)
def _fastembed_model(model_name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name)


class FastEmbedEmbedder:
    """Local semantic embeddings (ONNX, no API key). Downloads the model on first use.

    BGE models are asymmetric: queries get an instruction prefix, passages do not.
    """

    min_score = 0.5

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self.name = f"fastembed:{model_name}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _fastembed_model(self.model_name)
        return [v.tolist() for v in model.passage_embed(texts)]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _fastembed_model(self.model_name)
        return [v.tolist() for v in model.query_embed(texts)]
