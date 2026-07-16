# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Embedder for ingest application."""

from __future__ import annotations

import hashlib
import math
import re

from sentence_transformers import SentenceTransformer

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class HashEmbedder:
    """Embedder using hash function."""

    def __init__(self, dimension: int) -> None:
        """Initialize the embedder."""
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        """Embed a single text."""
        vector = [0.0] * self.dimension
        tokens = TOKEN_PATTERN.findall(text.lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = (
                int.from_bytes(digest[:4], byteorder="big") % self.dimension
            )
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) / 12.0
            vector[bucket] += sign * weight

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class SentenceTransformerEmbedder:
    """Real dense embeddings via sentence-transformers (BAAI/bge-small-en-v1.5, dim=384).

    Compatible with the WIG MilvusRetriever which uses the same model,
    so COSINE similarity search returns meaningful semantic results.
    """

    MODEL_NAME = "BAAI/bge-small-en-v1.5"

    def __init__(self, dimension: int) -> None:
        """Initialize the embedder."""
        self.dimension = dimension
        self._model = SentenceTransformer(self.MODEL_NAME)
        actual = self._model.get_sentence_embedding_dimension()
        if actual != dimension:
            raise ValueError(
                f"{self.MODEL_NAME} produces {actual}-dim embeddings but "
                f"MILVUS_DIMENSION={dimension}. Set the dimension to {actual} "
                "so Milvus inserts don't fail at write time."
            )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""
        return self._model.encode(texts, normalize_embeddings=True).tolist()


def build_embedder(
    provider: str, dimension: int
) -> HashEmbedder | SentenceTransformerEmbedder:
    """Build an embedder."""
    p = provider.strip().lower()
    if p == "hash":
        return HashEmbedder(dimension=dimension)
    if p in ("sentence_transformers", "sentence-transformers", "bge"):
        return SentenceTransformerEmbedder(dimension=dimension)
    raise ValueError(
        f"Unsupported embedding provider '{provider}'. Use 'hash' or 'sentence_transformers'."
    )
