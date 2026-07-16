# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tools wrapping ReviewFeedbackAgent.

ReviewFeedbackAgent is not called by any route today (confirmed orphaned) —
these tools exist for parity with the pre-migration architecture, not to
introduce new behavior. Wiring a real review/feedback route is separate
feature work.
"""
from typing import Any, Dict, List, Optional

from work_instruction_generator.agents.review_feedback_agent import (
    ReviewFeedbackAgent,
)

_review = ReviewFeedbackAgent()


def register(mcp) -> None:
    @mcp.tool()
    def review_feedback(
        document_id: str,
        content: str,
        steps: List[Dict[str, Any]],
        step_id: Optional[str] = None,
        mark_as_tribal_knowledge: bool = False,
    ) -> Dict[str, Any]:
        """Process one engineer review comment; returns affected steps/suggestions."""
        return _review.process(
            document_id=document_id,
            content=content,
            steps=steps,
            step_id=step_id,
            mark_as_tribal_knowledge=mark_as_tribal_knowledge,
        )

    @mcp.tool()
    def build_tribal_knowledge_record(
        tk_id: str, document_id: str, content: str, affected_steps: List[str]
    ) -> Dict[str, Any]:
        """Build a tribal-knowledge record dict for storage."""
        return _review.build_tk_record(
            tk_id, document_id, content, affected_steps
        )
