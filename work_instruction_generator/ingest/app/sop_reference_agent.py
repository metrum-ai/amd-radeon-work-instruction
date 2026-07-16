# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""SOP reference agent for ingest application.

For each procedure/machine combo, runs three targeted searches:
  1. procedure_docs  — filtered by machine_id  (procedure steps, interlocks)
  2. machine_manuals — filtered by machine_id  (OEM specs, calibration, warnings)
  3. sop_docs        — NO machine_id filter     (plantwide LOTO, PPE, HV safety)

Returns all three collections separately plus cross collection classified fields
(safety_warnings, loto_rules, approved_terminology) ready for prompt injection.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from .rag.milvus_retriever import MilvusRetriever

logger = logging.getLogger(__name__)

_RETRIEVER = None
_RETRIEVER_LOCK = threading.Lock()


def _get_retriever():
    """Get the retriever (thread-safe, lazily constructed once)."""
    global _RETRIEVER
    if _RETRIEVER is None:
        with _RETRIEVER_LOCK:
            if _RETRIEVER is None:
                _RETRIEVER = MilvusRetriever()
    return _RETRIEVER


class SOPReferenceAgent:
    """SOP reference agent for ingest application."""

    def __init__(self, retriever=None) -> None:
        """Initialize the SOP reference agent."""
        self._retriever = retriever or _get_retriever()

    def retrieve_context(
        self,
        query: str,
        machine_id: Optional[str] = None,
        oem_machine_id: Optional[str] = None,
        procedure_id: Optional[str] = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Run three targeted searches and return a unified context dict.

        - procedure_docs: filtered by machine_id — procedure-specific steps
        - machine_manuals: filtered by oem_machine_id (may differ from machine_id)
        - sop_docs: no filter — plant-wide LOTO, PPE, HV safety SOPs

        oem_machine_id is the machine_id stored in the machine_manuals Milvus
        collection, which may differ from the machine_id used in procedure_docs
        (e.g. nordson-problu-gantry vs nordson-problue-7).
        """
        manual_machine_id = oem_machine_id or machine_id
        base_query = " ".join(filter(None, [query, procedure_id, machine_id]))
        sop_query = " ".join(
            filter(
                None,
                [
                    query,
                    procedure_id,
                    "LOTO PPE safety lockout tagout interlock",
                ],
            )
        )

        # 1. Procedure docs — machine-specific procedure steps
        procedure_chunks = self._retriever.search(
            query=base_query,
            machine_id=machine_id,
            collections=["procedure_docs"],
            top_k=top_k,
        )

        # 2. Machine manuals — OEM specs (uses OEM-assigned machine_id)
        manual_chunks = self._retriever.search(
            query=base_query,
            machine_id=manual_machine_id,
            collections=["machine_manuals"],
            top_k=top_k,
        )

        # 3. SOP docs — plant-wide (no machine_id filter — they apply universally)
        sop_chunks = self._retriever.search(
            query=sop_query,
            machine_id=None,
            collections=["sop_docs"],
            top_k=top_k,
        )

        all_chunks = procedure_chunks + manual_chunks + sop_chunks

        if not all_chunks:
            return _empty_context()

        safety_warnings: list[str] = []
        loto_rules: list[str] = []
        terminology: dict[str, str] = {}

        for chunk in all_chunks:
            text: str = chunk.get("content_english") or ""
            doc_type: str = chunk.get("document_type") or ""
            vendor: str = chunk.get("vendor") or ""
            text_lower = text.lower()

            if any(
                kw in text_lower
                for kw in (
                    "warning",
                    "caution",
                    "danger",
                    "ppe",
                    "hazard",
                    "risk",
                )
            ):
                safety_warnings.append(text[:400])
            if any(
                kw in text_lower
                for kw in (
                    "loto",
                    "lockout",
                    "tagout",
                    "de-energize",
                    "lock out",
                    "tag out",
                )
            ):
                loto_rules.append(text[:400])
            if (
                doc_type in ("machine_manual", "procedure")
                and vendor
                and vendor not in terminology
            ):
                doc_name = chunk.get("document_name") or ""
                terminology[vendor] = (
                    f"Refer to {doc_name} for plant-standard terminology equivalents of {vendor} vocabulary"
                )

        return {
            "procedure_chunks": [_to_entry(c) for c in procedure_chunks],
            "machine_manual_chunks": [_to_entry(c) for c in manual_chunks],
            "sop_chunks": [_to_entry(c) for c in sop_chunks],
            "safety_warnings": safety_warnings[:5],
            "loto_rules": loto_rules[:5],
            "approved_terminology": terminology,
            "source_citations": [_build_citation(c) for c in all_chunks],
            "rag_retrieved": True,
            "chunk_count": len(all_chunks),
        }

    def retrieve_machine_context(
        self, machine_id: str, query: Optional[str] = None, top_k: int = 8
    ) -> dict[str, Any]:
        """Retrieve machine context."""
        q = (
            query
            or f"{machine_id} operating procedure setup calibration safety LOTO PPE"
        )
        return self.retrieve_context(
            query=q, machine_id=machine_id, top_k=top_k
        )


def _to_entry(chunk: dict[str, Any]) -> dict[str, Any]:
    """Convert a chunk to an entry."""
    return {
        "chunk_id": chunk.get("chunk_id") or "",
        "text": chunk.get("content_english") or "",
        "source": _build_citation(chunk),
        "score": float(chunk.get("score", 0.0)),
        "collection": chunk.get("collection") or "",
        "machine_id": chunk.get("machine_id") or "",
        "document_type": chunk.get("document_type") or "",
        "document_name": chunk.get("document_name") or "",
        "page_number": chunk.get("page_number") or 0,
        "element_type": chunk.get("element_type") or "",
    }


def _build_citation(chunk: dict[str, Any]) -> str:
    """Build a citation."""
    name = chunk.get("title") or chunk.get("document_name") or "Unknown"
    parts = [name]
    if chunk.get("vendor"):
        parts.append(f"({chunk['vendor']})")
    if chunk.get("page_number"):
        parts.append(f"p.{chunk['page_number']}")
    if chunk.get("source_anchor"):
        parts.append(chunk["source_anchor"])
    return " ".join(parts)


def _empty_context() -> dict[str, Any]:
    """Empty context."""
    return {
        "procedure_chunks": [],
        "machine_manual_chunks": [],
        "sop_chunks": [],
        "safety_warnings": [],
        "loto_rules": [],
        "approved_terminology": {},
        "source_citations": [],
        "rag_retrieved": False,
        "chunk_count": 0,
    }
