# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""MCP tools wrapping TechnicalIllustrationAgent (Flux/Lemonade image generation)."""
import asyncio
import logging
import os
from typing import Any, Optional

from work_instruction_generator.agents.technical_illustration_agent import (
    TechnicalIllustrationAgent,
)
from work_instruction_generator.generation.illustration_generator import (
    IllustrationGenerator,
)
from work_instruction_generator.services.lemonade_service import (
    LemonadeClient,
    ensure_flux_klein_model,
)

logger = logging.getLogger(__name__)

_LEMONADE_URL = os.environ.get("WIG_LEMONADE_URL", "http://lemonade:13305")
# max_concurrent_renders=2 matches the 2 physical Flux/Lemonade GPU backends
# behind the LB. With the default of 1, every request serializes through this
# singleton and nginx's least_conn always sees a 0-vs-0 tie, which it breaks
# toward the first listed server (lemonade-1) — lemonade-2 never gets traffic.
_illustrator = TechnicalIllustrationAgent(
    generator=IllustrationGenerator(lemonade_url=_LEMONADE_URL),
    max_concurrent_renders=2,
)


async def _prewarm_one(url: str) -> None:
    """Pull and load Flux on a single Lemonade instance, retrying until it's up."""
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


async def prewarm_flux() -> None:
    """Pre warm every Lemonade peer listed in WIG_LEMONADE_PEERS (comma-separated),
    falling back to WIG_LEMONADE_URL when no peers are configured. Mirrors the
    prewarm behavior the old agent_server.py ran on startup for this agent.

    Set WIG_PREWARM_FLUX=0 to skip it when agent-illustration already
    pre-warms the same peers — two pullers on one peer write the same
    .partial file concurrently and corrupt it
    """
    if os.environ.get("WIG_PREWARM_FLUX", "1").lower() in ("0", "false", "no"):
        logger.info("Flux pre-warm disabled (WIG_PREWARM_FLUX=0)")
        return
    peers_env = os.environ.get("WIG_LEMONADE_PEERS", "")
    urls = [u.strip() for u in peers_env.split(",") if u.strip()] or [
        _LEMONADE_URL
    ]
    # Shared HF cache across peers: first peer downloads alone, rest then load.
    await _prewarm_one(urls[0])
    await asyncio.gather(*[_prewarm_one(u) for u in urls[1:]])


def register(mcp) -> None:
    """Register the tools."""

    @mcp.tool()
    async def generate_illustrations(
        document_id: str,
        steps: list[dict[str, Any]],
        default_style: str = "technical_diagram",
    ) -> list[dict[str, Any]]:
        """Generate technical illustrations for unique steps (skips duplicates)."""
        return await _illustrator.process(document_id, steps, default_style)

    @mcp.tool()
    async def regenerate_illustration(
        illustration_id: str, style_override: Optional[str] = None
    ) -> dict[str, Any]:
        """Regenerate a specific illustration, optionally with a new style."""
        return await _illustrator.regenerate(illustration_id, style_override)
