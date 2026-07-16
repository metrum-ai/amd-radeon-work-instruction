# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""WIG MCP tools server — exposes all deterministic WIG business logic
(machine state/interlock, procedure context/RAG, LLM authoring/translation,
illustration generation, PDF/HTML/JSON export, review feedback) as MCP tools
consumed by the OpenClaw gateway (mcp.servers.wig tools in openclaw.json).

Transport is streamable HTTP (WIG_MCP_HOST/WIG_MCP_PORT) so the server can
run as a container reachable from the OpenClaw gateway over the docker
network, exactly like the agent containers it replaces.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from work_instruction_generator.api.store import store
from work_instruction_generator.mcp.tools import (
    author,
    export,
    illustration,
    machine_state,
    procedure_context,
    review_feedback,
)

logger = logging.getLogger(__name__)

_startup_done = False
_startup_lock = None

# Retain references to fire-and-forget tasks so the loop can't GC them mid-run.
_background_tasks: "set[asyncio.Task]" = set()


def _spawn_tracked(coro) -> None:
    """Schedule a background coroutine, retaining a reference and logging failures."""
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)

    def _done(t: "asyncio.Task") -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error("Background task failed: %s", t.exception())

    task.add_done_callback(_done)


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    """Lifespan for the MCP tools server."""
    global _startup_done, _startup_lock
    if _startup_lock is None:
        _startup_lock = asyncio.Lock()
    async with _startup_lock:
        if not _startup_done:
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                raise RuntimeError(
                    "DATABASE_URL is not set. Run scripts/setup.sh to scaffold "
                    ".env or export DATABASE_URL before starting wig-mcp-tools."
                )
            await store.init(database_url)
            _spawn_tracked(illustration.prewarm_flux())
            _startup_done = True
    yield {}


_MCP_HOST = os.environ.get("WIG_MCP_HOST")
_MCP_PORT = os.environ.get("WIG_MCP_PORT")
if not _MCP_HOST or not _MCP_PORT:
    raise RuntimeError(
        "WIG_MCP_HOST and WIG_MCP_PORT must be set. Run scripts/setup.sh to "
        "scaffold .env or export them before starting wig-mcp-tools."
    )
try:
    _MCP_PORT_INT = int(_MCP_PORT)
except ValueError as exc:
    raise RuntimeError(
        f"WIG_MCP_PORT must be an integer, got {_MCP_PORT!r}"
    ) from exc

mcp = FastMCP(
    name="wig-tools",
    host=_MCP_HOST,
    port=_MCP_PORT_INT,
    lifespan=_lifespan,
)

for module in (
    machine_state,
    procedure_context,
    author,
    illustration,
    export,
    review_feedback,
):
    module.register(mcp)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
