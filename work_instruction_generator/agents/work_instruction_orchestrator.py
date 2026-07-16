# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""WorkInstructionOrchestrator — routes WIG jobs through state, SOP, interlock,
authoring, and illustration agents.

Extracted from api/routes/generation.py so the pipeline routing described in
plans/04_WIG_WORK_INSTRUCTION_GENERATOR.plan.md section 6.1 lives in an
OpenClaw-addressable agent module instead of inline route handlers. Behavior
is unchanged: routes/generation.py now delegates here rather than duplicating
this logic.

Exposed to the OpenClaw gateway as MCP tools:
work_instruction_generator/mcp/tools/machine_state.py,
procedure_context.py
"""

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

import httpx

from work_instruction_generator.agents.instruction_author_agent import (
    InstructionAuthorAgent,
)
from work_instruction_generator.agents.technical_illustration_agent import (
    TechnicalIllustrationAgent,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

# Agent-server URLs from env (set by docker-compose), fall back to inline for dev
_AUTHOR_URL = os.environ.get("AGENT_INSTRUCTION_AUTHOR_URL", "")
_ILLUSTRATOR_URL = os.environ.get("AGENT_ILLUSTRATION_URL", "")
_HTTP_TIMEOUT = 120.0
_ILLUSTRATOR_TIMEOUT = 600.0
# OEM ingest / RAG service that provides procedure context
_CONTEXT_URL = os.environ.get("PROCEDURE_CONTEXT_URL", "http://localhost:8080")
_SIMULATOR_URL = os.environ.get(
    "SIMULATOR_URL", "http://machine-simulator:8000"
)

# Human-readable labels for every readiness flag the simulator can emit.
# Any flag reported as False by the machine state triggers a blocked reason.
_READINESS_FLAG_LABELS: dict[str, tuple] = {
    "loto_verified": (
        "LOTO not verified",
        "Verify LOTO is applied before proceeding",
    ),
    "ppe_class_0_confirmed": (
        "Class-0 PPE not confirmed",
        "Don class-0 PPE before entering HV zone",
    ),
    "hv_de_energized": (
        "HV circuit not de-energized",
        "De-energize HV circuit before proceeding",
    ),
    "msd_state_safe": (
        "MSD not in safe state",
        "Verify manual service disconnect is in safe position",
    ),
    "torque_tool_calibrated": (
        "Torque tool not calibrated",
        "Calibrate torque tool before use",
    ),
    "lens_clean": (
        "Lens not clean",
        "Execute lens clean cycle and confirm completion",
    ),
    "purge_complete": (
        "Nozzle purge not completed",
        "Complete nozzle purge cycle before dispensing",
    ),
    "fixture_locked": ("Fixture not locked", "Lock fixture before starting"),
    "fixture_clamped": (
        "Fixture not clamped",
        "Clamp fixture before proceeding",
    ),
    "laser_aligned": (
        "Laser not aligned",
        "Verify laser alignment before welding",
    ),
    "shield_gas_ok": (
        "Shielding gas not OK",
        "Verify shielding gas supply and flow rate",
    ),
    "head_homed": (
        "Dispenser head not homed",
        "Home the dispenser head before operation",
    ),
    "bead_sensor_cal": (
        "Bead sensor not calibrated",
        "Calibrate bead width sensor before dispensing",
    ),
    "calibrated": (
        "System not calibrated",
        "Run calibration sequence before proceeding",
    ),
    "focus_locked": ("Focus not locked", "Lock focus before scanning"),
}


def _json_safe(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable values (datetime → ISO string)."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


class WorkInstructionOrchestrator:
    """Routes WIG generation jobs through state, SOP, interlock, authoring,
    and illustration agents.

    Responsibilities (plan section 6.1):
    - Coordinate multiple OEM source files as one source set
    - Read runtime machine state and evaluate hard interlocks before authoring
    - Route source evidence + SOP context + machine state through
      InstructionAuthorAgent
    - Hand generated steps to TechnicalIllustrationAgent
    - Track progress via the job store
    """

    async def fetch_live_machine_state(
        self, station_id: str
    ) -> Optional[dict[str, Any]]:
        """Fetch machine state from the live simulator; fall back to last stored snapshot."""
        if not station_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_SIMULATOR_URL}/api/v1/stations/{station_id}/state"
                )
                resp.raise_for_status()
                data = resp.json()
                await store.add_machine_state(station_id, data)
                return data
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "Simulator unreachable for %s (%s) — falling back to stored state",
                station_id,
                exc,
            )
            return await store.get_machine_state(station_id)

    async def fetch_procedure_context(
        self, procedure_id: str, top_k: int = 5
    ) -> dict[str, Any]:
        """Fetch RAG procedure context from the OEM ingest service.

        Returns the full response dict on success, or an empty fallback so callers
        don't need to guard against None.
        """
        if not procedure_id:
            return {}
        try:
            url = f"{_CONTEXT_URL}/api/v1/procedure-context"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url, params={"procedure_id": procedure_id, "top_k": top_k}
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "procedure-context fetch failed (%s) — proceeding without RAG context",
                exc,
            )
            return {}

    def evaluate_interlock(
        self, station_id: str, ms: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate interlocks directly from machine readiness_flags reported by the simulator.

        Fully data-driven: any flag the machine reports as False becomes a blocked reason.
        No station-ID hardcoding — the machine state IS the interlock truth.
        """
        blocked_reasons: list[str] = []
        required_actions: list[str] = []

        logger.debug(
            "Evaluating interlock for station_id=%s", station_id
        )

        readiness_flags = (ms or {}).get("readiness_flags") or {}
        if not readiness_flags:
            # Fail CLOSED: absence of machine state (simulator unreachable →
            # empty/None ms) must never authorize proceeding on a safety path.
            logger.warning(
                "Interlock for %s: no readiness_flags — blocking (fail-closed)",
                station_id,
            )
            return {
                "status": "blocked",
                "blocked_reasons": ["Machine state unavailable"],
                "required_actions": [
                    "Verify machine connectivity and confirm station readiness "
                    "before proceeding"
                ],
            }

        for flag, value in readiness_flags.items():
            # Fail safe: any falsy/missing reading (False, 0, "", None) blocks.
            # Real simulator flags are booleans, so pass/block is unchanged for
            # valid input — this only hardens against degraded payloads.
            if not value:
                reason, action = _READINESS_FLAG_LABELS.get(
                    flag,
                    (
                        f"{flag} not ready",
                        f"Resolve '{flag}' before proceeding",
                    ),
                )
                blocked_reasons.append(reason)
                required_actions.append(action)

        return {
            "status": "blocked" if blocked_reasons else "pass",
            "blocked_reasons": blocked_reasons,
            "required_actions": required_actions,
        }

    async def call_author(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Issue a generation instruction to the InstructionAuthorAgent.

        Tries the HTTP agent-server first (when deployed via docker-compose),
        falls back to inline instantiation for local dev / testing.
        """
        if _AUTHOR_URL:
            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    resp = await client.post(
                        f"{_AUTHOR_URL}/run/generate_step",
                        json=_json_safe(payload),
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    if body.get("status") == "ok":
                        return body["result"]
                    logger.warning(
                        "Agent server returned non-ok status: %s", body
                    )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning(
                    "Agent-server call failed (%s), falling back inline", exc
                )

        agent = InstructionAuthorAgent()
        step = await agent.generate_step(
            step_number=payload.get("step_number", 1),
            step_description=payload.get(
                "step_description", "Perform operation"
            ),
            source_evidence=payload.get("source_evidence", {}),
            sop_context=payload.get("sop_context", {}),
            machine_state=payload.get("machine_state"),
            interlock_result=payload.get("interlock_result"),
            target_language=payload.get("target_language", "en"),
            target_audience=payload.get("target_audience", "operator"),
            total_steps=payload.get("total_steps", 1),
            previous_step_summary=payload.get("previous_step_summary", "None"),
            existing_instruction_text=payload.get("existing_instruction_text"),
        )
        return step  # type: ignore[return-value]

    async def plan_steps(
        self,
        source_evidence: dict[str, Any],
        sop_context: dict[str, Any],
        blocked_prereqs: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Ask the InstructionAuthorAgent to decompose the procedure into ordered steps.

        Tries the HTTP agent-server first, falls back to inline instantiation.
        Returns a list of {"desc": str, "prereq": bool} dicts.
        """
        if _AUTHOR_URL:
            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    resp = await client.post(
                        f"{_AUTHOR_URL}/run/plan_steps",
                        json={
                            "source_evidence": _json_safe(source_evidence),
                            "sop_context": _json_safe(sop_context),
                            "blocked_prereqs": blocked_prereqs or [],
                        },
                    )
                    resp.raise_for_status()
                    return resp.json().get("result", [])
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning(
                    "plan_steps agent-server call failed (%s), falling back "
                    "inline",
                    exc,
                )

        return await InstructionAuthorAgent().plan_steps(
            source_evidence,
            sop_context,
            blocked_prereqs=blocked_prereqs or None,
        )

    async def call_illustrator(
        self,
        document_id: str,
        steps: list[dict[str, Any]],
        default_style: str = "technical_diagram",
    ) -> list[dict[str, Any]]:
        """Feed generated steps to the TechnicalIllustrationAgent.

        Returns illustration dicts (one per step), or empty list on total failure.
        """
        if _ILLUSTRATOR_URL:
            try:
                async with httpx.AsyncClient(
                    timeout=_ILLUSTRATOR_TIMEOUT
                ) as client:
                    resp = await client.post(
                        f"{_ILLUSTRATOR_URL}/run/process",
                        json={
                            "document_id": document_id,
                            "steps": steps,
                            "default_style": default_style,
                        },
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    if body.get("status") == "ok":
                        return body["result"]
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning(
                    "Illustrator server call failed (%s), falling back inline",
                    exc,
                )

        agent = TechnicalIllustrationAgent()
        return await agent.process(document_id, steps, default_style)


# Module-level singleton — orchestrator holds no per-request state.
orchestrator = WorkInstructionOrchestrator()
