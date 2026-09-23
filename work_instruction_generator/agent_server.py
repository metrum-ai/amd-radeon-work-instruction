# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Generic OpenClaw agent HTTP server.

Each agent container sets AGENT_NAME and starts this app via:
  uvicorn work_instruction_generator.agent_server:app --host 0.0.0.0 --port <PORT>

Routes:
  GET  /health          → 503 until model pre-warm completes, then {"status": "ok"}
  POST /run/{action}    → calls agent.<action>(**request_body)
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)

AGENT_NAME: str = os.environ.get("AGENT_NAME", "")
_ready: bool = False

# Strong references to fire-and-forget tasks so the event loop can't GC them
# mid-flight; the done-callback surfaces exceptions that would otherwise vanish.
_background_tasks: "set[asyncio.Task]" = set()


def _spawn_tracked(coro: Any) -> None:
    """Schedule a background coroutine, retaining a reference and logging failures."""
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)

    def _done(t: "asyncio.Task") -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error("Background task failed: %s", t.exception())

    task.add_done_callback(_done)

# Allow-list of callable actions exposed per agent over /run/{action}.
# Anything not listed here is rejected, so getattr can't reach arbitrary methods.
_EXPOSED_ACTIONS: Dict[str, set] = {
    "InstructionAuthorAgent": {"generate_step", "plan_steps", "translate"},
    "TechnicalIllustrationAgent": {"process", "regenerate"},
    "CompositorExportAgent": {"export", "find_export"},
}


async def _prewarm_one(url: str) -> None:
    """Pull and load Flux on a single Lemonade instance, retrying until it's up."""
    from work_instruction_generator.services.lemonade_service import (
        LemonadeClient,
        ensure_flux_klein_model,
    )

    client = LemonadeClient(base_url=url)
    for attempt in range(10):
        ok, msg = await ensure_flux_klein_model(client)
        if ok:
            logger.info("Flux ready on %s: %s", url, msg)
            return
        logger.warning(
            "Pre-warm %s attempt %d/10: %s — retrying in 15s",
            url,
            attempt + 1,
            msg,
        )
        await asyncio.sleep(15)
    logger.error("Flux pre-warm failed for %s after 10 attempts", url)


async def _prewarm_flux(lemonade_url: str) -> None:
    """Pre-warm every Lemonade peer listed in WIG_LEMONADE_PEERS (comma-separated).
    Falls back to WIG_LEMONADE_URL (the LB) when no peers are configured.
    """
    global _ready
    peers_env = os.environ.get("WIG_LEMONADE_PEERS", "")
    urls = [u.strip() for u in peers_env.split(",") if u.strip()] or [
        lemonade_url
    ]
    # Peers share one HF cache mount, so parallel first pulls write the same
    # .partial file and fail content verification. Warm the first peer alone
    # (it downloads), then the rest in parallel (they hit the cache and load).
    await _prewarm_one(urls[0])
    await asyncio.gather(*[_prewarm_one(u) for u in urls[1:]])
    _ready = True


def _build_agent(name: str) -> Any:
    """Instantiate the named agent using env vars for service URLs."""
    if name == "TechnicalIllustrationAgent":
        from work_instruction_generator.agents.technical_illustration_agent import (
            TechnicalIllustrationAgent,
        )
        from work_instruction_generator.generation.illustration_generator import (
            IllustrationGenerator,
        )

        lemonade_url = os.environ.get(
            "WIG_LEMONADE_URL", "http://lemonade:13305"
        )
        generator = IllustrationGenerator(lemonade_url=lemonade_url)
        # Matches the 2 physical Flux/Lemonade GPU backends behind the LB. With
        # the default of 1, every request serializes through this singleton and
        # nginx's least_conn always sees a 0-vs-0 tie, which it breaks toward
        # the first listed server (lemonade-1) — lemonade-2 never gets traffic.
        return TechnicalIllustrationAgent(
            generator=generator, max_concurrent_renders=2
        )

    if name == "InstructionAuthorAgent":
        from work_instruction_generator.agents.instruction_author_agent import (
            InstructionAuthorAgent,
        )

        return InstructionAuthorAgent(
            llm_url=os.environ.get("AGENT_LLM_URL", "http://vllm-gemma:8000"),
            translate_url=os.environ.get(
                "AGENT_TRANSLATE_URL", "http://vllm-translate:8001"
            ),
        )

    if name == "CompositorExportAgent":
        from work_instruction_generator.agents.compositor_export_agent import (
            CompositorExportAgent,
        )

        return CompositorExportAgent(
            templates_dir=os.environ.get(
                "WIG_TEMPLATES_DIR",
                "work_instruction_generator/export/templates",
            ),
            artifact_path=os.environ.get(
                "WIG_ARTIFACT_PATH", "/data/wig/artifacts"
            ),
        )

    raise ValueError(f"Unknown AGENT_NAME: {name!r}")


def create_app() -> FastAPI:
    """Create the FastAPI app for the agent."""
    if not AGENT_NAME:
        raise RuntimeError("AGENT_NAME environment variable is required")

    agent = _build_agent(AGENT_NAME)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _ready
        if AGENT_NAME == "TechnicalIllustrationAgent":
            # Stay unready (/health → 503) until Flux is pre-warmed so the LB
            # doesn't route generation traffic before the model can serve it.
            # _prewarm_flux flips _ready=True once the warm-up loop finishes.
            lemonade_url = os.environ.get(
                "WIG_LEMONADE_URL", "http://lemonade:13305"
            )
            _spawn_tracked(_prewarm_flux(lemonade_url))
        else:
            _ready = True  # no model to warm; healthy as soon as uvicorn is up
        yield

    app = FastAPI(
        title=f"OpenClaw Agent: {AGENT_NAME}",
        description=f"HTTP wrapper for the {AGENT_NAME} OpenClaw agent.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        if not _ready:
            raise HTTPException(
                status_code=503, detail="Model pre-warming in progress"
            )
        return {"status": "ok", "agent": AGENT_NAME}

    @app.post("/run/{action}")
    async def run_action(
        action: str, body: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        if action not in _EXPOSED_ACTIONS.get(AGENT_NAME, set()):
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{AGENT_NAME}' has no action '{action}'",
            )
        method = getattr(agent, action, None)
        if not callable(method):
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{AGENT_NAME}' has no action '{action}'",
            )
        try:
            if asyncio.iscoroutinefunction(method):
                result = await method(**body)
            else:
                result = method(**body)
            return {"status": "ok", "result": result}
        except TypeError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid arguments for '{action}': {exc}",
            ) from exc
        except Exception as exc:
            logger.error(
                "Agent %s action %s failed: %s", AGENT_NAME, action, exc
            )
            raise HTTPException(
                status_code=500, detail="Agent action failed"
            ) from exc

    return app


app = create_app()
