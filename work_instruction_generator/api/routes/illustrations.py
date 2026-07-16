# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Illustration management API routes."""


from fastapi import APIRouter, BackgroundTasks, HTTPException

from work_instruction_generator.agents.technical_illustration_agent import (
    TechnicalIllustrationAgent,
)
from work_instruction_generator.api.models import (
    IllustrationRequest,
    IllustrationResponse,
)
from work_instruction_generator.api.store import store

router = APIRouter(prefix="/api/v1/wig", tags=["illustrations"])
_agent = TechnicalIllustrationAgent()


def _to_response(ill: dict) -> IllustrationResponse:
    return IllustrationResponse(
        illustration_id=ill["illustration_id"],
        step_id=ill.get("step_id"),
        style=ill.get("style", "technical_diagram"),
        image_url=ill.get("artifact_ref") or "",
        width=ill.get("width", 768),
        height=ill.get("height", 512),
        status=ill.get("status", "completed"),
    )


@router.get(
    "/documents/{document_id}/illustrations",
    response_model=list[IllustrationResponse],
)
async def get_illustrations(document_id: str):
    """Get the illustrations for a document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return [
        _to_response(ill) for ill in await store.list_illustrations(document_id)
    ]


@router.post(
    "/documents/{document_id}/illustrations/{ill_id}/regenerate",
    response_model=IllustrationResponse,
)
async def regenerate_illustration(
    document_id: str,
    ill_id: str,
    request: IllustrationRequest,
    background_tasks: BackgroundTasks,
):
    """Regenerate an illustration."""
    ill = await store.get_illustration(ill_id)
    if ill is None or ill.get("document_id") != document_id:
        raise HTTPException(status_code=404, detail="Illustration not found")

    async def _regen():
        result = await _agent.regenerate(
            ill_id=ill_id, style_override=request.style
        )
        await store.add_illustration(
            {
                **ill,
                "artifact_ref": result.get("artifact_ref")
                or result.get("image_url"),
                "style": request.style or ill.get("style", "technical_diagram"),
                "status": result.get("status", "completed"),
            }
        )

    background_tasks.add_task(_regen)
    return _to_response({**ill, "status": "generating"})


@router.post(
    "/documents/{document_id}/illustrations/regenerate-all",
    response_model=list[IllustrationResponse],
)
async def regenerate_all_illustrations(
    document_id: str, background_tasks: BackgroundTasks
):
    """Regenerate all illustrations for a document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    ills = await store.list_illustrations(document_id)

    async def _regen_all():
        for ill in ills:
            result = await _agent.regenerate(ill_id=ill["illustration_id"])
            await store.add_illustration(
                {
                    **ill,
                    "artifact_ref": result.get("artifact_ref")
                    or result.get("image_url"),
                    "status": result.get("status", "completed"),
                }
            )

    background_tasks.add_task(_regen_all)
    return [_to_response({**ill, "status": "generating"}) for ill in ills]
