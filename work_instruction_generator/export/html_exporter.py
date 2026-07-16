# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""HTML Exporter for WIG."""

import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from work_instruction_generator.export._template_support import (
    read_inline_css,
    running_header_safe,
)

logger = logging.getLogger(__name__)


class HTMLExporter:
    """Generates responsive HTML output with base64 embedded images."""

    def __init__(self, templates_dir: str, artifact_path: str):
        self.templates_dir = Path(templates_dir)
        self.artifact_path = Path(artifact_path)
        self.env = Environment(loader=FileSystemLoader(str(self.templates_dir)), autoescape=select_autoescape(["html", "xml"]))

    def _encode_image_to_base64(self, ill_ref: str) -> str:
        """Reads a local image under artifact_path and embeds it as a base64 data URI."""
        try:
            # artifact_ref is stored as a web URL; resolve to filesystem path
            if ill_ref.startswith("/api/v1/wig/artifacts/"):
                p = (self.artifact_path / Path(ill_ref).name).resolve()
            else:
                p = Path(ill_ref).resolve()
            # Only embed files that resolve under artifact_path; reject out-of-tree refs.
            root = self.artifact_path.resolve()
            if p.is_relative_to(root) and p.is_file():
                mime_type, _ = mimetypes.guess_type(p.name)
                if not mime_type:
                    mime_type = "image/png"

                with open(p, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:{mime_type};base64,{data}"
        except Exception as e:
            logger.warning("Failed to encode image %s: %s", ill_ref, e)

        # Return a 1x1 transparent pixel as fallback to avoid broken images
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    def export(
        self,
        document: dict[str, Any],
        steps: list[dict[str, Any]],
        illustrations: dict[str, dict[str, Any]],
    ) -> Path:
        """Renders responsive HTML and embeds images as base64."""
        logger.info("Exporting HTML for document: %s", document.get("title"))

        # Enrich steps with base64 images
        enriched_steps = []
        for step in steps:
            step_copy = step.copy()
            step_id = step.get("step_id")
            if step_id in illustrations:
                ill_ref = illustrations[step_id].get("artifact_ref")
                step_copy["illustration_url"] = self._encode_image_to_base64(
                    ill_ref
                )
            else:
                step_copy["illustration_url"] = None
            enriched_steps.append(step_copy)

        context = {
            "title": document.get("title"),
            "asset_id": document.get("asset_id"),
            "procedure_id": document.get("procedure_id"),
            "revision": document.get("revision", 1),
            "header_title": running_header_safe(document.get("title")),
            "header_asset_id": running_header_safe(document.get("asset_id")),
            "inline_css": read_inline_css(self.templates_dir),
            "steps": enriched_steps,
            "metadata": document.get("metadata", {}),
            "toc_items": [
                {
                    "number": s.get("step_number"),
                    "title": s.get("title", ""),
                    "interlock_status": s.get(
                        "interlock_status", "not_evaluated"
                    ),
                }
                for s in enriched_steps
            ],
            "source_citations": self._collect_citations(enriched_steps),
        }

        template = self.env.get_template("standard.html")
        html_content = template.render(**context)

        safe_id = re.sub(
            r"[^A-Za-z0-9_-]", "_", str(document.get("document_id", "unknown"))
        )
        output_filename = f"export_{safe_id}.html"
        output_path = self.artifact_path / output_filename

        self.artifact_path.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info("HTML successfully written to: %s", output_path)
        return output_path

    def _collect_citations(self, steps: list) -> list:
        """Collect all unique source citations, sorted.

        Sorted to match the PDF and JSON exporters so the source index is
        consistent across every export format.
        """
        citations = set()
        for step in steps:
            for cite in step.get("source_citations", []):
                citations.add(cite)
        return sorted(citations)
