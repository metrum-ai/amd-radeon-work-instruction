# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""JSON Exporter for WIG."""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JSONExporter:
    """Exports structured JSON for downstream tools and re-import."""

    def __init__(self, artifact_path: str):
        """Initialize the JSONExporter."""
        self.artifact_path = Path(artifact_path)

    def export(
        self,
        document: dict[str, Any],
        steps: list[dict[str, Any]],
        illustrations: dict[str, dict[str, Any]],
        revisions: Optional[list[dict[str, Any]]] = None,
        tribal_knowledge: Optional[list[dict[str, Any]]] = None,
    ) -> Path:
        """Generates a structured JSON file."""
        logger.info("Exporting JSON for document: %s", document.get("title"))

        export_data = {
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "document": {
                "document_id": document.get("document_id"),
                "title": document.get("title"),
                "description": document.get("description"),
                "product_name": document.get("product_name"),
                "asset_id": document.get("asset_id"),
                "procedure_id": document.get("procedure_id"),
                "station_id": document.get("station_id"),
                "procedure_stage": document.get("procedure_stage"),
                "vendor_names": document.get("vendor_names", []),
                "target_language": document.get("target_language", "en"),
                "status": document.get("status"),
                "metadata": document.get("metadata", {}),
            },
            "steps": steps,
            "illustrations": list(illustrations.values()),
            "revisions": revisions or [],
            "tribal_knowledge": tribal_knowledge or [],
            "source_citations_summary": self._collect_citations(steps),
        }

        safe_id = re.sub(
            r"[^A-Za-z0-9_-]", "_", str(document.get("document_id", "unknown"))
        )
        output_filename = f"export_{safe_id}.json"
        output_path = self.artifact_path / output_filename

        self.artifact_path.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info("JSON successfully written to: %s", output_path)
        return output_path

    def _collect_citations(self, steps: list[dict[str, Any]]) -> list[str]:
        """Collect all unique source citations."""
        citations = set()
        for step in steps:
            for cite in step.get("source_citations", []):
                citations.add(cite)
        return sorted(list(citations))
