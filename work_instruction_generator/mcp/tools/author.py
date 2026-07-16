# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tools wrapping InstructionAuthorAgent.

Each tool calls the agent's existing public method unchanged, including its
internal LLM call + deterministic fallback behavior (e.g. the
"[AUTODRAFT] LLM offline] ..." text when Gemma is unreachable, or returning
source text unchanged when translation is unreachable) — that behavior lives
in InstructionAuthorAgent._call_llm/_call_translate and is imperative Python,
not something an LLM interpreted OpenClaw skill could reproduce, so it stays
here rather than moving into a skill prompt.
"""
import os
from typing import Any, Optional

from work_instruction_generator.agents.instruction_author_agent import (
    InstructionAuthorAgent,
)

_author = InstructionAuthorAgent(
    llm_url=os.environ.get("AGENT_LLM_URL", "http://vllm-gemma:8000"),
    translate_url=os.environ.get(
        "AGENT_TRANSLATE_URL", "http://vllm-translate:8001"
    ),
)


def register(mcp) -> None:
    """Register the tools."""

    @mcp.tool()
    async def generate_step(
        step_number: int,
        step_description: str,
        source_evidence: dict[str, Any],
        sop_context: dict[str, Any],
        machine_state: Optional[dict[str, Any]] = None,
        interlock_result: Optional[dict[str, Any]] = None,
        target_language: str = "en",
        target_audience: str = "operator",
        total_steps: int = 0,
        previous_step_summary: str = "None",
        existing_instruction_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate one instruction step via Gemma, adapting to interlock state."""
        return await _author.generate_step(
            step_number=step_number,
            step_description=step_description,
            source_evidence=source_evidence,
            sop_context=sop_context,
            machine_state=machine_state,
            interlock_result=interlock_result,
            target_language=target_language,
            target_audience=target_audience,
            total_steps=total_steps,
            previous_step_summary=previous_step_summary,
            existing_instruction_text=existing_instruction_text,
        )

    @mcp.tool()
    async def plan_steps(
        source_evidence: dict[str, Any],
        sop_context: dict[str, Any],
        blocked_prereqs: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Decompose a procedure into ordered {desc, prereq} step objects."""
        return await _author.plan_steps(
            source_evidence, sop_context, blocked_prereqs=blocked_prereqs
        )

    @mcp.tool()
    async def translate_step(
        step: dict[str, Any], target_language: str
    ) -> dict[str, Any]:
        """Translate a step's instruction_text/title via the translation model."""
        return await _author.translate(step, target_language)
