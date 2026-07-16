# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tools wrapping WorkInstructionOrchestrator's machine-state/interlock logic.

Both tools delegate to the existing, unchanged WorkInstructionOrchestrator
methods (work_instruction_orchestrator.py) — evaluate_interlock in particular
is safety critical and must stay byte for byte identical; see
tests/wig/test_evaluate_interlock_parity.py.
"""
from typing import Any

from work_instruction_generator.agents.work_instruction_orchestrator import (
    orchestrator,
)


def register(mcp) -> None:
    """Register the tools."""

    @mcp.tool()
    async def fetch_machine_state(station_id: str) -> dict[str, Any]:
        """Fetch live machine state for a station from the simulator, falling
        back to the last stored snapshot if the simulator is unreachable.
        """
        return await orchestrator.fetch_live_machine_state(station_id) or {}

    @mcp.tool()
    def evaluate_interlock(
        station_id: str, machine_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate hard interlocks from machine readiness_flags. Returns
        {status, blocked_reasons, required_actions}.
        """
        return orchestrator.evaluate_interlock(station_id, machine_state)
