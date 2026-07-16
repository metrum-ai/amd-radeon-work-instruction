# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Compositor & Export Agent for WIG.

Terminal OpenClaw agent that compiles, exports, and publishes
final standardized work instructions. Supports PDF via WeasyPrint,
responsive HTML, and structured JSON output.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from work_instruction_generator.export.html_exporter import HTMLExporter
from work_instruction_generator.export.json_exporter import JSONExporter
from work_instruction_generator.export.pdf_compositor import PDFCompositor

logger = logging.getLogger(__name__)


class CompositorExportAgent:
    """Compose, export, and publish final standardized work instructions.

    This is a terminal OpenClaw agent — it calls the appropriate
    exporter based on the requested format and returns the artifact
    reference for download/display.
    """

    def __init__(
        self,
        templates_dir: str = "work_instruction_generator/export/templates",
        artifact_path: str = "/data/wig/artifacts",
    ):
        """Initialize the CompositorExportAgent."""
        self.pdf_compositor = PDFCompositor(templates_dir, artifact_path)
        self.html_exporter = HTMLExporter(templates_dir, artifact_path)
        self.json_exporter = JSONExporter(artifact_path)
        self.exports: dict[str, list[dict[str, Any]]] = {}

    async def export(
        self,
        document: dict[str, Any],
        steps: list[dict[str, Any]],
        illustrations: dict[str, dict[str, Any]],
        export_format: str = "pdf",
        include_illustrations: bool = True,
        revisions: Optional[list[dict[str, Any]]] = None,
        tribal_knowledge: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Main entry point to export a document in the requested format."""
        document_id = document.get("document_id", str(uuid.uuid4()))
        export_id = str(uuid.uuid4())

        logger.info(
            "Exporting document %(document_id)s as %(export_format)s",
            {
                "document_id": document_id,
                "export_format": export_format,
            },
        )

        if not include_illustrations:
            illustrations = {}

        output_path: Optional[Path] = None

        if export_format == "pdf":
            output_path = self.pdf_compositor.compose(
                document=document,
                steps=steps,
                illustrations=illustrations,
            )
            content_type = "application/pdf"
        elif export_format == "html":
            output_path = self.html_exporter.export(
                document=document,
                steps=steps,
                illustrations=illustrations,
            )
            content_type = "text/html"
        elif export_format == "json":
            output_path = self.json_exporter.export(
                document=document,
                steps=steps,
                illustrations=illustrations,
                revisions=revisions or [],
                tribal_knowledge=tribal_knowledge or [],
            )
            content_type = "application/json"
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        file_size_bytes = (
            output_path.stat().st_size
            if output_path and output_path.exists()
            else 0
        )

        export_record = {
            "export_id": export_id,
            "document_id": document_id,
            "format": export_format,
            "artifact_ref": str(output_path) if output_path else None,
            "file_size_bytes": file_size_bytes,
            "content_type": content_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist in-memory
        if document_id not in self.exports:
            self.exports[document_id] = []
        self.exports[document_id].append(export_record)

        logger.info(
            "Export %(export_id)s completed: %(file_size_bytes)s bytes, %(content_type)s",
            {
                "export_id": export_id,
                "file_size_bytes": file_size_bytes,
                "content_type": content_type,
            },
        )
        return export_record

    async def find_export(
        self, document_id: str, export_id: str
    ) -> Optional[dict[str, Any]]:
        """Lookup an export record."""
        doc_exports = self.exports.get(document_id, [])
        for e in doc_exports:
            if e["export_id"] == export_id:
                return e
        return None
