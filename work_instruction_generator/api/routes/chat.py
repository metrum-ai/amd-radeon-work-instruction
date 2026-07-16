# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Refinement chat route for WIG.

Delegates to ReviewFeedbackAgent to identify affected steps and capture
tribal knowledge, then broadcasts the exchange over the WS chat channel.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from work_instruction_generator.agents.review_feedback_agent import (
    ReviewFeedbackAgent,
)
from work_instruction_generator.api.models import ChatMessage, ChatResponse
from work_instruction_generator.api.routes.websocket import hub
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wig", tags=["chat"])

_agent = ReviewFeedbackAgent()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post(
    "/documents/{document_id}/chat",
    response_model=ChatResponse,
)
async def post_chat(document_id: str, msg: ChatMessage) -> ChatResponse:
    """Post a chat message to the document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")

    steps = await store.list_steps(document_id)
    result = _agent.process(
        document_id=document_id,
        content=msg.content,
        steps=steps,
        step_id=msg.step_id,
        mark_as_tribal_knowledge=msg.mark_as_tribal_knowledge,
    )
    affected = result["affected_steps"]
    tk_id: str | None = result["tk_id"]
    suggestions: list[str] = result["suggestions"]

    # Store tribal knowledge record and update step refs
    if tk_id is not None:
        tk = _agent.build_tk_record(tk_id, document_id, msg.content, affected)
        await store.add_tribal_knowledge(document_id, tk)
        for sid in affected:
            step = await store.get_step(document_id, sid)
            if step is not None:
                refs = list(step.get("tribal_knowledge_refs", []))
                refs.append(tk_id)
                await store.update_step(
                    document_id, sid, {"tribal_knowledge_refs": refs}
                )

    message_id = str(uuid.uuid4())
    engineer_msg = {
        "message_id": message_id,
        "document_id": document_id,
        "role": "engineer",
        "content": msg.content,
        "step_id": msg.step_id,
        "accepted_as_tribal_knowledge": msg.mark_as_tribal_knowledge,
        "tk_id": tk_id,
        "created_at": _now_iso(),
    }
    await store.add_chat(document_id, engineer_msg)

    tk_note = (
        " Marked as tribal knowledge." if msg.mark_as_tribal_knowledge else ""
    )
    assistant_content = (
        f"Noted.{tk_note} {len(affected)} step(s) flagged for review."
        if affected
        else f"Noted.{tk_note} No matching steps detected."
    )
    assistant_id = str(uuid.uuid4())
    assistant_msg = {
        "message_id": assistant_id,
        "document_id": document_id,
        "role": "assistant",
        "content": assistant_content,
        "step_id": msg.step_id,
        "accepted_as_tribal_knowledge": False,
        "tk_id": None,
        "created_at": _now_iso(),
    }
    await store.add_chat(document_id, assistant_msg)

    # Broadcast to WS chat channel (best-effort; import deferred to avoid circular dep at module load)
    try:
        channel = f"chat:{document_id}"
        await hub.publish(channel, {"event": "message", **engineer_msg})
        await hub.publish(channel, {"event": "message", **assistant_msg})
    except Exception as exc:
        logger.debug("WS broadcast skipped: %s", exc)

    return ChatResponse(
        message_id=assistant_id,
        content=assistant_content,
        suggestions=suggestions,
        affected_steps=affected,
    )
