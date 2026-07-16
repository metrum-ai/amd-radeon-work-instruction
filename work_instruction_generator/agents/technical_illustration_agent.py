# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Technical Illustration Agent."""
import asyncio
import logging
import os
import re
import uuid
from typing import Any, Optional

import httpx

from work_instruction_generator.generation.illustration_generator import (
    IllustrationGenerator,
)
from work_instruction_generator.skills.step_decomposition import (
    estimate_view_angle,
)

_LLM_URL = os.environ.get("AGENT_LLM_URL", "http://llm-inference:8000")
_LLM_MODEL = os.environ.get("AGENT_LLM_MODEL", "language-model")

_VISUAL_SUMMARY_PROMPT = """\
You are writing a prompt for a technical illustration generator.
Given a manufacturing step, write EXACTLY ONE sentence (10-15 words) that describes \
the physical visual scene — what action is being performed, what the operator's hands \
are doing, and what tool or component is being worked on.
Rules:
- No measurements, no part codes, no numbers, no acronyms
- Pure physical description only: verbs, hands, tools, components
- Output only the sentence, nothing else"""


async def _summarise_for_flux(
    title: str, instruction: str, tools: list, parts: list
) -> str:
    """Ask the LLM for a single clean visual scene sentence for the Flux prompt."""
    components = ", ".join((tools + parts)[:4]) or "assembly components"
    user_msg = (
        f"Step: {title}\n"
        f"Instruction: {instruction[:300]}\n"
        f"Tools/Parts: {components}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_LLM_URL}/v1/chat/completions",
                json={
                    "model": _LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": _VISUAL_SUMMARY_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 60,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            sentence = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip quotes if LLM wraps in them
            sentence = sentence.strip("\"'")
            logger.info("Visual summary: %s", sentence)
            return sentence
    except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Visual summary LLM failed (%s) — falling back to title.", exc
        )
        return title


def _split_substeps(instruction_text: str, max_callouts: int = 6) -> list[str]:
    """Split instruction text into full-sentence action phrases for callout overlay labels.

    Each label is a complete sentence — apply_callout_overlay's legend wraps
    long labels onto multiple lines rather than truncating, so labels must
    not be pre-shortened here (clause-trimming or word-capping produced
    sentence fragments that read as cut off).
    """
    sentences = [
        s.strip().rstrip(",.;:")
        for s in re.split(r"(?<=[.!?])\s+", instruction_text)
        if s.strip()
    ]
    return sentences[:max_callouts]


logger = logging.getLogger(__name__)


class TechnicalIllustrationAgent:
    """OpenClaw-compatible Technical Illustration Agent.
    Maps InstructionStep objects to illustration jobs and queues them for generation.
    """

    def __init__(
        self,
        generator: Optional[IllustrationGenerator] = None,
        max_concurrent_renders: int = 1,
    ):
        """Initialize the TechnicalIllustrationAgent."""
        self.generator = generator or IllustrationGenerator()
        self.max_concurrent_renders = max(1, max_concurrent_renders)
        self._render_semaphore = asyncio.Semaphore(self.max_concurrent_renders)
        self.pending_jobs: list[dict[str, Any]] = []

    async def _generate_one(
        self,
        document_id: str,
        step: dict[str, Any],
        default_style: str,
    ) -> dict[str, Any]:
        """Generate a single illustration for a step."""
        style_id = step.get("style", default_style)
        ill_id = str(uuid.uuid4())
        step_title = step.get("title", step.get("instruction_text", ""))
        tools = step.get("tools_required", [])
        parts = step.get("parts_required", [])
        visual_scene = await _summarise_for_flux(
            step_title, step.get("instruction_text", ""), tools, parts
        )
        try:
            result = await self.generator.generate_illustration(
                step_description=visual_scene,
                style_id=style_id,
                components=tools + parts,
                source_media_refs=step.get("visual_refs")
                or step.get("source_citations", []),
                view_angle=estimate_view_angle(step_title),
                callouts=_split_substeps(step.get("instruction_text", "")),
            )
            logger.info(
                "Generated illustration %s for step %s",
                ill_id,
                step.get("step_number"),
            )
            return {
                "illustration_id": ill_id,
                "document_id": document_id,
                "step_id": step.get("step_id"),
                "step_number": step.get("step_number"),
                "style": style_id,
                "artifact_ref": result.get("artifact_ref")
                or result.get("image_url"),
                "width": result["width"],
                "height": result["height"],
                "prompt": result["prompt_used"],
                "alt_text": step_title,
                # Propagate the generator's status (e.g. "degraded" for a mock
                # placeholder) instead of hardcoding "completed".
                "status": result.get("status", "completed"),
                "mock": result.get("mock", False),
                "lemonade_instance": result.get("lemonade_instance"),
            }
        except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
            logger.error(
                "Illustration generation failed for step %s: %s",
                step.get("step_number"),
                exc,
            )
            return {
                "illustration_id": ill_id,
                "document_id": document_id,
                "step_id": step.get("step_id"),
                "step_number": step.get("step_number"),
                "style": style_id,
                "artifact_ref": None,
                "status": "failed",
                "error": str(exc),
            }

    async def process(
        self,
        document_id: str,
        steps: list[dict[str, Any]],
        default_style: str = "technical_diagram",
    ) -> list[dict[str, Any]]:
        """Generate illustrations for unique steps only — skip repeats."""
        seen: set = set()
        unique = []
        for step in steps:
            key = (
                (step.get("title") or step.get("instruction_text", ""))
                .strip()
                .lower()
            )
            if key and key not in seen:
                seen.add(key)
                unique.append(step)
        logger.info(
            "Illustrating %d unique steps (skipped %d duplicates)",
            len(unique),
            len(steps) - len(unique),
        )
        async def _bounded(step: dict[str, Any]) -> dict[str, Any]:
            # Cap concurrent Flux renders to max_concurrent_renders (default 1),
            # matching the intent behind the accepted constructor argument.
            async with self._render_semaphore:
                return await self._generate_one(
                    document_id, step, default_style
                )

        results = await asyncio.gather(*[_bounded(step) for step in unique])
        return list(results)

    async def regenerate(
        self, ill_id: str, style_override: Optional[str] = None
    ) -> dict[str, Any]:
        """Regenerates a specific illustration."""
        result = await self.generator.regenerate_illustration(
            ill_id, style_override
        )
        return {
            "illustration_id": ill_id,
            "artifact_ref": result["image_url"],
            "style": style_override,
            "status": "completed",
        }
