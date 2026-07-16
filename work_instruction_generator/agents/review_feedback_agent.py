# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""ReviewFeedbackAgent — routes engineer review comments and captures tribal knowledge.

Accepts engineer review comments from the chat UI, identifies affected steps via
step-number pattern and keyword matching, and captures approved tribal knowledge
as versioned records attached to the document.

Exposed to the OpenClaw gateway as MCP tools: work_instruction_generator/mcp/tools/review_feedback.py
Next agents: InstructionAuthorAgent, TechnicalIllustrationAgent, CompositorExportAgent
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


class ReviewFeedbackAgent:
    """Route review comments and capture tribal knowledge.

    Tribal knowledge acceptance: immediate (MVP — poster = approver).
    Add a two-step approval flow when named reviewer roles are defined.
    """

    def process(
        self,
        document_id: str,
        content: str,
        steps: list[dict[str, Any]],
        step_id: Optional[str] = None,
        mark_as_tribal_knowledge: bool = False,
    ) -> dict[str, Any]:
        """Process one engineer review comment.

        Returns:
            affected_steps: step IDs matched by this comment
            suggestions:    human-readable actions for affected steps
            tk_id:          UUID of the stored tribal-knowledge record, or None
            tk_content:     the text stored as tribal knowledge, or None

        """
        if step_id:
            affected = [step_id]
        else:
            affected = self._find_affected_steps(steps, content)

        tk_id: Optional[str] = None
        if mark_as_tribal_knowledge:
            tk_id = str(uuid.uuid4())

        suggestions = self._build_suggestions(
            affected, steps, mark_as_tribal_knowledge
        )

        return {
            "affected_steps": affected,
            "tk_id": tk_id,
            "suggestions": suggestions,
        }

    def build_tk_record(
        self,
        tk_id: str,
        document_id: str,
        content: str,
        affected_steps: list[str],
    ) -> dict[str, Any]:
        """Build the tribal knowledge dict for storage."""
        return {
            "tk_id": tk_id,
            "document_id": document_id,
            "content": content,
            "step_ids": affected_steps,
            "status": "accepted",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _find_affected_steps(
        self, steps: list[dict[str, Any]], content: str
    ) -> list[str]:
        lower = content.lower()
        affected: list[str] = []

        # Detect explicit "step 3" / "#3" references
        step_nums: set[int] = set()
        for m in re.finditer(r"\bstep\s+(\d+)\b", lower):
            step_nums.add(int(m.group(1)))
        for m in re.finditer(r"#(\d+)\b", lower):
            step_nums.add(int(m.group(1)))

        for step in steps:
            if step.get("step_number") in step_nums:
                affected.append(step["step_id"])
                continue
            # Keyword match: words > 3 chars from the step title
            title_words = [
                w
                for w in (step.get("title") or "").lower().split()
                if len(w) > 3
            ]
            if any(w in lower for w in title_words):
                affected.append(step["step_id"])

        return affected

    def _build_suggestions(
        self,
        affected: list[str],
        steps: list[dict[str, Any]],
        is_tk: bool,
    ) -> list[str]:
        step_map = {s["step_id"]: s for s in steps}
        suggestions = []
        for sid in affected[:3]:
            s = step_map.get(sid)
            num = s["step_number"] if s else "?"
            verb = "Re-generate" if is_tk else "Review"
            suggestions.append(f"{verb} step {num}")
        if not affected and not steps:
            suggestions.append(
                "Add a tribal knowledge note for future generations"
            )
        return suggestions
