# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""InstructionAuthorAgent — generates step-by-step floor instructions via LLM.

Uses Gemma-4-E2B-it for English instruction
generation and Qwen3.5-9B  for DE/JA/ZH translation.
Degrades to structured mock steps when LLM services are unavailable.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

_LLM_MODEL = os.environ.get("AGENT_LLM_MODEL", "language-model")
_TRANSLATE_MODEL = os.environ.get("AGENT_TRANSLATE_MODEL", "language-model")

# Prefix stamped onto instruction_text when the LLM is unreachable; detected in
# generate_step to flag the step as degraded for export/UI.
_LLM_OFFLINE_MARKER = "[AUTO-DRAFT — LLM offline]"

logger = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────────

_PLAN_SYSTEM_PROMPT = """\
You are a manufacturing process engineer decomposing an EV battery assembly procedure \
into discrete operator steps. Each step must be a single, atomic action that one person \
can complete without interruption.

Output a JSON array of objects — nothing else. No markdown, no prose. Each object has \
exactly two keys: "desc" (the step description, 5–15 words, imperative) and "prereq" \
(boolean, true only if this step resolves an unmet machine prerequisite).

Example without prerequisites (the specific equipment, PPE, and safety terms below \
are illustrative only — always draw the real ones from the procedure's own source \
evidence and safety warnings, never copy these placeholders):
[{"desc": "Inspect connector for damage", "prereq": false}, \
{"desc": "Torque fasteners to spec in star pattern", "prereq": false}]

Example with prerequisites mixed in:
[{"desc": "Confirm the specific unmet condition noted in prerequisites", "prereq": true}, \
{"desc": "Inspect connector for damage", "prereq": false}, \
{"desc": "Don the PPE specified in this procedure's safety warnings", "prereq": true}, \
{"desc": "Torque fasteners to spec in star pattern", "prereq": false}]

Rules:
- 3 to 20 total steps depending on procedure complexity
- Order must match the physical execution sequence
- If unmet prerequisites are listed, insert each as a step (prereq: true) at the natural \
point in the sequence where that condition must be confirmed
- Normal procedure steps always have prereq: false"""

_SYSTEM_PROMPT = """\
You are a certified technical writer producing ISO 9001-compliant manufacturing work \
instructions for EV battery assembly operations. Your output is printed verbatim on \
shop-floor tablets and laminated quick-reference cards used by operators and trainees.

Writing standards:
- Lead every instruction with a precise imperative action verb \
(Verify, Install, Torque, Apply, Confirm, Inspect, Clear, Position, Connect, Load)
- State exact values: torque specs in N·m, temperatures in °C, pressures in kPa/bar, \
times in seconds or minutes, quantities with units
- Reference tool and part numbers where available (e.g. torque wrench P/N TW-450, \
adhesive batch LOT-2214)
- Prefix safety-critical sentences with WARNING: or CAUTION: per plant SOP convention
- Translate any vendor-specific jargon to approved plant vocabulary
- Write for a Level 2 operator in a high-noise environment: unambiguous, no assumptions, \
no passive voice
- Output 3–5 sentences of plain prose. No markdown, no bullet points, no headers, \
no numbered sub-steps.
- After the prose, on a new line output exactly: SAFETY: <warning 1> | <warning 2> | <warning 3>
  These must be 2–3 concise safety warnings specific to THIS step (not generic). \
  Each warning must be one sentence. No markdown."""

_USER_PROMPT_TEMPLATE = """\
Procedure: {procedure_name}
Step: {step_number} of {total_steps}
Previous step completed: {previous_step_summary}

--- Source Evidence ---
{source_citations}

--- Applicable SOPs / LOTO / Quality Rules ---
{rag_context}

--- Approved Plant Terminology ---
{terminology_context}

--- Senior Engineer Notes ---
{tribal_knowledge}

--- Current Machine State ---
State: {machine_state}
Active alarms: {active_alarms}
Last completed step: {last_completed_step}
Interlock status: {interlock_result}

Target language: {target_language}
Audience: {target_audience}

Step to document:
{step_description}"""

