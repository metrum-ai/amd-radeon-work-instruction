# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Generation, step, and dynamic-next-step routes for WIG.

Thin HTTP layer over the WorkInstructionOrchestrator, which routes jobs
through machine-state, interlock, authoring, and illustration agents.
Tracks generation progress through jobs.
"""

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from work_instruction_generator.agents.work_instruction_orchestrator import (
    orchestrator,
)
from work_instruction_generator.api import openclaw_client, workload_metrics
from work_instruction_generator.api.models import (
    DynamicInstructionRequest,
    GenerateRequest,
    GenerateResponse,
    GenerationStatus,
    RegenerateRequest,
    StepResponse,
    StepUpdate,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wig", tags=["generation"])

_LEMONADE_LB_URL = os.environ.get("WIG_LEMONADE_URL", "http://lemonade:13305")

# Matches the number of physical Flux/Lemonade GPU instances behind the LB (lemonade-1, lemonade-2).
# Firing more concurrent requests than this races nginx's least_conn: connection counts only
# increment once the upstream connection is actually established, so several requests dispatched
# within the same few milliseconds can all see a stale zero-count and pile onto the same backend.
# Capping client-side concurrency to the backend count avoids the race entirely.
_MAX_CONCURRENT_ILLUSTRATIONS = 2

# Route business logic through the real OpenClaw gateway's MCP tools (see
# work_instruction_generator/mcp/) instead of the WorkInstructionOrchestrator
# singleton's own HTTP-to-agent-container calls. Kept behind a flag so the
# old path (and its 3 agent-* containers) can run side-by-side during
# validation and be rolled back instantly if the gateway misbehaves.
_USE_OPENCLAW_GATEWAY = (
    os.environ.get("WIG_USE_OPENCLAW_GATEWAY", "false").lower() == "true"
)


async def _fetch_live_machine_state(
    station_id: str,
) -> Optional[dict[str, Any]]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__fetch_machine_state", {"station_id": station_id}
        )
    return await orchestrator.fetch_live_machine_state(station_id)


async def _fetch_procedure_context(
    procedure_id: str, top_k: int = 5
) -> dict[str, Any]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__fetch_procedure_context",
            {"procedure_id": procedure_id, "top_k": top_k},
        )
    return await orchestrator.fetch_procedure_context(procedure_id, top_k)


async def _evaluate_interlock(
    station_id: str, ms: dict[str, Any]
) -> dict[str, Any]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__evaluate_interlock",
            {"station_id": station_id, "machine_state": ms},
        )
    return orchestrator.evaluate_interlock(station_id, ms)


async def _plan_steps(
    source_evidence: dict[str, Any],
    sop_context: dict[str, Any],
    blocked_prereqs: list[str],
) -> list[dict[str, Any]]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__plan_steps",
            {
                "source_evidence": source_evidence,
                "sop_context": sop_context,
                "blocked_prereqs": blocked_prereqs,
            },
        )
    return await orchestrator.plan_steps(
        source_evidence, sop_context, blocked_prereqs=blocked_prereqs
    )


async def _call_agent(payload: dict[str, Any]) -> dict[str, Any]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__generate_step", payload
        )
    return await orchestrator.call_author(payload)


async def _call_illustrator(
    document_id: str,
    steps: list[dict[str, Any]],
    default_style: str = "technical_diagram",
) -> list[dict[str, Any]]:
    if _USE_OPENCLAW_GATEWAY:
        return await openclaw_client.invoke_tool(
            "wig-tools__generate_illustrations",
            {
                "document_id": document_id,
                "steps": steps,
                "default_style": default_style,
            },
        )
    return await orchestrator.call_illustrator(
        document_id, steps, default_style
    )


def _mock_steps(count: int = 3, prefix: str = "Step") -> list[dict[str, Any]]:
    """Generate simple mock steps when no agent is available."""
    import uuid

    steps = []
    for i in range(count):
        steps.append(
            {
                "step_id": str(uuid.uuid4()),
                "step_number": i + 1,
                "title": f"{prefix} {i + 1}",
                "instruction_text": f"Perform {prefix.lower()} {i + 1} according to plant SOP.",
                "tools_required": (
                    ["torque wrench", "multimeter"]
                    if i == 0
                    else ["torque wrench"]
                ),
                "parts_required": [],
                "safety_warnings": (
                    [
                        "Wear class-0 PPE",
                        "Verify LOTO is applied",
                    ]
                    if i == 0
                    else []
                ),
                "quality_checks": [],
                "source_citations": [],
                "terminology_mappings": {},
                "tribal_knowledge_refs": [],
                "interlock_status": "pass",
                "difficulty": "medium",
                "estimated_time_minutes": 5,
                "target_language": "en",
            }
        )
    return steps


async def _generate_illustrations_bg(
    document_id: str, steps: list[dict[str, Any]], style: str, job_id: str
) -> None:
    """Background task: generate illustrations for all steps concurrently,
    capped at _MAX_CONCURRENT_ILLUSTRATIONS in flight at a time.

    Previously looped one step at a time — that fed TechnicalIllustrationAgent's
    internal asyncio.gather a single-item list every call, so the two Flux
    backends never actually ran jobs in parallel. Firing all steps at once
    (uncapped) fixed that but re-introduced a different problem: nginx's
    least_conn only increments a backend's connection count once the upstream
    connection is actually established, so several requests dispatched within
    the same few milliseconds can all see a stale zero-count and pile onto the
    same backend before it corrects. Capping concurrency to the physical
    backend count avoids the race — at most 2 requests are ever in flight, so
    each new one always sees an accurate, already-settled connection count.
    """
    import traceback

    total = len(steps)
    logger.info(
        "Illustration background task START for %s (%d steps)",
        document_id,
        total,
    )
    completed = 0
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_ILLUSTRATIONS)

    async def _one(step: dict[str, Any]) -> None:
        nonlocal completed
        async with semaphore:
            workload_metrics.record_illustration_start(_LEMONADE_LB_URL)
            try:
                illustrations = await _call_illustrator(
                    document_id, [step], style
                )
                for ill in illustrations:
                    await store.add_illustration(ill)
                # Ground truth from nginx's X-Upstream-Addr header (set on the LB in
                # config/nginx.conf), not a guess — see workload_metrics.instance_from_upstream_addr.
                instance = None
                if illustrations:
                    instance = workload_metrics.instance_from_upstream_addr(
                        illustrations[0].get("lemonade_instance")
                    )
                workload_metrics.record_illustration_complete(
                    _LEMONADE_LB_URL,
                    instance,
                )
            except BaseException:
                workload_metrics.record_illustration_failed(_LEMONADE_LB_URL)
                raise
        completed += 1
        await store.update_job(
            job_id,
            {
                "current_step": f"illustration:{completed}/{total}",
                "progress_percent": 80 + int(completed / max(total, 1) * 20),
            },
        )

    try:
        await asyncio.gather(*[_one(step) for step in steps])
        await store.update_job(
            job_id, {"current_step": None, "progress_percent": 100}
        )
        logger.info(
            "Illustration background task DONE for %s (%d images)",
            document_id,
            total,
        )
    except BaseException as exc:
        logger.error(
            "Background illustration FAILED for %s: %s\n%s",
            document_id,
            exc,
            traceback.format_exc(),
        )


# ── Generate ────────────────────────────────────────────────────────────────


@router.post(
    "/documents/{document_id}/generate",
    response_model=GenerateResponse,
)
async def generate_steps(
    document_id: str,
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
) -> GenerateResponse:
    """Start generating instructions for a document."""
    doc = await store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    job = await store.create_job(document_id)
    await store.update_document(document_id, {"status": "generating"})
    job_id = job["job_id"]

    _llm_model = os.environ.get("AGENT_LLM_MODEL", "language-model")
    _translate_model = os.environ.get("AGENT_TRANSLATE_MODEL", "language-model")

    # Source Document Agent — loading sources and procedure context
    await store.update_job(
        job_id,
        {
            "current_step": "source_document:0/1",
            "progress_percent": 5,
            "context": {
                "doc_title": doc.get("title", ""),
                "llm_model": _llm_model,
                "translate_model": _translate_model,
            },
        },
    )

    sources = await store.list_sources(document_id)

    # Fetch procedure context from RAG service (non-blocking; falls back to empty on failure)
    procedure_id = doc.get("procedure_id") or ""
    proc_context = await _fetch_procedure_context(procedure_id)
    procedure_chunks = proc_context.get("procedure_chunks", [])
    sop_chunks = proc_context.get("sop_chunks", [])
    machine_manual_chunks = proc_context.get("machine_manual_chunks", [])

    # Procedure Context agent
    await store.update_job(
        job_id,
        {
            "current_step": "procedure_context:1/1",
            "progress_percent": 20,
            "context": {
                "doc_title": doc.get("title", ""),
                "procedure_name": proc_context.get(
                    "procedure_name", procedure_id
                )
                or procedure_id,
                "proc_chunks": len(procedure_chunks),
                "sop_chunks": len(sop_chunks),
                "manual_chunks": len(machine_manual_chunks),
                "llm_model": _llm_model,
                "translate_model": _translate_model,
            },
        },
    )

    # Machine State Agent — use snapshot only when its station_id matches the resolved station
    # (the SSE snapshot is always for hv_integration_bench; other stations must be fetched live
    # so get_station_state() can merge the correct machine-specific readiness flags).
    station_id = proc_context.get("station_id", "") or doc.get("station_id", "")
    snapshot = req.machine_state_snapshot or {}
    snapshot_station = (
        snapshot.get("station_id", "") if isinstance(snapshot, dict) else ""
    )
    if snapshot and station_id and snapshot_station == station_id:
        machine_state = snapshot
    else:
        machine_state = (
            await _fetch_live_machine_state(station_id) if station_id else None
        )
    interlock_result = (
        await _evaluate_interlock(station_id, machine_state or {})
        if station_id
        else None
    )

    await store.update_job(
        job_id,
        {
            "current_step": "machine_state:1/1",
            "progress_percent": 28,
            "context": {
                "doc_title": doc.get("title", ""),
                "procedure_name": proc_context.get(
                    "procedure_name", procedure_id
                )
                or procedure_id,
                "station_id": station_id,
                "machine_id": proc_context.get("machine_id", ""),
                "machine_state": (machine_state or {}).get("state", "unknown"),
                "active_alarms": len(
                    (machine_state or {}).get("active_alarms", [])
                ),
                "readiness_flags": (machine_state or {}).get(
                    "readiness_flags", {}
                ),
                "quality_readings": (machine_state or {}).get(
                    "quality_readings", {}
                ),
                "proc_chunks": len(procedure_chunks),
                "sop_chunks": len(sop_chunks),
                "manual_chunks": len(machine_manual_chunks),
                "llm_model": _llm_model,
                "translate_model": _translate_model,
            },
        },
    )

    # SOP Reference Agent
    await store.update_job(
        job_id,
        {
            "current_step": "sop_reference:1/1",
            "progress_percent": 35,
            "context": {
                "doc_title": doc.get("title", ""),
                "procedure_name": proc_context.get(
                    "procedure_name", procedure_id
                )
                or procedure_id,
                "station_id": station_id,
                "machine_id": proc_context.get("machine_id", ""),
                "machine_state": (machine_state or {}).get("state", "unknown"),
                "active_alarms": len(
                    (machine_state or {}).get("active_alarms", [])
                ),
                "safety_warnings": len(proc_context.get("safety_warnings", [])),
                "loto_rules": len(proc_context.get("loto_rules", [])),
                "proc_chunks": len(procedure_chunks),
                "sop_chunks": len(sop_chunks),
                "manual_chunks": len(machine_manual_chunks),
                "llm_model": _llm_model,
                "translate_model": _translate_model,
            },
        },
    )

    sop_context: dict[str, Any] = {
        "safety_warnings": proc_context.get("safety_warnings", []),
        "loto_rules": proc_context.get("loto_rules", []),
        "approved_terminology": proc_context.get("approved_terminology", {}),
        "relevant_sops": sop_chunks,
    }

    # VLM-analyzed image descriptions from OEM manuals — used to ground illustration prompts
    visual_refs: list[str] = [
        c.get("text", "")
        for c in machine_manual_chunks
        if c.get("element_type") == "image_explanation" and c.get("text")
    ]
    # Fall back to all manual text chunks if no image explanations were ingested yet
    if not visual_refs:
        visual_refs = [
            c.get("text", "") for c in machine_manual_chunks if c.get("text")
        ]
    source_evidence: dict[str, Any] = {
        "document_id": document_id,
        "procedure_name": proc_context.get("procedure_name", procedure_id),
        "station_id": station_id,
        "machine_id": proc_context.get("machine_id", ""),
        "procedure_outline": [
            {"source_citation": c.get("source", ""), "text": c.get("text", "")}
            for c in procedure_chunks
        ],
        "machine_manual_refs": [
            {"source_citation": c.get("source", ""), "text": c.get("text", "")}
            for c in machine_manual_chunks
        ],
        "machine_state_context": (
            {
                "state": (machine_state or {}).get("state", "unknown"),
                "active_alarms": (machine_state or {}).get("active_alarms", []),
                "readiness_flags": (machine_state or {}).get(
                    "readiness_flags", {}
                ),
                "quality_readings": (machine_state or {}).get(
                    "quality_readings", {}
                ),
                "last_completed_step": (machine_state or {}).get(
                    "last_completed_step"
                ),
            }
            if machine_state
            else None
        ),
    }

    # Clear stale sources then persist unique source documents from RAG
    await store.delete_sources(document_id)
    _COLLECTION_URL: dict[str, str] = {
        "procedure_docs": "/procedure-docs",
        "sop_docs": "/sop-docs",
        "machine_manuals": "/manuals",
    }
    all_chunks = procedure_chunks + sop_chunks + machine_manual_chunks
    seen_docs: set = set()
    for chunk in all_chunks:
        doc_name = chunk.get("document_name") or chunk.get("source", "")
        if not doc_name or doc_name in seen_docs:
            continue
        seen_docs.add(doc_name)
        collection = chunk.get("collection", "")
        url_prefix = _COLLECTION_URL.get(collection, "")
        pdf_url = f"{url_prefix}/{doc_name}.pdf" if url_prefix else ""
        try:
            await store.add_source(
                doc_id=document_id,
                file_name=doc_name,
                file_type="pdf",
                file_size_bytes=0,
                vendor_name=chunk.get("machine_id") or None,
                artifact_ref=pdf_url,
                extracted_metadata={
                    "collection": collection,
                    "page_number": chunk.get("page_number"),
                    "document_type": chunk.get("document_type", ""),
                },
            )
        except Exception as exc:
            logger.debug(
                "Source artifact insert skipped (%s): %s", doc_name, exc
            )

    _base_ctx: dict[str, Any] = {
        "doc_title": doc.get("title", ""),
        "procedure_name": proc_context.get("procedure_name", procedure_id)
        or procedure_id,
        "station_id": station_id,
        "machine_id": proc_context.get("machine_id", ""),
        "machine_state": (machine_state or {}).get("state", "unknown"),
        "active_alarms": len((machine_state or {}).get("active_alarms", [])),
        "readiness_flags": (machine_state or {}).get("readiness_flags", {}),
        "quality_readings": (machine_state or {}).get("quality_readings", {}),
        "safety_warnings": len(proc_context.get("safety_warnings", [])),
        "loto_rules": len(proc_context.get("loto_rules", [])),
        "proc_chunks": len(procedure_chunks),
        "sop_chunks": len(sop_chunks),
        "manual_chunks": len(machine_manual_chunks),
        "llm_model": _llm_model,
        "translate_model": _translate_model,
        "interlock_status": (interlock_result or {}).get("status", "pass"),
        "interlock_reasons": (interlock_result or {}).get(
            "blocked_reasons", []
        ),
    }

    try:
        await store.update_job(
            job_id,
            {
                "current_step": "orchestrator:1/1",
                "progress_percent": 38,
                "context": _base_ctx,
            },
        )
        await store.update_job(
            job_id,
            {
                "current_step": "safety_interlock:1/1",
                "progress_percent": 45,
                "context": _base_ctx,
            },
        )

        is_blocked = bool(
            interlock_result and interlock_result.get("status") == "blocked"
        )
        blocked_prereqs = (
            interlock_result.get("required_actions", []) if is_blocked else []
        )

        step_descriptions = await _plan_steps(
            source_evidence, sop_context, blocked_prereqs
        )

        # plan_steps now returns list[{"desc": str, "prereq": bool}].
        # Normalise in case of old plain-string format.
        normalised: list[dict[str, Any]] = []
        for s in step_descriptions:
            if isinstance(s, dict):
                normalised.append(
                    {
                        "desc": str(s.get("desc", "")),
                        "prereq": bool(s.get("prereq", False)),
                    }
                )
            elif isinstance(s, str):
                normalised.append({"desc": s, "prereq": False})
        # Deduplicate by lowercased desc, then cap at 20 steps total
        _seen_descs: set = set()
        _deduped: list[dict[str, Any]] = []
        for _s in normalised:
            _key = _s["desc"].lower().strip()
            if _key not in _seen_descs:
                _seen_descs.add(_key)
                _deduped.append(_s)
        step_descriptions = _deduped[:20]
        step_count = len(step_descriptions)

        await store.update_job(
            job_id,
            {
                "status": "generating",
                "steps_total": step_count,
                "current_step": f"instruction_author:0/{step_count}",
                "context": {**_base_ctx, "steps_planned": step_count},
            },
        )

        await store.delete_steps(document_id)
        completed = 0

        async def _author_one(
            i: int, step_def: dict[str, Any]
        ) -> dict[str, Any]:
            nonlocal completed
            clean_description = step_def["desc"]
            step_is_prereq = step_def[
                "prereq"
            ]  # set by LLM via boolean field — reliable
            # Previous-step context comes from the pre-planned description (known upfront
            # from plan_steps), not the previously *generated* title — this lets all steps
            # be authored concurrently across both LLM backends instead of one at a time.
            previous_summary = (
                step_descriptions[i - 1]["desc"] if i > 0 else "None"
            )

            step = await _call_agent(
                {
                    "step_number": i + 1,
                    "step_description": clean_description,
                    "source_evidence": source_evidence,
                    "sop_context": sop_context,
                    "machine_state": machine_state,
                    # Never pass blocked interlock to the author — it would suppress normal step content.
                    # Interlock status is stamped after generation based on step_is_prereq.
                    "interlock_result": None,
                    "target_language": req.target_language,
                    "target_audience": req.target_audience,
                    "total_steps": step_count,
                    "previous_step_summary": previous_summary,
                }
            )
            if step_is_prereq:
                step["interlock_status"] = "blocked"
                step["skip_illustration"] = True
            step["visual_refs"] = visual_refs
            await store.add_step(document_id, step)
            completed += 1
            await store.update_job(
                job_id,
                {
                    "current_step": f"instruction_author:{completed}/{step_count}",
                    "steps_completed": completed,
                    "progress_percent": int(completed / step_count * 80),
                    "context": {
                        **_base_ctx,
                        "steps_planned": step_count,
                        "current_step_desc": clean_description,
                    },
                },
            )
            return step

        steps = await asyncio.gather(
            *[
                _author_one(i, step_def)
                for i, step_def in enumerate(step_descriptions)
            ]
        )

        await store.update_document(document_id, {"status": "generated"})
        await store.update_job(
            job_id,
            {
                "status": "completed",
                "progress_percent": 80,
                "steps_completed": step_count,
                "steps_total": step_count,
                "current_step": f"illustration:0/{step_count}",
            },
        )
    except Exception as exc:
        logger.error("Generation failed for %s: %s", document_id, exc)
        await store.update_document(document_id, {"status": "draft"})
        await store.update_job(
            job_id, {"status": "failed", "progress_percent": 0}
        )
        raise HTTPException(
            status_code=500, detail="Generation failed"
        ) from exc

    # Launch TechnicalIllustrationAgent after the response is sent.
    # Skip prereq-resolution steps (skip_illustration=True) — no image needed for safety checks.
    illustratable_steps = [s for s in steps if not s.get("skip_illustration")]
    background_tasks.add_task(
        _generate_illustrations_bg,
        document_id,
        illustratable_steps,
        req.illustration_style,
        job_id,
    )

    return GenerateResponse(
        job_id=job_id,
        status="completed",
        progress_percent=100,
        current_step="Finalising",
    )


# ── Generation status ───────────────────────────────────────────────────────


@router.get(
    "/documents/{document_id}/status",
    response_model=GenerationStatus,
)
async def get_generation_status(document_id: str) -> GenerationStatus:
    """Get the generation status for a document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    job = await store.find_job_for_document(document_id)
    if job is None:
        return GenerationStatus(
            job_id="",
            status="not_started",
            progress_percent=0,
            steps_completed=0,
            steps_total=0,
        )
    return GenerationStatus(**job)


