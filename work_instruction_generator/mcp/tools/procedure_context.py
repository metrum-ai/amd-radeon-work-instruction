# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tool wrapping WorkInstructionOrchestrator's SOP/RAG context fetch."""
from typing import Any

from work_instruction_generator.agents.work_instruction_orchestrator import (
    orchestrator,
)


def register(mcp) -> None:
    """Register the tools."""

    @mcp.tool()
    async def fetch_procedure_context(
        procedure_id: str, top_k: int = 5
    ) -> dict[str, Any]:
        """Fetch RAG procedure context (SOPs, LOTO rules, terminology, tribal
        knowledge) for a procedure. Returns {} if unavailable.
        """
        return await orchestrator.fetch_procedure_context(procedure_id, top_k)
