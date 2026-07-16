# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Milvus store for ingest application."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from .models import ChunkRecord

logger = logging.getLogger(__name__)


def _milvus_quote(value: str) -> str:
    """Escape a value for safe interpolation inside a Milvus filter expression."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


class MilvusStore:
    """Milvus store for ingest application."""

    def __init__(
        self,
        host: str,
        port: str,
        collection_name: str,
        dimension: int,
        connect_timeout_seconds: float,
        connect_interval_seconds: float,
    ) -> None:
        """Initialize the Milvus store."""
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.dimension = dimension
        self.connect_timeout_seconds = connect_timeout_seconds
        self.connect_interval_seconds = connect_interval_seconds
        self.alias = "default"

    def connect(self) -> None:
        """Connect to the Milvus store."""
        deadline = time.time() + self.connect_timeout_seconds
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                connections.connect(
                    alias=self.alias, host=self.host, port=self.port
                )
                utility.list_collections(using=self.alias)
                return
            except Exception as exc:
                last_error = exc
                logger.info(
                    "Waiting for Milvus at %s:%s: %s",
                    self.host,
                    self.port,
                    exc,
                )
                time.sleep(self.connect_interval_seconds)

        raise TimeoutError(
            f"Failed to connect to Milvus at {self.host}:{self.port}"
        ) from last_error

    def reset_collection(self, collection_name: str | None = None) -> None:
        """Reset the collection."""
        name = collection_name or self.collection_name
        if utility.has_collection(name, using=self.alias):
            utility.drop_collection(name, using=self.alias)

    def ensure_collection(
        self, collection_name: str | None = None
    ) -> Collection:
        """Ensure the collection exists."""
        name = collection_name or self.collection_name
        if utility.has_collection(name, using=self.alias):
            collection = Collection(name, using=self.alias)
            if not self._supports_rich_schema(collection):
                raise ValueError(
                    f"Collection '{name}' uses an outdated schema. "
                    "Re-ingest with reset_collection=true."
                )
            self._ensure_index(collection)
            return collection

        schema = CollectionSchema(
            fields=[
                FieldSchema(
                    name="chunk_id",
                    dtype=DataType.VARCHAR,
                    max_length=128,
                    is_primary=True,
                    auto_id=False,
                ),
                FieldSchema(
                    name="source_doc_id", dtype=DataType.VARCHAR, max_length=128
                ),
                FieldSchema(
                    name="document_name", dtype=DataType.VARCHAR, max_length=256
                ),
                FieldSchema(
                    name="title", dtype=DataType.VARCHAR, max_length=512
                ),
                FieldSchema(
                    name="vendor", dtype=DataType.VARCHAR, max_length=128
                ),
                FieldSchema(
                    name="machine_id", dtype=DataType.VARCHAR, max_length=128
                ),
                FieldSchema(
                    name="document_type", dtype=DataType.VARCHAR, max_length=128
                ),
                FieldSchema(
                    name="version", dtype=DataType.VARCHAR, max_length=64
                ),
                FieldSchema(
                    name="source_language",
                    dtype=DataType.VARCHAR,
                    max_length=16,
                ),
                FieldSchema(
                    name="translated_language",
                    dtype=DataType.VARCHAR,
                    max_length=16,
                ),
                FieldSchema(
                    name="translation_provider",
                    dtype=DataType.VARCHAR,
                    max_length=32,
                ),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(
                    name="element_type", dtype=DataType.VARCHAR, max_length=32
                ),
                FieldSchema(name="page_number", dtype=DataType.INT64),
                FieldSchema(
                    name="source_anchor", dtype=DataType.VARCHAR, max_length=256
                ),
                FieldSchema(
                    name="content_original",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="content_english",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.dimension,
                ),
            ],
            description="EV assembly documents translated to English and chunked for retrieval.",
        )
        collection = Collection(name, schema=schema, using=self.alias)
        self._ensure_index(collection)
        return collection

    def upsert_chunks(
        self,
        collection: Collection,
        chunks: list[ChunkRecord],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert chunks into the collection."""
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts do not match.")

        collection.load()
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if chunk_ids:
            # Escape each id — chunk_id embeds user-controlled doc_id, so a raw
            # quote/backslash could break out of the delete expression.
            quoted = ", ".join(f'"{_milvus_quote(cid)}"' for cid in chunk_ids)
            collection.delete(expr=f"chunk_id in [{quoted}]")

        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            row = asdict(chunk)
            row["embedding"] = embedding
            rows.append(row)

        collection.insert(rows)
        collection.flush()

    def search(
        self,
        collection: Collection,
        query_vector: list[float],
        machine_id: str | None = None,
        document_type: str | None = None,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
    ) -> list[dict]:
        """Similarity search over a collection.

        Returns chunk dicts sorted by score descending, filtered to
        those above similarity_threshold.
        """
        output_fields = [
            "chunk_id",
            "source_doc_id",
            "document_name",
            "title",
            "vendor",
            "machine_id",
            "document_type",
            "version",
            "element_type",
            "page_number",
            "source_anchor",
            "content_original",
            "content_english",
        ]
        expr_parts: list[str] = []
        if machine_id:
            expr_parts.append(f'machine_id == "{_milvus_quote(machine_id)}"')
        if document_type:
            expr_parts.append(
                f'document_type == "{_milvus_quote(document_type)}"'
            )
        expr = " && ".join(expr_parts) if expr_parts else None

        # ponytail: load() is idempotent; never release() per-request — a
        # concurrent request's release could unload the collection mid-search.
        collection.load()
        hits = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            expr=expr,
            output_fields=output_fields,
        )

        results: list[dict] = []
        for hit in hits[0]:
            if hit.score < similarity_threshold:
                continue
            entity = {field: hit.entity.get(field) for field in output_fields}
            entity["score"] = hit.score
            results.append(entity)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _ensure_index(self, collection: Collection) -> None:
        """Ensure the index exists."""
        if "embedding" in {index.field_name for index in collection.indexes}:
            return
        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": 128},
            },
        )

    def _supports_rich_schema(self, collection: Collection) -> bool:
        """Check if the collection supports a rich schema."""
        names = {field.name for field in collection.schema.fields}
        required = {
            "element_type",
            "page_number",
            "source_anchor",
            "document_name",
        }
        return required.issubset(names)