# ── Dynamic next-step ───────────────────────────────────────────────────────


@router.post(
    "/documents/{document_id}/dynamic-next-step",
    response_model=StepResponse,
)
async def dynamic_next_step(
    document_id: str,
    req: DynamicInstructionRequest,
) -> StepResponse:
    """Generate a single current-state-aware dynamic instruction.

    Reads the latest machine state for the requested station, evaluates
    hard interlocks from the plan config, and generates one step that
    reflects the current simulator state.
    """
    doc = await store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    ms = await _fetch_live_machine_state(req.station_id)
    if ms is None:
        raise HTTPException(
            status_code=404,
            detail=f"No state found for station '{req.station_id}'",
        )

    interlock_result: dict[str, Any] = await _evaluate_interlock(
        req.station_id, ms
    )

    try:
        step = await _call_agent(
            {
                "step_number": 1,
                "step_description": f"Perform {req.procedure_id} on {req.station_id}",
                "source_evidence": {"document_id": document_id},
                "sop_context": {},
                "machine_state": ms,
                "interlock_result": interlock_result,
                "target_language": req.target_language,
                "target_audience": req.target_audience,
                "total_steps": 1,
            }
        )
        await store.add_step(document_id, step)
        return StepResponse(**step)
    except Exception as exc:
        logger.warning("Dynamic agent call failed (%s), using mock step.", exc)
        mock = _mock_steps(count=1, prefix="Dynamic")[0]
        mock["machine_state_ref"] = ms.get("state_id")
        mock["interlock_status"] = interlock_result.get("status", "pass")
        mock["degraded"] = True
        mock["llm_status"] = "offline"
        await store.add_step(document_id, mock)
        return StepResponse(**mock)


