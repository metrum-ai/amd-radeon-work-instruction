# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Semantic chunking for structured PDF elements."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extraction_types import ExtractedElement

TOKEN_SPLIT = re.compile(r"[\s、。，．！？・·：；،।]+")

_ATOMIC_TYPES = frozenset({"table", "image_explanation"})


@dataclass(frozen=True)
class ChunkDraft:
    """A chunk ready for ingest API serialization."""

    text: str
    element_type: str
    page_number: int
    source_anchor: str
    skip_translation: bool


def count_words(text: str) -> int:
    """Count the words in a text."""
    return sum(1 for token in TOKEN_SPLIT.split(text) if token.strip())


def element_chunks(
    elements: list[ExtractedElement],
    max_words: int,
    overlap_words: int,
) -> list[ChunkDraft]:
    """Build ingest chunks from extracted elements.

    Tables and image explanations are always one chunk each. Prose elements
    are merged up to max_words with optional overlap between prose chunks.

    Args:
        elements: Parsed document elements with text populated.
        max_words: Maximum words per prose chunk.
        overlap_words: Prose overlap between consecutive prose chunks.

    Returns:
        Ordered chunk drafts for the ingest API.

    """
    chunks: list[ChunkDraft] = []
    prose_buffer: list[ExtractedElement] = []
    prose_words = 0

    for element in elements:
        if not element.text.strip():
            continue

        # Drop fragments too short to be useful for RAG (e.g. page-number footers)
        if (
            count_words(element.text) < 5
            and element.element_type not in _ATOMIC_TYPES
        ):
            continue

        if element.element_type in _ATOMIC_TYPES:
            chunks.extend(
                _flush_prose(
                    prose_buffer, prose_words, max_words, overlap_words
                )
            )
            prose_buffer = []
            prose_words = 0
            chunks.append(_element_to_chunk(element))
            continue

        paragraph_words = max(count_words(element.text), 1)
        if prose_buffer and (prose_words + paragraph_words > max_words):
            chunks.extend(
                _flush_prose(
                    prose_buffer, prose_words, max_words, overlap_words
                )
            )
            prose_buffer = _overlap_elements(prose_buffer, overlap_words)
            prose_words = sum(
                max(count_words(item.text), 1) for item in prose_buffer
            )

        prose_buffer.append(element)
        prose_words += paragraph_words

    chunks.extend(
        _flush_prose(prose_buffer, prose_words, max_words, overlap_words)
    )
    return chunks


def _element_to_chunk(element: ExtractedElement) -> ChunkDraft:
    """Convert an extracted element to a chunk draft."""
    return ChunkDraft(
        text=element.text.strip(),
        element_type=element.element_type,
        page_number=element.page_number,
        source_anchor=element.source_anchor,
        skip_translation=element.skip_translation,
    )


def _flush_prose(
    elements: list[ExtractedElement],
    prose_words: int,
    max_words: int,
    overlap_words: int,
) -> list[ChunkDraft]:
    """Flush prose elements into chunks."""
    del prose_words, max_words, overlap_words
    if not elements:
        return []

    if len(elements) == 1:
        return [_element_to_chunk(elements[0])]

    dominant = _dominant_type(elements)
    return [
        ChunkDraft(
            text="\n\n".join(item.text.strip() for item in elements),
            element_type=dominant,
            page_number=elements[0].page_number,
            source_anchor=elements[0].source_anchor,
            skip_translation=elements[0].skip_translation,
        )
    ]


def _dominant_type(elements: list[ExtractedElement]) -> str:
    """Determine the dominant type of a list of elements."""
    types = {element.element_type for element in elements}
    if types == {"list"}:
        return "list"
    return "paragraph"


def _overlap_elements(
    elements: list[ExtractedElement],
    overlap_words: int,
) -> list[ExtractedElement]:
    """Overlap elements to create a list of elements with overlap."""
    if overlap_words <= 0:
        return []

    kept: list[ExtractedElement] = []
    running_words = 0
    for element in reversed(elements):
        kept.insert(0, element)
        running_words += count_words(element.text)
        if running_words >= overlap_words:
            break
    return kept
