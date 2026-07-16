# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Context retrieval endpoints — GET /api/v1/context, /api/v1/procedure-context."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from fastapi import APIRouter, Query

from ..context_models import (
    ContextChunk,
    ContextResponse,
    ProcedureContextResponse,
    SOPEntry,
)
from ..sop_reference_agent import SOPReferenceAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["context"])

_AGENT = None
_AGENT_LOCK = threading.Lock()


def _get_agent():
    """Get the SOP reference agent (thread-safe, lazily constructed once)."""
    global _AGENT
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = SOPReferenceAgent()
    return _AGENT


# ── Procedure → machine mapping ───────────────────────────────────────────────

_PROCEDURE_MAP: dict[str, tuple[str, str, str]] = {
    # procedure_id           station_id            milvus_machine_id          station_name
    "cell_inspection": (
        "cell_tester",
        "nexora-ks200",
        "Nexora KS-200 Cell Tester",
    ),
    "cell_sorting": (
        "cell_tester",
        "nexora-ks200",
        "Nexora KS-200 Cell Tester",
    ),
    "module_bonding": (
        "dispenser",
        "veltrix-problu-gantry",
        "Veltrix Gantry Dispenser",
    ),
    "tab_busbar_welding": (
        "welder",
        "zyro-kr20-r1810",
        "ZYRO Fiber Laser Welder",
    ),
    "tim_application": (
        "tim_dispenser",
        "veltrix-problu-gantry",
        "Veltrix Gantry Dispenser",
    ),
    "enclosure_sealing": (
        "sealing_dispenser",
        "veltrix-problu-gantry",
        "Veltrix Gantry Dispenser",
    ),
    "hv_harness_routing": (
        "hv_bench",
        "zyro-assembly-tooling",
        "ZYRO Assembly Tooling",
    ),
    "leak_test_troubleshooting": (
        "leak_tester",
        "nexora-leak-test-system",
        "Nexora Leak Test System",
    ),
    "hipot_testing": (
        "hipot_tester",
        "nexora-hipot-tester",
        "Nexora Hi-Pot Tester",
    ),
    "eol_functional_test": (
        "eol_rig",
        "nexora-eol-test-system",
        "Nexora EOL Test System",
    ),
}

# Maps procedure machine_id → actual machine_id stored in machine_manuals collection.
# Modified manuals were re-ingested with consistent IDs — no remapping needed.
_OEM_MANUAL_MACHINE_ID: dict[str, str] = {}