_TRANSLATE_SYSTEM = """\
You are a technical translator specializing in manufacturing and EV battery assembly \
documentation. Translate the work instruction below into {language}. \
Preserve all part numbers, model numbers, measurement values, units, and safety \
prefixes (WARNING:, CAUTION:) exactly. Use culturally appropriate phrasing for \
shop-floor personnel. Output only the translated text, nothing else."""


def _parse_safety_line(text: str) -> tuple[str, list[str]]:
    """Split LLM output into (prose, warnings). Extracts the SAFETY: line if present."""
    lines = text.splitlines()
    warnings: list[str] = []
    prose_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("SAFETY:"):
            raw = stripped[len("SAFETY:") :].strip()
            if "|" in raw:
                warnings = [w.strip() for w in raw.split("|") if w.strip()]
            else:
                # LLM used periods instead of pipes — split into sentences
                warnings = [
                    s.strip()
                    for s in re.split(r"(?<=[.!?])\s+", raw)
                    if len(s.strip()) > 10
                ]
            warnings = warnings[:3]
        else:
            prose_lines.append(line)
    prose = " ".join(l.strip() for l in prose_lines if l.strip())
    return prose, warnings


def _clean_llm_output(text: str) -> str:
    """Strip chain-of-thought blocks and markdown artifacts from LLM output."""
    # Remove <think>...</think> reasoning blocks (Qwen3 leakage)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip markdown bold/italic/code markers
    text = re.sub(r"[*_`]{1,3}", "", text)
    # Collapse whitespace
    text = re.sub(r"\n{2,}", " ", text)
    return text.strip()


def _estimate_time(step_description: str) -> int:
    """Rough time estimate in minutes based on step keywords."""
    desc = step_description.lower()
    if any(k in desc for k in ("calibrat", "torque", "cure", "soak", "settle")):
        return 10
    if any(
        k in desc for k in ("install", "connect", "assemble", "mount", "route")
    ):
        return 8
    if any(
        k in desc for k in ("verify", "confirm", "inspect", "check", "validate")
    ):
        return 3
    return 5


