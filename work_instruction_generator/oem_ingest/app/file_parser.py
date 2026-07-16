# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Rich PDF parsing: tables, prose, and embedded images."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page
from pypdf import PdfReader

from .extraction_types import ExtractedElement

logger = logging.getLogger(__name__)

_LIST_ITEM = re.compile(
    r"^[•‣◦⁃∙•●○▪\-\*]\s+", re.MULTILINE
)
_MIN_IMAGE_PX = 50
_SAFE_PNG_MODES = {"RGB", "RGBA", "L", "LA", "P"}


class FileParser:
    """Extracts structured elements from OEM PDF manuals."""

    def parse(self, path: Path, doc_id: str) -> list[ExtractedElement]:
        """Parse a PDF into ordered extraction elements.

        Args:
            path: Path to the source PDF file.
            doc_id: Document identifier used in source anchors.

        Returns:
            Elements in page order: prose, tables, then images per page.

        """
        elements: list[ExtractedElement] = []
        seen_hashes: set[int] = set()
        image_pages = self._images_by_page(path)

        with pdfplumber.open(str(path)) as doc:
            for page_number, page in enumerate(doc.pages, start=1):
                table_bboxes = self._table_bboxes(page)
                elements.extend(
                    self._extract_tables(page, page_number, doc_id, table_bboxes)
                )
                elements.extend(
                    self._extract_prose(page, page_number, doc_id, table_bboxes)
                )
                elements.extend(
                    self._extract_images(
                        image_pages.get(page_number, []),
                        page_number,
                        doc_id,
                        seen_hashes,
                    )
                )

        if not any(
            element.text.strip() or element.image_bytes for element in elements
        ):
            logger.warning(
                "%s: no text or images extracted (scanned PDF?)", path.name
            )

        return elements

    def _table_bboxes(self, page: Page) -> list[tuple[float, float, float, float]]:
        try:
            return [table.bbox for table in page.find_tables()]
        except Exception as exc:
            logger.debug(
                "Table detection skipped on page %s: %s", page.page_number, exc
            )
            return []

    def _extract_tables(
        self,
        page: Page,
        page_number: int,
        doc_id: str,
        table_bboxes: list[tuple[float, float, float, float]],
    ) -> list[ExtractedElement]:
        if not table_bboxes:
            return []

        elements: list[ExtractedElement] = []
        try:
            tables = page.find_tables()
        except Exception as exc:
            logger.warning(
                "Table detection failed on page %d of %s: %s",
                page_number,
                doc_id,
                exc,
            )
            return elements

        for table_index, table in enumerate(tables):
            rows = table.extract()
            if not _table_is_meaningful(rows):
                continue
            markdown = _table_to_markdown(rows)
            if not markdown.strip():
                continue
            elements.append(
                ExtractedElement(
                    element_type="table",
                    page_number=page_number,
                    source_anchor=(
                        f"{doc_id}:page:{page_number}:table:{table_index}"
                    ),
                    text=markdown,
                )
            )
        return elements

    def _extract_prose(
        self,
        page: Page,
        page_number: int,
        doc_id: str,
        table_bboxes: list[tuple[float, float, float, float]],
    ) -> list[ExtractedElement]:
        elements: list[ExtractedElement] = []
        for para_index, paragraph in enumerate(
            _group_lines_into_paragraphs(page.extract_text_lines(), table_bboxes)
        ):
            element_type = (
                "list" if _LIST_ITEM.search(paragraph) else "paragraph"
            )
            elements.append(
                ExtractedElement(
                    element_type=element_type,
                    page_number=page_number,
                    source_anchor=(
                        f"{doc_id}:page:{page_number}:{element_type}:{para_index}"
                    ),
                    text=paragraph,
                )
            )
        return elements

    def _images_by_page(self, path: Path) -> dict[int, list[bytes]]:
        results: dict[int, list[bytes]] = {}
        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            for image in page.images:
                try:
                    png_bytes = _to_png(image.image)
                except Exception as exc:
                    logger.warning(
                        "Skipping image %s on page %s: %s",
                        image.name,
                        page_number,
                        exc,
                    )
                    continue
                if png_bytes:
                    results.setdefault(page_number, []).append(png_bytes)
        return results

    def _extract_images(
        self,
        images: list[bytes],
        page_number: int,
        doc_id: str,
        seen_hashes: set[int],
    ) -> list[ExtractedElement]:
        elements: list[ExtractedElement] = []
        image_index = 0
        for image_bytes in images:
            image_hash = hash(image_bytes)
            if image_hash in seen_hashes:
                continue
            seen_hashes.add(image_hash)
            elements.append(
                ExtractedElement(
                    element_type="image_explanation",
                    page_number=page_number,
                    source_anchor=(
                        f"{doc_id}:page:{page_number}:image:{image_index}"
                    ),
                    image_bytes=image_bytes,
                    skip_translation=True,
                )
            )
            image_index += 1
        return elements


_PARAGRAPH_GAP_RATIO = 1.3
_MIN_LINE_HEIGHT = 4.0


def _rects_intersect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _group_lines_into_paragraphs(
    lines: list[dict],
    table_bboxes: list[tuple[float, float, float, float]],
) -> list[str]:
    """Group text lines into paragraph-like blocks by vertical gap.

    Mirrors PyMuPDF's block-based text extraction, which pdfplumber's
    extract_text() does not reproduce (it never inserts blank lines).
    """
    groups: list[list[dict]] = []
    current: list[dict] = []
    prev_bottom: float | None = None

    for line in lines:
        bbox = (line["x0"], line["top"], line["x1"], line["bottom"])
        if any(_rects_intersect(bbox, table_bbox) for table_bbox in table_bboxes):
            if current:
                groups.append(current)
                current = []
            prev_bottom = None
            continue

        height = max(line["bottom"] - line["top"], _MIN_LINE_HEIGHT)
        gap = line["top"] - prev_bottom if prev_bottom is not None else 0.0
        if prev_bottom is not None and gap > height * _PARAGRAPH_GAP_RATIO:
            groups.append(current)
            current = []

        current.append(line)
        prev_bottom = line["bottom"]

    if current:
        groups.append(current)

    paragraphs = [
        "\n".join(line["text"] for line in group).strip() for group in groups
    ]
    return [paragraph for paragraph in paragraphs if paragraph]


def _table_is_meaningful(rows: list[list[str | None]]) -> bool:
    if len(rows) < 2:
        return False
    filled_cells = sum(
        1 for row in rows for cell in row if cell and str(cell).strip()
    )
    header_filled = sum(1 for cell in rows[0] if cell and str(cell).strip())
    return filled_cells >= 6 and header_filled >= 2


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    if not rows:
        return ""

    def _cell(value: str | None) -> str:
        if value is None:
            return ""
        return str(value).replace("|", "\\|").strip()

    header = [_cell(cell) for cell in rows[0]]
    body = [[_cell(cell) for cell in row] for row in rows[1:]]
    if not any(any(cell for cell in row) for row in rows):
        return ""

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def _to_png(image) -> bytes | None:
    if image.width < _MIN_IMAGE_PX or image.height < _MIN_IMAGE_PX:
        return None
    if image.mode not in _SAFE_PNG_MODES:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