_PROCEDURE_NAMES: dict[str, str] = {
    "cell_inspection": "CEL-001 Cell Inspection & Sorting",
    "cell_sorting": "CEL-001 Cell Sorting",
    "module_bonding": "MOD-002 Module Bonding & Adhesive",
    "tab_busbar_welding": "ELJ-003 Electrical Joining Laser Welding",
    "tim_application": "TIM-004 Thermal Interface Material Application",
    "enclosure_sealing": "ENC-006 Enclosure Sealing",
    "hv_harness_routing": "HVI-005 HV Integration & Harness Routing",
    "leak_test_troubleshooting": "LKT-007 Leak Testing",
    "hipot_testing": "HPT-008 Hi-Pot Insulation Testing",
    "eol_functional_test": "EOL-009 EOL Functional Test",
}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/context", response_model=ContextResponse)
async def get_context(
    query: str = Query(..., description="Natural language query"),
    machine_id: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    top_k: int = Query(5, ge=1, le=20),
) -> ContextResponse:
    """Search Milvus for chunks relevant to a query + optional machine filter."""
    try:
        raw = _get_agent()._retriever.search(
            query=query,
            machine_id=machine_id,
            document_type=document_type,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning("Context retrieval failed: %s", exc)
        raw = []

    collections_seen: list[str] = []
    chunks: list[ContextChunk] = []
    for c in raw:
        coll = c.get("collection", "unknown")
        if coll not in collections_seen:
            collections_seen.append(coll)
        chunks.append(
            ContextChunk(
                chunk_id=c.get("chunk_id") or "",
                document_name=c.get("document_name") or "",
                title=c.get("title") or "",
                vendor=c.get("vendor") or "",
                machine_id=c.get("machine_id") or "",
                document_type=c.get("document_type") or "",
                collection=coll,
                content=c.get("content_english") or "",
                page_number=c.get("page_number") or 0,
                source_anchor=c.get("source_anchor") or "",
                score=float(c.get("score", 0.0)),
            )
        )

    return ContextResponse(
        query=query,
        machine_id=machine_id,
        total=len(chunks),
        chunks=chunks,
        collections_searched=collections_seen,
    )


@router.get("/context/machines/{machine_id}", response_model=ContextResponse)
async def get_machine_context(
    machine_id: str,
    query: Optional[str] = Query(None),
    top_k: int = Query(8, ge=1, le=20),
) -> ContextResponse:
    """Broad context sweep for a specific machine."""
    try:
        ctx = _get_agent().retrieve_machine_context(
            machine_id=machine_id, query=query, top_k=top_k
        )
        raw = (
            ctx.get("procedure_chunks", [])
            + ctx.get("machine_manual_chunks", [])
            + ctx.get("sop_chunks", [])
        )
    except Exception as exc:
        logger.warning("Machine context failed for %s: %s", machine_id, exc)
        raw = []

    chunks = [
        ContextChunk(
            chunk_id=c.get("chunk_id") or "",
            document_name=c.get("source") or "",
            title="",
            vendor="",
            machine_id=machine_id,
            document_type=c.get("document_type") or "",
            collection=c.get("collection") or "unknown",
            content=c.get("text") or "",
            page_number=0,
            source_anchor="",
            score=float(c.get("score", 0.0)),
        )
        for c in raw
    ]
    return ContextResponse(
        query=query or f"{machine_id} context",
        machine_id=machine_id,
        total=len(chunks),
        chunks=chunks,
        collections_searched=list({c.collection for c in chunks}),
    )


@router.get("/procedure-context", response_model=ProcedureContextResponse)
async def get_procedure_context(
    procedure_id: str = Query(
        ...,
        description=(
            "One of: cell_inspection, module_bonding, tab_busbar_welding, "
            "tim_application, hv_harness_routing, enclosure_sealing, "
            "leak_test_troubleshooting, hipot_testing, eol_functional_test"
        ),
    ),
    station_id: Optional[str] = Query(None),
    top_k: int = Query(5, ge=1, le=20),
) -> ProcedureContextResponse:
    """Return structured SOP context for a selected procedure.

    Called by the frontend when the engineer selects a procedure. Resolves
    procedure_id → OEM machine_id → Milvus search → structured safety context.
    """
    entry = _PROCEDURE_MAP.get(procedure_id)
    resolved_station_id = station_id or (entry[0] if entry else procedure_id)
    milvus_machine_id = entry[1] if entry else resolved_station_id
    station_name = entry[2] if entry and not station_id else resolved_station_id
    procedure_name = _PROCEDURE_NAMES.get(
        procedure_id, procedure_id.replace("_", " ").title()
    )
    oem_machine_id = _OEM_MANUAL_MACHINE_ID.get(
        milvus_machine_id, milvus_machine_id
    )

    try:
        ctx = _get_agent().retrieve_context(
            query=f"{procedure_name} {milvus_machine_id} LOTO PPE safety warning procedure interlock",
            machine_id=milvus_machine_id,
            oem_machine_id=oem_machine_id,
            procedure_id=procedure_id,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning(
            "SOPReferenceAgent failed for %s/%s: %s",
            procedure_id,
            milvus_machine_id,
            exc,
        )
        ctx = {
            "procedure_chunks": [],
            "machine_manual_chunks": [],
            "sop_chunks": [],
            "safety_warnings": [],
            "loto_rules": [],
            "approved_terminology": {},
            "source_citations": [],
            "rag_retrieved": False,
            "chunk_count": 0,
        }

    def _to_sop_entry(s: dict) -> SOPEntry:
        return SOPEntry(
            chunk_id=s.get("chunk_id") or "",
            text=s.get("text") or "",
            source=s.get("source") or "",
            score=float(s.get("score", 0.0)),
            collection=s.get("collection") or "",
            machine_id=s.get("machine_id") or "",
            document_type=s.get("document_type") or "",
            document_name=s.get("document_name") or "",
            page_number=s.get("page_number") or 0,
        )

    return ProcedureContextResponse(
        procedure_id=procedure_id,
        procedure_name=procedure_name,
        station_id=resolved_station_id,
        station_name=station_name,
        machine_id=milvus_machine_id,
        rag_retrieved=ctx.get("rag_retrieved", False),
        chunk_count=ctx.get("chunk_count", 0),
        procedure_chunks=[
            _to_sop_entry(s) for s in ctx.get("procedure_chunks", [])
        ],
        machine_manual_chunks=[
            _to_sop_entry(s) for s in ctx.get("machine_manual_chunks", [])
        ],
        sop_chunks=[_to_sop_entry(s) for s in ctx.get("sop_chunks", [])],
        safety_warnings=ctx.get("safety_warnings", []),
        loto_rules=ctx.get("loto_rules", []),
        approved_terminology=ctx.get("approved_terminology", {}),
        source_citations=ctx.get("source_citations", []),
    )
