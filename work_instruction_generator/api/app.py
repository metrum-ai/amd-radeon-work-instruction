# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""FastAPI app factory for WIG.

Wires the REST routes (documents, stations, generation, steps,
chat, illustrations, exports) and the WebSocket channels from plan
Section 11. On startup it logs the route table so the operator can see
which endpoints are live; DB schema initialisation happens in
`work_instruction_generator.api.store`.
"""

import asyncio
import json
import logging
import os
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from work_instruction_generator.api.routes import (
    catalog,
    chat,
    documents,
    export,
    generation,
    illustrations,
    metrics,
    stations,
    websocket,
)
from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

SIMULATOR_URL = os.environ.get("SIMULATOR_URL", "http://machine-simulator:8000")


async def _machine_stream_gen() -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=1.5) as client:
        while True:
            try:
                resp = await client.get(f"{SIMULATOR_URL}/api/v1/snapshot")
                resp.raise_for_status()
                data = resp.json()
                payload = json.dumps(
                    {
                        "machines": data.get("machines", []),
                        "station_state": data.get("station_state"),
                    }
                )
                yield f"data: {payload}\n\n"
            except Exception as exc:
                # Keep the stream alive across transient simulator hiccups.
                logger.warning(
                    "machine-stream poll failed (%s) — sending keep-alive.", exc
                )
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: initialise the store, log the route table, and run shutdown hooks."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Run scripts/setup.sh to scaffold .env "
            "or export DATABASE_URL before starting the API."
        )
    await store.init(database_url)
    logger.info("WIG API starting up — Postgres store initialised")
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path:
            logger.info(
                "  %s %s", ",".join(sorted(methods)) if methods else "WS", path
            )
    yield
    logger.info("WIG API shutting down")


def create_app() -> FastAPI:
    """Create the FastAPI app for the API."""
    app = FastAPI(
        title="Work Instruction Generator (WIG)",
        description=(
            "OpenClaw-powered technical illustration and instruction generation API. "
            "Implements REST endpoints and WebSocket channels from plan Section 11."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # REST routers
    app.include_router(documents.router)
    app.include_router(stations.router)
    app.include_router(catalog.router)
    app.include_router(generation.router)
    app.include_router(metrics.router)
    app.include_router(chat.router)
    app.include_router(illustrations.router)
    app.include_router(export.router)

    # WebSocket channels
    app.include_router(websocket.router)

    # Serve generated illustration images
    artifact_path = os.environ.get("WIG_ARTIFACT_PATH", "/data/wig/artifacts")

    pathlib.Path(artifact_path).mkdir(parents=True, exist_ok=True)
    app.mount(
        "/api/v1/wig/artifacts",
        StaticFiles(directory=artifact_path),
        name="artifacts",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "wig-api"}

    @app.get("/api/v1/machine-stream")
    async def machine_stream() -> StreamingResponse:
        return StreamingResponse(
            _machine_stream_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
