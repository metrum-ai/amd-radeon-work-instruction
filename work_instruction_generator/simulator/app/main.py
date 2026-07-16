# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Main application for the machine simulator."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .publisher import SparkplugPublisher
from .simulator import MachineSimulator


class AlarmModel(BaseModel):
    """Alarm model."""

    code: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str | None = None


class GaugeModel(BaseModel):
    """Gauge model."""

    key: str
    label: str
    value: float
    unit: str
    max: float


class MachineDocModel(BaseModel):
    """Machine document model."""

    doc_id: str
    file_name: str
    display_name: str
    file_type: str
    language: str
    pages: int | None = None


PackMLStatus = Literal[
    "Execute", "Idle", "Starting", "Completing", "Complete", "Held", "Aborted"
]


class MachineModel(BaseModel):
    """Machine model."""

    id: str
    name: str
    vendor: str
    origin: str
    type: str
    serial_number: str
    firmware_version: str
    install_date: str
    cycles_completed: int
    hours_run: float
    status: PackMLStatus
    gauges: list[GaugeModel]
    readiness: dict[str, bool]
    fault_prone: bool = False
    docs: list[MachineDocModel]


class StationStateModel(BaseModel):
    """Station state model."""

    state_id: str
    station_id: str
    procedure_id: str | None = None
    source: str
    state: str
    active_alarms: list[AlarmModel]
    readiness_flags: dict[str, bool]
    quality_readings: dict[str, str | float | int]
    last_completed_step: str | None = None
    created_at: str


class SnapshotModel(BaseModel):
    """Snapshot model."""

    sampled_at: str
    simulator_uptime_seconds: float
    machines: list[MachineModel]
    station_state: StationStateModel


class HistoryPointModel(BaseModel):
    """History point model."""

    timestamp: str
    status: str
    gauges: list[GaugeModel]
    readiness: dict[str, bool]


class MachineHistoryModel(BaseModel):
    """Machine history model."""

    machine_id: str
    interval_seconds: float
    samples: int
    history: list[HistoryPointModel]


simulator = MachineSimulator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan for the application."""
    publisher = SparkplugPublisher(
        broker_host=os.getenv("MQTT_HOST", "mosquitto"),
        broker_port=int(os.getenv("MQTT_PORT", "1883")),
        simulator=simulator,
    )
    publisher.start()
    try:
        yield
    finally:
        publisher.stop()


app = FastAPI(
    title="Machine Simulator Service",
    version="0.1.0",
    description="Standalone synthetic machine simulator that exposes stable, trend-based machine telemetry over HTTP.",
    lifespan=lifespan,
)

# Restrict cross-origin access to the known frontend origin(s).
# Set SIMULATOR_CORS_ORIGINS (comma-separated) to override the dev default.
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "SIMULATOR_CORS_ORIGINS", "http://localhost:8080"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/v1/snapshot", response_model=SnapshotModel)
def get_snapshot() -> SnapshotModel:
    """Get the snapshot of the simulator."""
    return SnapshotModel.model_validate(simulator.snapshot())


@app.get("/api/v1/machines", response_model=list[MachineModel])
def get_machines() -> list[MachineModel]:
    """Get the machines of the simulator."""
    return [
        MachineModel.model_validate(machine)
        for machine in simulator.list_machines()
    ]


@app.get("/api/v1/machines/{machine_id}", response_model=MachineModel)
def get_machine(machine_id: str) -> MachineModel:
    """Get the machine of the simulator."""
    machine = simulator.get_machine(machine_id)
    if machine is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown machine_id '{machine_id}'"
        )
    return MachineModel.model_validate(machine)


@app.get(
    "/api/v1/machines/{machine_id}/history", response_model=MachineHistoryModel
)
def get_machine_history(
    machine_id: str,
    samples: int = Query(default=60, ge=10, le=600),
    interval_seconds: float = Query(default=1.0, ge=0.25, le=60.0),
) -> MachineHistoryModel:
    """Get the machine history of the simulator."""
    history = simulator.machine_history(
        machine_id, samples=samples, interval_seconds=interval_seconds
    )
    if history is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown machine_id '{machine_id}'"
        )
    return MachineHistoryModel.model_validate(history)


@app.post("/api/v1/machines/{machine_id}/fault-mode")
def toggle_fault_mode(machine_id: str) -> dict[str, bool]:
    """Toggle the fault mode of the simulator."""
    try:
        new_state = simulator.toggle_fault_prone(machine_id)
        return {"fault_prone": new_state}
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown machine_id '{machine_id}'"
        )


@app.get(
    "/api/v1/stations/{station_id}/state", response_model=StationStateModel
)
def get_station_state(station_id: str) -> StationStateModel:
    """Get the station state of the simulator."""
    station_state = simulator.get_station_state(station_id)
    return StationStateModel.model_validate(station_state)
