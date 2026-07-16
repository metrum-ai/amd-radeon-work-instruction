# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Models for ingest application."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class TranslationResult:
    """Translation result."""

    source_language: str
    target_language: str
    provider: str
    translated_text: str


@dataclass(frozen=True)
class ChunkRecord:
    """Chunk record."""

    chunk_id: str
    source_doc_id: str
    document_name: str
    title: str
    vendor: str
    machine_id: str
    document_type: str
    version: str
    source_language: str
    translated_language: str
    translation_provider: str
    chunk_index: int
    content_original: str
    content_english: str
    element_type: str
    page_number: int
    source_anchor: str


class ChunkItem(BaseModel):
    """Chunk item."""

    doc_id: str
    document_name: str = ""
    title: str
    vendor: str = ""
    machine_id: str = ""
    document_type: str
    version: str
    source_language: str
    target_language: str
    chunk_index: int
    content_original: str
    element_type: str = "paragraph"
    page_number: int = 0
    source_anchor: str = ""
    skip_translation: bool = False


class IngestRequest(BaseModel):
    """Ingest request."""

    chunks: list[ChunkItem]
    reset_collection: bool = False
    collection: str = ""


class IngestResponse(BaseModel):
    """Ingest response."""

    ingested: int
    collection: str