# ── Step CRUD ───────────────────────────────────────────────────────────────


@router.get(
    "/documents/{document_id}/steps",
    response_model=list[StepResponse],
)
async def list_steps(document_id: str) -> list[StepResponse]:
    """List the steps for a document."""
    if await store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    steps = await store.list_steps(document_id)
    results = []
    for s in steps:
        ill = await store.get_illustration_by_step(s["step_id"])
        sp = StepResponse(
            **s,
            illustration_url=ill.get("artifact_ref") if ill else None,
        )
        results.append(sp)
    return results


@router.put(
    "/documents/{document_id}/steps/{step_id}",
    response_model=StepResponse,
)
async def update_step(
    document_id: str,
    step_id: str,
    updates: StepUpdate,
) -> StepResponse:
    """Update a step."""
    updated = await store.update_step(
        document_id, step_id, updates.model_dump(exclude_none=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Step not found")
    ill = await store.get_illustration_by_step(step_id)
    return StepResponse(
        **updated,
        illustration_url=ill.get("artifact_ref") if ill else None,
    )


async def _regenerate_illustration_for_step_bg(
    document_id: str, step: dict[str, Any]
) -> None:
    """Background task: regenerate illustration for a single step after refine."""
    workload_metrics.record_illustration_start(_LEMONADE_LB_URL)
    try:
        illustrations = await _call_illustrator(
            document_id, [step], "technical_diagram"
        )
        for ill in illustrations:
            await store.add_illustration(ill)
        instance = None
        if illustrations:
            instance = workload_metrics.instance_from_upstream_addr(
                illustrations[0].get("lemonade_instance")
            )
        workload_metrics.record_illustration_complete(
            _LEMONADE_LB_URL,
            instance,
        )
    except Exception as exc:
        workload_metrics.record_illustration_failed(_LEMONADE_LB_URL)
        logger.warning(
            "Illustration re-gen failed for step %s: %s",
            step.get("step_id"),
            exc,
        )


@router.post(
    "/documents/{document_id}/steps/{step_id}/regenerate",
    response_model=StepResponse,
)
async def regenerate_step(
    document_id: str,
    step_id: str,
    background_tasks: BackgroundTasks,
    req: Optional[RegenerateRequest] = None,
) -> StepResponse:
    """Regenerate a specific step, optionally with new description/language."""
    existing = await store.get_step(document_id, step_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Step not found")

    req = req or RegenerateRequest()
    description = req.step_description or existing.get(
        "instruction_text", "Regenerate step"
    )
    language = req.target_language or existing.get("target_language", "en")
    # target_audience is not persisted on steps, so there's nothing to read back
    # from `existing` — honor the request value or default to operator.
    audience = req.target_audience or "operator"

    # Re-fetch procedure context so the refined step gets real RAG safety warnings.
    # Fall back to the existing step's warnings if the fetch fails.
    doc = await store.get_document(document_id) or {}
    procedure_id = doc.get("procedure_id", "")
    proc_ctx = (
        await _fetch_procedure_context(procedure_id) if procedure_id else {}
    )
    sop_ctx: dict[str, Any] = {
        "safety_warnings": proc_ctx.get(
            "safety_warnings", existing.get("safety_warnings", [])
        ),
        "loto_rules": proc_ctx.get("loto_rules", []),
        "approved_terminology": proc_ctx.get("approved_terminology", {}),
        "relevant_sops": proc_ctx.get("sop_chunks", []),
    }

    degraded = False
    try:
        new_step: dict[str, Any] = await _call_agent(
            {
                "step_number": existing["step_number"],
                "step_description": description,
                "source_evidence": {"document_id": document_id},
                "sop_context": sop_ctx,
                "target_language": language,
                "target_audience": audience,
                "total_steps": len(await store.list_steps(document_id)),
                # Only a real refine (user supplied new instruction text) should
                # edit the existing step — a bare regenerate (no new text) already
                # uses the existing text as step_description above.
                "existing_instruction_text": (
                    existing.get("instruction_text")
                    if req.step_description
                    else None
                ),
            }
        )
        new_step["step_id"] = step_id  # preserve original id
        await store.update_step(document_id, step_id, new_step)
    except Exception as exc:
        logger.warning(
            "Regenerate agent call failed (%s), using fallback.", exc
        )
        degraded = True
        await store.update_step(
            document_id,
            step_id,
            {
                "instruction_text": f"[Regenerated] {description}",
                "target_language": language,
            },
        )

    updated = await store.get_step(document_id, step_id)

    # Re-generate illustration in the background if this step previously had one.
    # The response returns the old URL immediately; the new image replaces it once Flux finishes.
    ill = await store.get_illustration_by_step(step_id)
    if ill:
        background_tasks.add_task(
            _regenerate_illustration_for_step_bg, document_id, updated
        )

    return StepResponse(
        **updated,
        illustration_url=ill.get("artifact_ref") if ill else None,
        degraded=degraded,
        llm_status="offline" if degraded else "ok",
    )
