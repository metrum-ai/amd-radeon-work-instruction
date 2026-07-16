# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Pydantic models for context/retrieval endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ContextChunk(BaseModel):
    """A single chunk of context."""

    chunk_id: str
    document_name: str
    title: str
    vendor: str = ""
    machine_id: str = ""
    document_type: str = ""
    collection: str
    content: str
    page_number: int = 0
    source_anchor: str = ""
    score: float


class ContextResponse(BaseModel):
    """A response to a context query."""

    query: str
    machine_id: Optional[str] = None
    total: int
    chunks: list[ContextChunk]
    collections_searched: list[str] = []


class SOPEntry(BaseModel):
    """A single retrieved chunk with full source traceability."""

    chunk_id: str
    text: str
    source: str
    score: float
    collection: str
    machine_id: str = ""
    document_type: str = ""
    document_name: str = ""
    page_number: int = 0


class ProcedureContextResponse(BaseModel):
    """Full context for a selected procedure — procedure steps + machine manual + SOPs.

    Three separate collections are queried:
      procedure_chunks      — procedure steps/interlocks filtered by machine_id
      machine_manual_chunks — OEM manual content filtered by machine_id
      sop_chunks            — plant-wide LOTO/PPE/safety SOPs (no machine filter)

    Cross-collection classified fields are also returned for direct prompt injection:
      safety_warnings       → {rag_context} placeholder
      loto_rules            → LOTO enforcement block
      approved_terminology  → {terminology_context} placeholder
      source_citations      → {source_citations} placeholder
    """

    procedure_id: str
    procedure_name: str
    station_id: str
    station_name: str
    machine_id: str
    rag_retrieved: bool
    chunk_count: int

    # Per-collection results
    procedure_chunks: list[SOPEntry] = []
    machine_manual_chunks: list[SOPEntry] = []
    sop_chunks: list[SOPEntry] = []

    # Cross-collection classified
    safety_warnings: list[str] = []
    loto_rules: list[str] = []
    approved_terminology: dict[str, str] = {}
    source_citations: list[str] = []
