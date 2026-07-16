# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Types for structured PDF extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedElement:
    """A single unit extracted from a PDF page.

    Attributes:
        element_type: One of table, paragraph, list, image_explanation.
        page_number: 1-based page index in the source PDF.
        source_anchor: Stable citation id, e.g. doc_id:page:3:table:0.
        text: Text or markdown content; empty until VLM runs for images.
        image_bytes: Raw PNG bytes for figures pending VLM analysis.
        skip_translation: When True, content is already English (VLM output).

    """

    element_type: str
    page_number: int
    source_anchor: str
    text: str = ""
    image_bytes: bytes | None = None
    skip_translation: bool = False
