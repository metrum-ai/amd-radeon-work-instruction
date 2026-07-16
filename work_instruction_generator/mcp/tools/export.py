# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tools wrapping CompositorExportAgent (PDF/HTML/JSON export).

Uses a module level singleton so the in memory export index
(CompositorExportAgent.exports) survives across tool calls for the lifetime
of the MCP server process, matching the current agent compositor container's
behavior (one process, in memory dict, no shared store).
"""
import os
from typing import Any, Optional

from work_instruction_generator.agents.compositor_export_agent import (
    CompositorExportAgent,
)

_compositor = CompositorExportAgent(
    templates_dir=os.environ.get(
        "WIG_TEMPLATES_DIR", "work_instruction_generator/export/templates"
    ),
    artifact_path=os.environ.get("WIG_ARTIFACT_PATH", "/data/wig/artifacts"),
)


def register(mcp) -> None:
    """Register the tools."""

    @mcp.tool()
    async def compile_export(
        document: dict[str, Any],
        steps: list[dict[str, Any]],
        illustrations: dict[str, dict[str, Any]],
        export_format: str = "pdf",
        include_illustrations: bool = True,
        revisions: Optional[list[dict[str, Any]]] = None,
        tribal_knowledge: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Compile and export a document as pdf/html/json."""
        return await _compositor.export(
            document=document,
            steps=steps,
            illustrations=illustrations,
            export_format=export_format,
            include_illustrations=include_illustrations,
            revisions=revisions,
            tribal_knowledge=tribal_knowledge,
        )

    @mcp.tool()
    async def find_export(
        document_id: str, export_id: str
    ) -> Optional[dict[str, Any]]:
        """Look up a previously created export record."""
        return await _compositor.find_export(document_id, export_id)
