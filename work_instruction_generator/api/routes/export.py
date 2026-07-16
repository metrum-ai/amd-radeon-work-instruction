# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Export API routes for WIG."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from work_instruction_generator.agents.compositor_export_agent import (
    CompositorExportAgent,
)
from work_instruction_generator.api.models import (
    ExportRequest,
    ExportResponse,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wig", tags=["exports"])
agent = CompositorExportAgent()


@router.post("/documents/{document_id}/export", response_model=ExportResponse)
async def export_document(document_id: str, request: ExportRequest):
    """Export a document in the requested format (pdf / html / json).
    Uses mock document/steps data for now — production will receive these from the DB.
    """
    doc = await store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        document = {
            "document_id": document_id,
            "title": doc.get("title", "Work Instruction Document"),
            "asset_id": doc.get("asset_id") or document_id,
            "procedure_id": doc.get("procedure_id") or "default_procedure",
            "revision": 1,
            "status": doc.get("status", "draft"),
        }

        steps = await store.list_steps(document_id)

        illustrations = {
            ill["step_id"]: ill
            for ill in await store.list_illustrations(document_id)
        }

        result = await agent.export(
            document=document,
            steps=steps,
            illustrations=illustrations,
            export_format=request.format,
            include_illustrations=request.include_illustrations,
        )

        return ExportResponse(
            export_id=result["export_id"],
            format=result["format"],
            status="completed",
            download_url=f"/api/v1/wig/documents/{document_id}/export/{result['export_id']}/download",
            file_size_bytes=result.get("file_size_bytes", 0),
        )
    except Exception as e:
        logger.error("Export failed: %s", e)
        raise HTTPException(status_code=500, detail="Export failed") from e


@router.get("/documents/{document_id}/export/{export_id}/download")
async def download_export(document_id: str, export_id: str):
    """Download a previously generated export."""
    record = await agent.find_export(document_id, export_id)
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")

    artifact_ref = record.get("artifact_ref")
    if not artifact_ref:
        raise HTTPException(status_code=404, detail="Export artifact missing")

    # Confine served files to the artifact root (artifact_ref is internal, but
    # a stored traversal value must not escape it).
    artifact_root = agent.json_exporter.artifact_path.resolve()
    artifact_path = Path(artifact_ref).resolve()
    if (
        not artifact_path.is_relative_to(artifact_root)
        or not artifact_path.is_file()
    ):
        raise HTTPException(
            status_code=404, detail="Export file not found on disk"
        )

    content_type = record.get("content_type", "application/octet-stream")
    filename = artifact_path.name

    return FileResponse(
        path=str(artifact_path), media_type=content_type, filename=filename
    )
