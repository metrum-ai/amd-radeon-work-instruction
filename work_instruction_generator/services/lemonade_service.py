# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Lemonade service for pulling Flux-2-Klein-4B and generating images."""
import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

LEMONADE_BASE_URL = "http://lemonade:13305"


class LemonadeClient:
    """Client for Lemonade API (pull, load, image generation)."""

    def __init__(self, base_url: str = LEMONADE_BASE_URL):
        """Initialize the Lemonade client."""
        self.base_url = base_url.rstrip("/")

    async def health(self) -> bool:
        """Check the health of the Lemonade service."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/health", timeout=5.0)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("Lemonade health check failed: %s", exc)
            return False

    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from the Lemonade service.

        /v1/pull blocks until the download completes. Flux-2-Klein-4B is ~16 GB,
        which far exceeds a 300s read window — timing out mid-download made the
        pre-warm retry loop restart the pull from scratch every time (nothing
        commits to the HF cache on abort), so it never finished. Only the read
        timeout is lifted; connect stays bounded so a dead server still fails fast.
        """
        try:
            timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/v1/pull",
                    json={"model_name": model_name},
                    timeout=timeout,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("Pull failed for %s: %s", model_name, e)
            return False

    async def load_model(self, model_name: str, **params) -> bool:
        """Load a model from the Lemonade service."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/v1/load",
                    json={"model_name": model_name, **params},
                    timeout=120.0,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("Load failed for %s: %s", model_name, e)
            return False

    async def generate_image(
        self,
        prompt: str,
        model: str,
        negative_prompt: str = "",
        width: int = 768,
        height: int = 512,
        steps: int = 8,
        cfg_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> tuple[dict[str, Any], Optional[str]]:
        """Call /v1/images/generations and return (response JSON, upstream instance address).

        The upstream address comes straight from nginx's X-Upstream-Addr response header
        (set on the Lemonade LB in config/nginx.conf) — ground truth for which physical
        backend actually served the request, rather than guessing after the fact.
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "negative_prompt": negative_prompt,
            "size": f"{width}x{height}",
            "n": 1,
            "steps": steps,
            "cfg_scale": cfg_scale,
        }
        if seed is not None:
            payload["seed"] = seed

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/images/generations",
                json=payload,
                timeout=300.0,
            )
            resp.raise_for_status()
            upstream_addr = resp.headers.get("x-upstream-addr")
            return resp.json(), upstream_addr


async def ensure_flux_klein_model(
    client: Optional[LemonadeClient] = None,
) -> tuple[bool, str]:
    """Pull and load Flux-2-Klein-4B via Lemonade.

    Returns (success, message).
    """
    if client is None:
        client = LemonadeClient()

    if not await client.health():
        return False, "Lemonade service unreachable"

    model_name = "Flux-2-Klein-4B"

    if not await client.pull_model(model_name):
        return False, f"Failed to pull {model_name}"

    if not await client.load_model(
        model_name, steps=8, cfg_scale=7.5, width=768, height=512
    ):
        return False, f"Failed to load {model_name}"

    return True, f"{model_name} ready"


async def generate_image(
    prompt: str,
    model: str = "Flux-2-Klein-4B",
    negative_prompt: str = "",
    width: int = 768,
    height: int = 512,
    steps: int = 8,
    cfg_scale: float = 7.5,
    artifact_dir: Optional[str] = None,
    client: Optional[LemonadeClient] = None,
) -> tuple[str, Optional[str]]:
    """Generate an image via Lemonade and save to disk.

    Returns (file path, upstream instance address) — the latter is nginx's
    ground truth for which physical Lemonade backend actually served the request.
    """
    if artifact_dir is None:
        # Default to the shared artifact root so real and mock save paths agree
        # and returned URLs resolve on disk (see illustration_generator mock path).
        artifact_dir = os.environ.get("WIG_ARTIFACT_PATH", "/data/wig/artifacts")
    if client is None:
        client = LemonadeClient()

    data, upstream_addr = await client.generate_image(
        prompt=prompt,
        model=model,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
    )

    # Lemonade returns base64 in the "data" array (OpenAI-compatible) or as "image"
    raw: Optional[str] = None
    if isinstance(data.get("data"), list) and len(data["data"]) > 0:
        raw = data["data"][0].get("b64_json")
    if not raw:
        raw = data.get("image") or data.get("b64_json")
    if not raw:
        raise ValueError(
            f"No image data in Lemonade response: {list(data.keys())}"
        )

    file_id = uuid.uuid4().hex
    dest = Path(artifact_dir)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"ill_{file_id}.png"
    path.write_bytes(base64.b64decode(raw))

    logger.info("Illustration saved to %s", path)
    return str(path), upstream_addr
