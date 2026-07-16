# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""PDF Compositor for WIG."""

import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from work_instruction_generator.export._template_support import (
    read_inline_css,
    running_header_safe,
)

logger = logging.getLogger(__name__)


class PDFCompositor:
    """Renders content into a standardized PDF using WeasyPrint and Jinja2 templates."""

    def __init__(self, templates_dir: str, artifact_path: str):
        """Initialize the PDFCompositor."""
        self.templates_dir = Path(templates_dir)
        self.artifact_path = Path(artifact_path)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _get_illustration_url(self, ill_ref: str) -> str:
        """Resolve an artifact_ref to a file:// URI under artifact_path.

        Only files that actually resolve under artifact_path are served;
        anything else (remote URLs, out-of-tree local paths) is rejected so
        WeasyPrint can't be steered into SSRF or arbitrary local-file reads.
        """
        if ill_ref.startswith("/api/v1/wig/artifacts/"):
            local = self.artifact_path / Path(ill_ref).name
        else:
            local = Path(ill_ref)
        root = self.artifact_path.resolve()
        resolved = local.resolve()
        if resolved.is_relative_to(root) and resolved.exists():
            return resolved.as_uri()  # handles spaces/special chars safely
        logger.warning("Rejected out-of-tree illustration ref: %s", ill_ref)
        return ""

    def compose(
        self,
        document: dict[str, Any],
        steps: list[dict[str, Any]],
        illustrations: dict[
            str, dict[str, Any]
        ],  # step_id -> illustration_data
    ) -> Path:
        """Generates a PDF document."""
        logger.info("Composing PDF for document: %s", document.get("title"))

        # 1. Prepare step data with attached illustrations
        enriched_steps = []
        for step in steps:
            step_copy = step.copy()
            step_id = step.get("step_id")
            if step_id in illustrations:
                ref = illustrations[step_id].get("artifact_ref") or ""
                step_copy["illustration_url"] = (
                    self._get_illustration_url(ref) if ref else None
                )
            else:
                step_copy["illustration_url"] = None
            enriched_steps.append(step_copy)

        # 2. Prepare template context
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
            # TOC / Index components
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

        # 3. Render HTML via Jinja2
        template = self.env.get_template("standard.html")
        html_content = template.render(**context)

        # 4. Generate PDF via WeasyPrint
        safe_id = re.sub(
            r"[^A-Za-z0-9_-]", "_", str(document.get("document_id", "unknown"))
        )
        output_filename = f"export_{safe_id}.pdf"
        output_path = self.artifact_path / output_filename

        try:
            # Ensure artifact dir exists
            self.artifact_path.mkdir(parents=True, exist_ok=True)

            # Use templates_dir as base_url so relative URIs (print.css, img src) resolve
            HTML(
                string=html_content, base_url=str(self.templates_dir)
            ).write_pdf(str(output_path))
            logger.info("PDF successfully written to: %s", output_path)
            return output_path
        except Exception as e:
            logger.error("WeasyPrint compilation failed: %s", e)
            raise

    def _collect_citations(self, steps: list[dict[str, Any]]) -> list[str]:
        """Collects all unique source citations from all steps."""
        citations = set()
        for step in steps:
            for cite in step.get("source_citations", []):
                citations.add(cite)
        return sorted(list(citations))