class InstructionAuthorAgent:
    """Generate state-aware floor instructions via Gemma (generation) + Qwen (translation).

    Exposed to the OpenClaw gateway as MCP tools: work_instruction_generator/mcp/tools/author.py
    Next agents: TechnicalIllustrationAgent, ReviewFeedbackAgent
    """

    def __init__(
        self,
        llm_url: str = "http://localhost:8000",
        translate_url: str = "http://localhost:8001",
    ) -> None:
        self.llm_url = llm_url.rstrip("/")
        self.translate_url = translate_url.rstrip("/")

    async def generate_step(
        self,
        step_number: int,
        step_description: str,
        source_evidence: dict[str, Any],
        sop_context: dict[str, Any],
        machine_state: Optional[dict[str, Any]] = None,
        interlock_result: Optional[dict[str, Any]] = None,
        target_language: str = "en",
        target_audience: str = "operator",
        total_steps: int = 0,
        previous_step_summary: str = "None",
        existing_instruction_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return an InstructionStep dict for one procedure step.

        existing_instruction_text, when set, means this is a refine of an
        already-generated step rather than a from-scratch generation — the
        prompt is steered to edit that text instead of authoring anew.
        """
        step_id = str(uuid.uuid4())
        interlock_status = (interlock_result or {}).get("status", "pass")
        blocked = interlock_status == "blocked"

        source_citations: list[str] = [
            item.get("source_citation", "")
            for item in source_evidence.get("procedure_outline", [])
        ]

        chunk_texts = [
            c.get("text", "")
            for c in sop_context.get("relevant_sops", [])[:5]
            if c.get("text")
        ]
        safety_text = "; ".join(sop_context.get("safety_warnings", [])[:3])
        loto_text = "; ".join(sop_context.get("loto_rules", [])[:2])
        rag_parts = (
            chunk_texts
            + ([safety_text] if safety_text else [])
            + ([loto_text] if loto_text else [])
        )
        rag_context = "\n---\n".join(rag_parts) if rag_parts else "N/A"

        ms = machine_state or {}
        interlock_summary = (
            f"BLOCKED — {'; '.join((interlock_result or {}).get('blocked_reasons', []))}"
            if blocked
            else "PASS"
        )
        description_to_use = (
            "Prerequisites not met — generate recovery instructions: "
            + "; ".join((interlock_result or {}).get("required_actions", []))
            if blocked
            else step_description
        )
        if not blocked and existing_instruction_text:
            description_to_use = (
                "EXISTING STEP TEXT (preserve this — change only what the "
                f"request below asks for):\n{existing_instruction_text}\n\n"
                f"REQUESTED CHANGE: {step_description}\n\n"
                "Rewrite the step applying only the requested change. Keep all "
                "other wording, tools, and safety warnings from the existing "
                "step text unless the requested change requires updating them."
            )

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            procedure_name=source_evidence.get("procedure_name")
            or source_evidence.get("document_id", ""),
            step_number=step_number,
            total_steps=total_steps or "?",
            previous_step_summary=previous_step_summary,
            source_citations=", ".join(source_citations) or "N/A",
            rag_context=rag_context or "N/A",
            terminology_context=str(sop_context.get("approved_terminology", {}))
            or "N/A",
            tribal_knowledge=str(sop_context.get("tribal_knowledge", ""))
            or "None",
            machine_state=ms.get("state", "unknown"),
            active_alarms=str(ms.get("active_alarms", [])),
            last_completed_step=ms.get("last_completed_step", "None"),
            interlock_result=interlock_summary,
            target_language=target_language,
            target_audience=target_audience,
            step_description=description_to_use,
        )

        raw_output = await self._call_llm(user_prompt)
        llm_offline = raw_output.startswith(_LLM_OFFLINE_MARKER)
        instruction_text, warnings = _parse_safety_line(raw_output)
        if not instruction_text:
            instruction_text = raw_output
        # Collapse remaining whitespace in prose only, after SAFETY line is extracted
        instruction_text = re.sub(r"\n{2,}", " ", instruction_text).strip()

        quality_checks = self._extract_quality_checks(
            sop_context, step_description
        )

        step: dict[str, Any] = {
            "step_id": step_id,
            "step_number": step_number,
            "title": self._derive_title(instruction_text),
            "instruction_text": instruction_text,
            "tools_required": self._extract_tools(sop_context, step_description),
            "parts_required": [],
            "safety_warnings": warnings,
            "quality_checks": quality_checks,
            "source_citations": source_citations,
            "terminology_mappings": sop_context.get("approved_terminology", {}),
            "tribal_knowledge_refs": [],
            "estimated_time_minutes": _estimate_time(description_to_use),
            "difficulty": "medium",
            "interlock_status": interlock_status,
            "target_language": target_language,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "degraded": llm_offline,
            "llm_status": "offline" if llm_offline else "ok",
        }
        logger.info(
            "Generated step %d (interlock=%s, lang=%s)",
            step_number,
            interlock_status,
            target_language,
        )
        return step

    async def plan_steps(
        self,
        source_evidence: dict[str, Any],
        sop_context: dict[str, Any],
        blocked_prereqs: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Ask the LLM to decompose the procedure into ordered step objects.

        Returns a list of {"desc": str, "prereq": bool} dicts.
        Falls back to generic steps on LLM failure.
        """
        procedure_name = source_evidence.get(
            "procedure_name"
        ) or source_evidence.get("document_id", "procedure")
        outline_texts = [
            item.get("text", "")
            for item in source_evidence.get("procedure_outline", [])
            if item.get("text")
        ]
        manual_texts = [
            item.get("text", "")
            for item in source_evidence.get("machine_manual_refs", [])
            if item.get("text")
        ]
        safety_notes = sop_context.get("safety_warnings", [])[:3]

        context_block = (
            "\n---\n".join(outline_texts + manual_texts)
            or "No source evidence provided."
        )
        safety_block = "; ".join(safety_notes) if safety_notes else "None"
        prereq_block = (
            f"Unmet prerequisites — insert exactly {len(blocked_prereqs)} step(s) "
            "with \"prereq\": true, one per item below, each at the natural point "
            "in the sequence where that condition must be confirmed. Every other "
            "step in the procedure must have \"prereq\": false:\n"
            + "\n".join(f"- {p}" for p in blocked_prereqs)
            if blocked_prereqs
            else ""
        )

        user_prompt = (
            f"Procedure: {procedure_name}\n\n"
            f"Source evidence:\n{context_block}\n\n"
            f"Safety/LOTO requirements: {safety_block}\n\n"
            + (f"{prereq_block}\n\n" if prereq_block else "")
            + 'Decompose into ordered steps. Output JSON array of {"desc": str, "prereq": bool} objects.'
        )

        try:
            payload = {
                "model": _LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self.llm_url}/v1/chat/completions", json=payload
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"]
                raw = _clean_llm_output(raw)
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                if match:
                    steps = json.loads(match.group())
                    if isinstance(steps, list) and len(steps) >= 1:
                        parsed = []
                        for s in steps:
                            if isinstance(s, dict) and "desc" in s:
                                parsed.append(
                                    {
                                        "desc": str(s["desc"]).strip(),
                                        "prereq": bool(s.get("prereq", False)),
                                    }
                                )
                            elif isinstance(s, str) and s.strip():
                                # Fallback: plain string from old-format LLM output
                                parsed.append(
                                    {"desc": s.strip(), "prereq": False}
                                )
                        parsed = [s for s in parsed if s["desc"]]
                        # Deduplicate by lowercased description
                        seen: set = set()
                        unique: list = []
                        for s in parsed:
                            key = s["desc"].lower().strip()
                            if key not in seen:
                                seen.add(key)
                                unique.append(s)
                        parsed = unique
                        # Guard against the LLM over-applying prereq: true beyond
                        # the actual number of unmet prerequisites — demote any
                        # excess back to a normal step rather than let the whole
                        # procedure read as blocked.
                        max_prereqs = len(blocked_prereqs or [])
                        prereq_seen = 0
                        for s in parsed:
                            if s["prereq"]:
                                if prereq_seen < max_prereqs:
                                    prereq_seen += 1
                                else:
                                    s["prereq"] = False
                        prereqs = [s for s in parsed if s["prereq"]]
                        normals = [s for s in parsed if not s["prereq"]]
                        # Cap total at 20
                        normals = normals[: max(0, 20 - len(prereqs))]
                        parsed = prereqs + normals
                        if len(parsed) >= 3:
                            return parsed
                        logger.warning(
                            "plan_steps returned %d steps — padding.",
                            len(parsed),
                        )
                        while len(parsed) < 3:
                            parsed.append(
                                {
                                    "desc": f"Verify and confirm completion of {procedure_name}",
                                    "prereq": False,
                                }
                            )
                        return parsed
        except Exception as exc:
            logger.warning(
                "plan_steps LLM call failed (%s) — using fallback.", exc
            )

        fallback = [
            {
                "desc": f"Prepare workspace and verify PPE/LOTO for {procedure_name}",
                "prereq": False,
            },
            {"desc": f"Perform {procedure_name} operation", "prereq": False},
            {
                "desc": f"Inspect and confirm completion of {procedure_name}",
                "prereq": False,
            },
        ]
        if blocked_prereqs:
            for p in blocked_prereqs:
                fallback.insert(0, {"desc": p, "prereq": True})
        return fallback

    async def translate(
        self, step: dict[str, Any], target_language: str
    ) -> dict[str, Any]:
        """Translate instruction_text and title via Qwen3.5."""
        if target_language == "en":
            return step

        try:
            translated_text = await self._call_translate(
                step.get("instruction_text", ""), target_language
            )
            translated_title = await self._call_translate(
                step.get("title", ""), target_language
            )
        except Exception as exc:
            # Translation failed: keep the source text and do NOT relabel the
            # language, so downstream never claims translated content it lacks.
            logger.warning(
                "Translation to %s failed (%s) — keeping source text.",
                target_language,
                exc,
            )
            fallback = dict(step)
            fallback["translation_failed"] = True
            return fallback

        translated = dict(step)
        translated["instruction_text"] = translated_text
        translated["title"] = translated_title
        translated["target_language"] = target_language
        translated["translation_failed"] = False
        return translated

    # ── private helpers ──────────────────────────────────────────────────────

    async def _call_llm(self, user_prompt: str) -> str:
        """Call Gemma-4-E2B-it via chat completions; fall back to structured draft on failure."""
        try:
            payload = {
                "model": _LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 512,
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self.llm_url}/v1/chat/completions", json=payload
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
                # Remove <think> blocks and markdown but preserve newlines so
                # _parse_safety_line can find the SAFETY: line before collapsing.
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                text = re.sub(r"[*_`]{1,3}", "", text)
                return text.strip()
        except Exception as exc:
            logger.warning(
                "LLM unavailable (%s) — using fallback instruction text.", exc
            )
            return f"{_LLM_OFFLINE_MARKER} {user_prompt.splitlines()[-1]}"

    async def _call_translate(self, text: str, language: str) -> str:
        """Call Qwen3.5-9B via chat completions for translation.

        Raises on transport/HTTP failure so the caller (translate) can flag the
        step as untranslated rather than silently mislabeling source text.
        """
        if not text:
            return text
        payload = {
            "model": _TRANSLATE_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": _TRANSLATE_SYSTEM.format(language=language),
                },
                {"role": "user", "content": text},
            ],
            "max_tokens": 600,
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.translate_url}/v1/chat/completions", json=payload
            )
            resp.raise_for_status()
            translated = resp.json()["choices"][0]["message"]["content"]
        return _clean_llm_output(translated)

    @staticmethod
    def _extract_quality_checks(
        sop_context: dict[str, Any], step_description: str
    ) -> list[str]:
        checks: list[str] = []
        _QC_RE = re.compile(
            r"\b(inspect|measure|verify|check|confirm|validate|torque|dimension|tolerance|reading)\b",
            re.IGNORECASE,
        )
        # Pull explicit quality checks from SOP context
        for raw in sop_context.get("quality_checks", []):
            if isinstance(raw, str) and _QC_RE.search(raw):
                checks.append(raw.strip())
        # Derive a basic check from the step description if none found
        if not checks and _QC_RE.search(step_description):
            checks.append(f"Verify completion of: {step_description[:80]}")
        return checks[:3]

    @staticmethod
    def _derive_title(description: str) -> str:
        m = re.search(r"^(.+?[.!?])\s", description)
        sentence = m.group(1) if m else description
        sentence = sentence.rstrip(".,;:").strip() if sentence else ""
        if not sentence:
            return "Step"
        # Only uppercase the first char — never lowercase the rest, so safety
        # acronyms/part codes (LOTO, HV, PN-123) keep their casing.
        return sentence[:1].upper() + sentence[1:]

    @staticmethod
    def _extract_tools(
        sop_context: dict[str, Any], step_description: str
    ) -> list[str]:
        _TOOL_KEYWORDS = {
            "torque wrench": "torque wrench",
            "multimeter": "multimeter",
            "caliper": "caliper",
            "torque arm": "torque arm",
            "barcode scanner": "barcode scanner",
            "leak tester": "leak tester",
            "hipot tester": "hipot tester",
            "hi-pot tester": "hipot tester",
            "calibration target": "calibration target",
            "esd wrist strap": "ESD wrist strap",
            "dispensing gun": "dispensing gun",
            "adhesive dispenser": "adhesive dispenser",
            "laser welder": "laser welder",
            "tim dispenser": "TIM dispenser",
            "crimp tool": "crimp tool",
            "sealant gun": "sealant gun",
            "esd ground lead": "ESD ground lead",
        }
        # Tools are step-specific — match only against this step's own
        # planned description. sop_context is shared across every step in
        # the document, so matching against it tags every step identically
        # regardless of what that step actually does.
        step_text = step_description.lower()
        return [
            label
            for keyword, label in _TOOL_KEYWORDS.items()
            if keyword in step_text
        ]
