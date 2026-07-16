# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MilvusRetriever — embed queries and search ingested EV assembly documents."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from pymilvus import connections, utility
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _milvus_quote(value: str) -> str:
    """Escape a value for safe interpolation inside a Milvus filter expression."""
    return value.replace("\\", "\\\\").replace('"', '\\"')

_COLLECTIONS = ["machine_manuals", "procedure_docs", "sop_docs"]
_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
_DIM = 384
_OUTPUT_FIELDS = [
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
    "content_english",
]


class MilvusRetriever:
    """Milvus retriever for ingest application."""

    def __init__(
        self, host: Optional[str] = None, port: Optional[str] = None
    ) -> None:
        """Initialize the Milvus retriever."""
        url = os.environ.get("MILVUS_URL", "http://milvus-standalone:19530")
        stripped = url.replace("http://", "").replace("https://", "")
        parts = stripped.split(":")
        self._host = host or (parts[0] if parts else "milvus-standalone")
        self._port = port or (parts[1] if len(parts) > 1 else "19530")
        self._alias = "api_retriever"
        self._connected = False
        self._encoder = None

    def search(
        self,
        query: str,
        machine_id: Optional[str] = None,
        document_type: Optional[str] = None,
        collections: Optional[list[str]] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Search the Milvus retriever."""
        try:
            self._connect()
        except Exception as exc:
            logger.warning("MilvusRetriever unavailable (%s)", exc)
            return []
        try:
            query_vector = self._embed(query)
        except Exception as exc:
            logger.warning("MilvusRetriever embedding failed (%s)", exc)
            return []

        from pymilvus import Collection, utility

        results: list[dict[str, Any]] = []
        for coll_name in collections or _COLLECTIONS:
            try:
                if not utility.has_collection(coll_name, using=self._alias):
                    continue
                coll = Collection(coll_name, using=self._alias)
                coll.load()
                expr_parts: list[str] = []
                if machine_id:
                    expr_parts.append(
                        f'machine_id == "{_milvus_quote(machine_id)}"'
                    )
                if document_type:
                    expr_parts.append(
                        f'document_type == "{_milvus_quote(document_type)}"'
                    )
                hits = coll.search(
                    data=[query_vector],
                    anns_field="embedding",
                    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=top_k,
                    expr=" && ".join(expr_parts) if expr_parts else None,
                    output_fields=_OUTPUT_FIELDS,
                )
                for hit in hits[0]:
                    if hit.score < similarity_threshold:
                        continue
                    entity = {f: hit.entity.get(f) for f in _OUTPUT_FIELDS}
                    entity["score"] = float(hit.score)
                    entity["collection"] = coll_name
                    results.append(entity)
            except Exception as exc:
                logger.warning("Search on '%s' failed: %s", coll_name, exc)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _connect(self) -> None:
        """Connect to the Milvus retriever."""
        if self._connected:
            return

        connections.connect(alias=self._alias, host=self._host, port=self._port)
        utility.list_collections(using=self._alias)
        self._connected = True

    def _embed(self, text: str) -> list[float]:
        """Embed a text."""
        if self._encoder is None:

            self._encoder = SentenceTransformer(_EMBEDDING_MODEL)
        return self._encoder.encode(text, normalize_embeddings=True).tolist()
