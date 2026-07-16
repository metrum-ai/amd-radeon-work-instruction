# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Loader for OEM ingest application."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .file_parser import FileParser
from .image_analyzer import ImageAnalyzer
from .models import SourceDocument

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Loads OEM PDFs with rich structure and optional VLM image analysis."""

    def __init__(
        self,
        documents_dir: str,
        analyze_images: bool = True,
        image_analyzer: ImageAnalyzer | None = None,
    ) -> None:
        """Initialize the document loader."""
        self.documents_dir = Path(documents_dir)
        self.analyze_images = analyze_images
        self._parser = FileParser()
        self._image_analyzer = image_analyzer

    def load_documents(self) -> list[SourceDocument]:
        """Load the documents."""
        if not self.documents_dir.exists():
            raise FileNotFoundError(
                f"Documents directory does not exist: {self.documents_dir}"
            )

        documents: list[SourceDocument] = []
        for path in sorted(self.documents_dir.glob("*.pdf")):
            try:
                documents.append(self._load_pdf(path))
            except Exception as exc:
                logger.error("Failed to load %s: %s", path.name, exc)

        if not documents:
            raise ValueError(f"No .pdf documents found in {self.documents_dir}")

        return documents

    def _load_pdf(self, path: Path) -> SourceDocument:
        """Load a PDF document."""
        meta = self._load_meta(path)
        required = ("doc_id", "title", "document_type", "version")
        missing = [field for field in required if field not in meta]
        if missing:
            raise ValueError(
                f"{path.name}: missing metadata fields: {', '.join(missing)}"
            )

        doc_id = meta["doc_id"]
        elements = self._parser.parse(path, doc_id)
        if not self.analyze_images:
            elements = [
                element
                for element in elements
                if element.element_type != "image_explanation"
            ]
        elif self._image_analyzer is not None:
            elements = self._image_analyzer.explain_elements(elements)

        return SourceDocument(
            doc_id=doc_id,
            document_name=path.stem,
            title=meta["title"],
            vendor=meta.get("vendor", ""),
            machine_id=meta.get("machine_id", ""),
            document_type=meta["document_type"],
            version=meta["version"],
            declared_language=meta.get("language"),
            source_path=path,
            elements=elements,
        )

    def _load_meta(self, pdf_path: Path) -> dict:
        """Load the metadata for a PDF document."""
        # Try exact match first: file.pdf → file.meta.yaml
        # Also try language-tagged: file.pdf → file.en.meta.yaml (glob any lang code)
        candidates = [
            pdf_path.with_suffix(".meta.yaml"),
            *sorted(pdf_path.parent.glob(pdf_path.stem + ".*.meta.yaml")),
        ]
        for sidecar in candidates:
            if sidecar.exists():
                with sidecar.open(encoding="utf-8") as handle:
                    return yaml.safe_load(handle) or {}
        raise FileNotFoundError(
            f"No .meta.yaml sidecar found for {pdf_path.name}"
        )
