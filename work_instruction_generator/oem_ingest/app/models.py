# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Models for OEM ingest application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .extraction_types import ExtractedElement


@dataclass(frozen=True)
class SourceDocument:
    """Source document model."""

    doc_id: str
    document_name: str
    title: str
    vendor: str
    machine_id: str
    document_type: str
    version: str
    declared_language: str | None
    source_path: Path
    elements: list[ExtractedElement]

    @property
    def content(self) -> str:
        """Plain text summary used for language detection."""
        return "\n\n".join(
            element.text.strip()
            for element in self.elements
            if element.text.strip()
        )
