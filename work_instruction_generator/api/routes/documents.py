# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Document and source-artifact routes for WIG."""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from work_instruction_generator.api.models import (
    DocumentCreate,
    DocumentDetail,
    DocumentResponse,
    DocumentSummary,
    ExportSummary,
    PaginatedResponse,
    RevisionSummary,
    SourceArtifact,
    StepResponse,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wig", tags=["documents"])


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(payload: DocumentCreate) -> DocumentResponse:
    """Create a new document."""
    doc = await store.create_document(payload.model_dump())
    return DocumentResponse(**doc)


@router.get("/documents", response_model=PaginatedResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse:
    """List documents."""
    items = await store.list_documents(page=page, page_size=page_size)
    total = await store.count_documents()
    return PaginatedResponse(
        items=[DocumentSummary(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str) -> DocumentDetail:
    """Get a document."""
    doc = await store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    steps = [
        StepResponse(**step) for step in await store.list_steps(document_id)
    ]
    revisions = [
        RevisionSummary(**rev)
        for rev in await store.list_revisions(document_id)
    ]
    exports = [
        ExportSummary(**exp) for exp in await store.list_exports(document_id)
    ]
    return DocumentDetail(
        **{k: v for k, v in doc.items() if k != "step_count"},
        step_count=doc["step_count"],
        steps=steps,
        revisions=revisions,
        exports=exports,
    )


@router.delete(
    "/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_document(document_id: str) -> None:
    """Delete a document."""
    if not await store.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")


@router.get(
    "/documents/{document_id}/sources",
    response_model=list[SourceArtifact],
)
async def list_sources(document_id: str) -> list[SourceArtifact]:
    """List sources for a document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return [
        SourceArtifact(**src) for src in await store.list_sources(document_id)
    ]
