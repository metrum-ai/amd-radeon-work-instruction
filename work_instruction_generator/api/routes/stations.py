# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Station-state routes for WIG.

Supports listing configured stations, reading the latest mock simulator
state, and setting the simulator state for demos.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException

from work_instruction_generator.api.models import (
    MachineStateResponse,
    SimulatorStateUpdate,
    StationSummary,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wig", tags=["stations"])

_SIMULATOR_URL = os.environ.get(
    "SIMULATOR_URL", "http://machine-simulator:8000"
)

# Plan Section 3.4: all 8 EV battery stations
_STATIONS: list[dict[str, Any]] = [
    {
        "station_id": "cell_tester",
        "name": "OCV/IR Cell Tester",
        "procedure_area": "Cell inspection/sorting",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "dispenser",
        "name": "Nordson Dispenser",
        "procedure_area": "Module bonding",
        "state": "ready",
        "has_simulator": True,
    },
    {
        "station_id": "welder",
        "name": "KUKA Welder",
        "procedure_area": "Electrical joining",
        "state": "active",
        "has_simulator": True,
    },
    {
        "station_id": "tim_dispenser",
        "name": "TIM Dispenser",
        "procedure_area": "Thermal assembly",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "hv_bench",
        "name": "HV Integration Bench",
        "procedure_area": "HV integration",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "sealing_dispenser",
        "name": "Enclosure Sealing Dispenser",
        "procedure_area": "Enclosure sealing",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "leak_tester",
        "name": "Helium/Air Leak Tester",
        "procedure_area": "Leak testing",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "hipot_tester",
        "name": "Hi-Pot Insulation Tester",
        "procedure_area": "Hi-Pot testing",
        "state": "idle",
        "has_simulator": True,
    },
    {
        "station_id": "eol_rig",
        "name": "EOL Functional Rig",
        "procedure_area": "EOL functional test",
        "state": "idle",
        "has_simulator": True,
    },
]


async def _seed_station(sid: str, default_state: str) -> None:
    """Insert default idle state for a station if none exists yet."""
    if await store.get_machine_state(sid) is None:
        await store.add_machine_state(
            sid,
            {
                "state_id": str(uuid4()),
                "station_id": sid,
                "procedure_id": None,
                "source": "mock_simulator",
                "state": default_state,
                "active_alarms": [],
                "readiness_flags": {},
                "quality_readings": {},
                "last_completed_step": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )


@router.get("/stations", response_model=list[StationSummary])
async def list_stations() -> list[StationSummary]:
    """List the stations."""

    async def _summary(s: dict[str, Any]) -> StationSummary:
        # Each station is a distinct row, so seeding + reading them concurrently
        # is race-free and turns the previous per-station serial round trips
        # into a single parallel wave.
        await _seed_station(s["station_id"], s["state"])
        ms = await store.get_machine_state(s["station_id"])
        return StationSummary(
            station_id=s["station_id"],
            name=s["name"],
            procedure_area=s["procedure_area"],
            state=(ms or {}).get("state", s["state"]),
            has_simulator=s["has_simulator"],
        )

    return list(await asyncio.gather(*(_summary(s) for s in _STATIONS)))


@router.get("/stations/{station_id}/state", response_model=MachineStateResponse)
async def get_station_state(station_id: str) -> MachineStateResponse:
    """Get the state of a station."""
    cfg = next((s for s in _STATIONS if s["station_id"] == station_id), None)
    if cfg:
        await _seed_station(station_id, cfg["state"])
    ms = await store.get_machine_state(station_id)
    if ms is None:
        raise HTTPException(
            status_code=404, detail=f"Station '{station_id}' not found"
        )
    return MachineStateResponse(**ms)


@router.post(
    "/stations/{station_id}/simulate",
    response_model=MachineStateResponse,
)
async def simulate_station_state(
    station_id: str,
    update: SimulatorStateUpdate,
) -> MachineStateResponse:
    """Simulate the state of a station."""
    station_ids = {s["station_id"] for s in _STATIONS}
    if station_id not in station_ids:
        raise HTTPException(
            status_code=404, detail=f"Unknown station '{station_id}'"
        )

    snapshot = {
        "state_id": str(uuid4()),
        "station_id": station_id,
        "procedure_id": None,
        "source": "mock_simulator",
        "state": update.state,
        "active_alarms": update.active_alarms,
        "readiness_flags": update.readiness_flags,
        "quality_readings": update.quality_readings,
        "last_completed_step": update.last_completed_step,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await store.add_machine_state(station_id, snapshot)
    return MachineStateResponse(**snapshot)


@router.post("/machines/{machine_id}/fault-mode")
async def toggle_machine_fault_mode(machine_id: str) -> dict[str, bool]:
    """Toggle fault-prone mode on a simulator machine; proxied to the simulator service."""
    # Reject anything but a plain id so it can't manipulate the upstream URL path.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", machine_id):
        raise HTTPException(status_code=400, detail="Invalid machine_id")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_SIMULATOR_URL}/api/v1/machines/{machine_id}/fault-mode"
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Simulator fault-mode returned %s for %s",
            exc.response.status_code,
            machine_id,
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="Simulator rejected the fault-mode request",
        ) from exc
    except Exception as exc:
        logger.warning(
            "Simulator unreachable for fault-mode %s: %s", machine_id, exc
        )
        raise HTTPException(
            status_code=503, detail="Simulator unreachable"
        ) from exc
