# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Generates technical illustrations using Flux-2-Klein-4B via Lemonade."""

import asyncio
import base64
import json
import logging
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from PIL import Image, ImageDraw, ImageFont

try:
    import cv2
    import numpy as np

    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from work_instruction_generator.generation.style_presets import (
    IllustrationStyle,
)
from work_instruction_generator.services import lemonade_service

logger = logging.getLogger(__name__)


_BADGE_BG = (242, 101, 34)
_BADGE_TEXT = (255, 255, 255)
_LEGEND_BG = (10, 10, 12, 210)
_LEGEND_TEXT = (240, 240, 240)
_LEGEND_NUM = (242, 101, 34)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# VLM region-matching endpoint. Prefer dedicated AGENT_VLM_* vars; fall back to
# the legacy AGENT_TRANSLATE_* values so existing deployments keep working.
_INFERENCE_URL = os.environ.get("AGENT_VLM_URL") or os.environ.get(
    "AGENT_TRANSLATE_URL", "http://inference:8000"
)
_INFERENCE_MODEL = os.environ.get("AGENT_VLM_MODEL") or os.environ.get(
    "AGENT_TRANSLATE_MODEL", "language-model"
)

# Fallback arrow targets when VLM positioning fails: interior content positions so arrows
# point inward from badge (badge offset logic pushes badges toward nearest edge).
_SCATTER_ANCHORS = [
    (0.35, 0.30),
    (0.65, 0.25),
    (0.25, 0.55),
    (0.75, 0.50),
    (0.40, 0.72),
    (0.62, 0.70),
]

_VLM_MATCH_PROMPT = """\
You are analyzing a technical manufacturing illustration.
I have detected {n_regions} distinct visual regions in this image:

{region_list}

Below are {n_callouts} action labels that each describe something happening in the image.
For EACH label, return the NUMBER (1 to {n_regions}) of the region that best matches that action.
Multiple labels may share the same region number.

Return ONLY a JSON array of integers with exactly {n_callouts} elements, like: [2, 1, 3, 1]
No explanation. No other text.

Labels:
{labels}"""


def _scatter_as_regions(
    n: int, width_px: int, height_px: int
) -> list[tuple[int, int, int, int, int, int]]:
    stub = width_px // 8
    return [
        (
            int(ax * width_px),
            int(ay * height_px),
            int(ax * width_px) - stub // 2,
            int(ay * height_px) - stub // 2,
            stub,
            stub,
        )
        for ax, ay in (_SCATTER_ANCHORS * 2)[:n]
    ]


def _subdivide_fallback(
    regions: list[tuple[int, int, int, int, int, int]],
    n: int,
    width_px: int,
    height_px: int,
) -> list[tuple[int, int, int, int, int, int]]:
    """Subdivide dominant bounding box into a 2×3 grid when OpenCV finds < 2 blobs."""
    if regions:
        _, _, bx, by, bw, bh = regions[0]
    else:
        bx, by, bw, bh = (
            int(width_px * 0.1),
            int(height_px * 0.1),
            int(width_px * 0.8),
            int(height_px * 0.8),
        )
    grid = []
    for row in range(3):
        for col in range(2):
            cx = bx + int(bw * (col + 0.5) / 2)
            cy = by + int(bh * (row + 0.5) / 3)
            sw, sh = bw // 2, bh // 3
            grid.append((cx, cy, cx - sw // 2, cy - sh // 2, sw, sh))
    return (grid * 2)[:n]


def _cv_find_regions(
    image_path: str, n: int, width_px: int, height_px: int
) -> list[tuple[int, int, int, int, int, int]]:
    """Find top-N distinct visual blobs in a white-background line art image via OpenCV.

    Returns (cx, cy, bx, by, bw, bh) per region, sorted by area descending.
    Falls back to scatter geometry if OpenCV is unavailable or image unreadable.
    """
    if not _CV2_AVAILABLE:
        return _scatter_as_regions(n, width_px, height_px)
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return _scatter_as_regions(n, width_px, height_px)
    inv = cv2.bitwise_not(img)
    _, thresh = cv2.threshold(inv, 30, 255, cv2.THRESH_BINARY)
    k = max(
        5, width_px // 100
    )  # ~7px at 768px — merges strokes without fusing separate objects
    kernel = np.ones((k, k), np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=3)
    contours, _ = cv2.findContours(
        dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    min_area = int(
        width_px * height_px * 0.003
    )  # 0.3% ≈ 1179px at 768×512; catches medium components
    valid = sorted(
        [c for c in contours if cv2.contourArea(c) >= min_area],
        key=cv2.contourArea,
        reverse=True,
    )
    regions: list[tuple[int, int, int, int, int, int]] = []
    for c in valid[: max(n, 8)]:
        moments = cv2.moments(c)
        if moments["m00"] == 0:
            continue
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        bx, by, bw, bh = cv2.boundingRect(c)
        regions.append((cx, cy, bx, by, bw, bh))
    if len(regions) < 2:
        return _subdivide_fallback(regions, n, width_px, height_px)
    return regions[:n] if len(regions) >= n else regions


def _region_zone(cx: int, cy: int, width_px: int, height_px: int) -> str:
    col = "left" if cx < width_px // 3 else ("center" if cx < 2 * width_px // 3 else "right")
    row = "top" if cy < height_px // 3 else ("middle" if cy < 2 * height_px // 3 else "bottom")
    return f"{row}-{col}"


def _vlm_match_regions(
    image_path: str,
    callouts: list[str],
    regions: list[tuple[int, int, int, int, int, int]],
    width_px: int,
    height_px: int,
) -> list[int]:
    """Ask VLM to assign each callout to a detected region (classification, not regression).

    Returns 0-based region indices, one per callout.
    Falls back to sequential assignment on any error.
    """
    n_regions = len(regions)
    n_callouts = len(callouts)
    try:
        img_bytes = Path(image_path).read_bytes()
        encoded = base64.b64encode(img_bytes).decode("ascii")
        region_list = "\n".join(
            f"  Region {i + 1}: {_region_zone(cx, cy, width_px, height_px)} (center {cx}, {cy})"
            for i, (cx, cy, *_) in enumerate(regions)
        )
        labels_str = "\n".join(
            f'{i + 1}. "{c}"' for i, c in enumerate(callouts)
        )
        payload = {
            "model": _INFERENCE_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded}"
                            },
                        },
                        {
                            "type": "text",
                            "text": _VLM_MATCH_PROMPT.format(
                                n_regions=n_regions,
                                region_list=region_list,
                                n_callouts=n_callouts,
                                labels=labels_str,
                            ),
                        },
                    ],
                }
            ],
            "max_tokens": 128,
            "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{_INFERENCE_URL}/v1/chat/completions", json=payload
            )
            resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        raw = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("No JSON array in VLM response")
        items = json.loads(raw[start : end + 1])
        # Convert 1-based VLM indices → 0-based, clamped to valid range
        indices = [
            max(0, min(n_regions - 1, int(x) - 1)) for x in items[:n_callouts]
        ]
        while len(indices) < n_callouts:
            indices.append(len(indices) % n_regions)
        logger.info(
            "VLM matched %d callouts to %d regions", n_callouts, n_regions
        )
        return indices
    except Exception as exc:
        logger.warning(
            "VLM region matching failed (%s) — using sequential fallback.", exc
        )
        return [i % n_regions for i in range(n_callouts)]


def _wrap_text_to_width(
    draw: ImageDraw.ImageDraw, text: str, font, max_width: int
) -> list[str]:
    """Word-wrap text to max_width pixels, measured with the actual font.

    Never truncates: legend labels must read in full, so long callouts wrap
    onto additional lines instead of being cut off. (A single word wider
    than max_width is still kept whole and allowed to overflow slightly,
    rather than chopping it — that's the rare pathological case; routine
    sentences wrap normally.)
    """
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple,
    width: int = 2,
    arrow_size: int = 8,
) -> None:
    """Draw a line with a filled arrowhead at (x1, y1)."""
    draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
    angle = math.atan2(y1 - y0, x1 - x0)
    for side in (0.45, -0.45):
        ax = x1 - arrow_size * math.cos(angle - side)
        ay = y1 - arrow_size * math.sin(angle - side)
        draw.polygon(
            [
                (x1, y1),
                (int(ax), int(ay)),
                (
                    int(x1 - arrow_size * 0.4 * math.cos(angle)),
                    int(y1 - arrow_size * 0.4 * math.sin(angle)),
                ),
            ],
            fill=color,
        )


def apply_callout_overlay(image_path: str, callouts: list[str]) -> str:
    """Overlay numbered badges with VLM-positioned leader arrows + bottom-right legend."""
    if not callouts:
        return image_path

    img = Image.open(image_path).convert("RGBA")
    width_px, height_px = img.size
    n = len(callouts)

    badge_r = max(14, width_px // 48)
    font_badge = _load_font(badge_r)
    font_legend_num = _load_font(max(11, width_px // 68))
    font_legend_txt = _load_font(max(10, width_px // 76))

    # Word-wrap every label up front so the legend's height reflects the
    # actual number of lines needed — labels are never truncated.
    padding = 12
    col_w = min(320, width_px // 2)
    text_max_width = col_w - 22
    _measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    wrapped_labels = [
        _wrap_text_to_width(_measure, c, font_legend_txt, text_max_width)
        for c in callouts
    ]
    total_lines = sum(len(lines) for lines in wrapped_labels)

    # Stage 1: OpenCV finds distinct visual blobs in the line art
    regions = _cv_find_regions(image_path, n, width_px, height_px)
    # Stage 2: VLM classifies which region each callout matches (easier than coordinate regression)
    region_indices = _vlm_match_regions(image_path, callouts, regions, width_px, height_px)
    target_positions: list[tuple[int, int]] = [
        regions[idx][:2] for idx in region_indices
    ]

    # Radial jitter for callouts sharing the same region center — prevents badge stacking
    bucket: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, tp in enumerate(target_positions):
        bucket[tp].append(i)
    for tp, idxs in bucket.items():
        if len(idxs) > 1:
            for k, idx in enumerate(idxs):
                angle = 2 * math.pi * k / len(idxs) - math.pi / 2
                target_positions[idx] = (
                    tp[0] + int(badge_r * 2.5 * math.cos(angle)),
                    tp[1] + int(badge_r * 2.5 * math.sin(angle)),
                )

    # Reserve legend area so badges don't land inside it
    line_h = (
        max(18, int(font_legend_txt.size * 1.7))
        if hasattr(font_legend_txt, "size")
        else 20
    )
    legend_x = width_px - (col_w + padding * 2) - 8
    legend_y = height_px - (padding * 2 + total_lines * line_h) - 8

    # Place each badge offset from its target toward the nearest edge
    badge_positions = []
    for tx, ty in target_positions:
        bx = tx + (-(width_px // 6) if tx < width_px // 2 else (width_px // 6))
        by = ty + (-(height_px // 6) if ty < height_px // 2 else (height_px // 6))
        bx = max(badge_r + 4, min(width_px - badge_r - 4, bx))
        by = max(badge_r + 4, min(height_px - badge_r - 4, by))
        if bx > legend_x and by > legend_y:
            by = max(badge_r + 4, legend_y - badge_r - 4)
        badge_positions.append((bx, by))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for i, ((bx, by), (tx, ty)) in enumerate(
        zip(badge_positions, target_positions)
    ):
        # Arrow from badge edge to the VLM-identified target point
        arr_angle = math.atan2(ty - by, tx - bx)
        lx0 = int(bx + badge_r * math.cos(arr_angle))
        ly0 = int(by + badge_r * math.sin(arr_angle))
        _draw_arrow(
            draw,
            lx0,
            ly0,
            tx,
            ty,
            color=(*_BADGE_BG, 220),
            width=2,
            arrow_size=9,
        )

        # Numbered badge
        num = str(i + 1)
        draw.ellipse(
            [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
            fill=(*_BADGE_BG, 235),
        )
        bbox = draw.textbbox((0, 0), num, font=font_badge)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (bx - tw // 2, by - th // 2),
            num,
            font=font_badge,
            fill=(*_BADGE_TEXT, 255),
        )

    img = Image.alpha_composite(img, overlay)

    # Legend strip (bottom-right) — each label spans as many lines as it needs
    strip_h = padding * 2 + total_lines * line_h
    strip_w = col_w + padding * 2
    legend = Image.new("RGBA", (strip_w, strip_h), _LEGEND_BG)
    ld = ImageDraw.Draw(legend)
    y_leg = padding
    for i, lines in enumerate(wrapped_labels):
        ld.text(
            (padding, y_leg),
            f"{i + 1}.",
            font=font_legend_num,
            fill=(*_LEGEND_NUM, 255),
        )
        for line in lines:
            ld.text(
                (padding + 22, y_leg),
                line,
                font=font_legend_txt,
                fill=(*_LEGEND_TEXT, 255),
            )
            y_leg += line_h
    img.paste(legend, (width_px - strip_w - 8, height_px - strip_h - 8), legend)

    img.convert("RGB").save(image_path, format="PNG")
    logger.info(
        "Callout overlay with arrows applied (%d labels, %d lines) → %s",
        n,
        total_lines,
        image_path,
    )
    return image_path


class IllustrationGenerator:
    """Generates technical illustrations using Flux-2-Klein-4B via Lemonade."""

    def __init__(
        self,
        styles_path: str = "work_instruction_generator/config/illustration_styles.yaml",
        lemonade_url: str = "http://lemonade:13305",
    ):
        self.styles_path = Path(styles_path)
        self.lemonade_url = lemonade_url
        self.styles = self._load_styles()
        self.client = lemonade_service.LemonadeClient(
            base_url=self.lemonade_url
        )

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        with open(path) as f:
            return yaml.safe_load(f)

    def _load_styles(self) -> dict[str, IllustrationStyle]:
        data = self._load_yaml(self.styles_path)
        styles = {}
        for s in data.get("styles", []):
            style = IllustrationStyle(
                id=s["id"],
                name=s["name"],
                description=s.get("description", ""),
                prompt_prefix=s["prompt_prefix"],
                negative_prompt=s["negative_prompt"],
                controlnet_strength=s["controlnet_strength"],
                width=s.get("width", 768),
                height=s.get("height", 512),
            )
            styles[style.id] = style
        return styles

    @staticmethod
    def _build_visual_prompt(
        style_prefix: str,
        components: list[str],
        view_angle: Optional[str],
        step_description: str = "",
    ) -> str:
        """Build a Flux prompt combining the step action with visual elements.

        OEM source_media_refs are intentionally excluded: they contain safety text blocks
        (WARNING/CAUTION/VAC labels) that Flux renders verbatim into the image. All callout
        labels are composited in post via apply_callout_overlay().
        """
        scene = (
            ", ".join(components)
            if components
            else "manufacturing assembly station"
        )
        angle = f"{view_angle} view" if view_angle else "isometric view"
        # Trim to first sentence only — full paragraphs cause Flux to hallucinate rendered text
        first_sentence = (
            step_description.split(".")[0].strip() if step_description else ""
        )
        action_context = (
            f"Physical action depicted: {first_sentence}. "
            "Show only hands, tools, and components in motion — absolutely no rendered text anywhere.\n"
            if first_sentence
            else ""
        )
        return (
            "NO TEXT. NO WORDS. NO LETTERS. NO NUMBERS. NO LABELS. NO ANNOTATIONS. NO WRITING. "
            "PURELY VISUAL DIAGRAM ONLY. "
            f"{style_prefix}\n\n"
            f"{action_context}"
            f"Scene: {scene}, {angle}\n"
            "Style: Clean technical line art, white background, thin black engineering lines. "
            "Every part code, measurement value, and identifier must remain invisible — "
            "show only physical shapes, hands, tools and components. "
            "NO TEXT. NO NUMBERS. NO LABELS. NO ANNOTATIONS."
        )

    async def generate_illustration(  # pylint: disable=unused-argument
        self,
        step_description: str,
        style_id: str,
        components: Optional[list[str]] = None,
        source_media_refs: Optional[
            list[str]
        ] = None,  # kept for API compat, not used in prompt
        view_angle: Optional[str] = None,
        callouts: Optional[list[str]] = None,
        control_image_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate an illustration via Lemonade Flux-2-Klein."""
        style = self.styles.get(style_id)
        if not style:
            logger.warning(
                "Style %s not found. Falling back to default.", style_id
            )
            style = self.styles.get("technical_diagram")
            if not style:
                raise ValueError(
                    f"No valid style found, including default: {style_id}"
                )

        prompt = self._build_visual_prompt(
            style.prompt_prefix, components or [], view_angle, step_description
        )

        negative_prompt = (
            style.negative_prompt
            + ", text, words, letters, digits, numbers, labels, annotations, writing, typography, "
            "watermark, part numbers, codes, alphanumeric characters, captions, callouts, "
            "written measurements, printed values, overlaid text, UI elements, diagrams with text"
        )

        logger.info(
            "Requesting illustration for style %s (%s)",
            style_id,
            view_angle or "isometric",
        )
        try:
            artifact_path, upstream_addr = (
                await lemonade_service.generate_image(
                    prompt=prompt,
                    model="Flux-2-Klein-4B",
                    negative_prompt=negative_prompt,
                    width=style.width,
                    height=style.height,
                    steps=4,
                    cfg_scale=1.0,
                    client=self.client,
                )
            )
        except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
            # ponytail: no separate pre-flight health() check — a per-request health
            # probe through the LB was skewing nginx least_conn routing (it occupied
            # a connection slot on one backend right as the real request needed to
            # pick one). Just attempt the call and fall back to mock on failure.
            logger.warning(
                "Lemonade generate_image failed (%s) — returning mock illustration.",
                exc,
            )
            artifact_dir = Path(
                os.environ.get("WIG_ARTIFACT_PATH", "/data/wig/artifacts")
            )
            mock_filename = f"mock_ill_{style.id}.png"
            mock_path = artifact_dir / mock_filename
            if not mock_path.exists():
                artifact_dir.mkdir(parents=True, exist_ok=True)
                img = Image.new(
                    "RGB", (style.width, style.height), (230, 232, 240)
                )
                draw = ImageDraw.Draw(img)
                draw.text(
                    (style.width // 2, style.height // 2),
                    f"[{style.name}]",
                    fill=(140, 145, 165),
                    anchor="mm",
                )
                img.save(str(mock_path))
            return {
                # Degraded, not "completed": this is a shared gray placeholder,
                # not a real render — surfaced so the UI/export can flag it.
                "status": "degraded",
                "mock": True,
                "artifact_ref": f"/api/v1/wig/artifacts/{mock_filename}",
                "image_url": f"/api/v1/wig/artifacts/{mock_filename}",
                "width": style.width,
                "height": style.height,
                "prompt_used": prompt,
                "metadata": {
                    "style": style.id,
                    "components": components or [],
                    "mock": True,
                },
            }

        if callouts:
            # ponytail: overlay does blocking OpenCV + a sync HTTP call to the VLM
            # endpoint — off the event loop so concurrent generate_illustration()
            # calls (asyncio.gather in TechnicalIllustrationAgent.process) actually overlap.
            await asyncio.to_thread(
                apply_callout_overlay, artifact_path, callouts
            )

        filename = Path(artifact_path).name
        web_url = f"/api/v1/wig/artifacts/{filename}"
        return {
            "status": "completed",
            "artifact_ref": web_url,
            "image_url": web_url,
            "width": style.width,
            "height": style.height,
            "prompt_used": prompt,
            "metadata": {"style": style.id, "components": components or []},
            "lemonade_instance": upstream_addr,
        }

    async def regenerate_illustration(
        self, ill_id: str, style_override: Optional[str] = None
    ) -> dict[str, Any]:
        """Re-generate an existing illustration."""
        logger.info(
            "Regenerating illustration: %s with style %s",
            ill_id,
            style_override or "original",
        )
        return await self.generate_illustration(
            step_description=f"Regenerate illustration {ill_id}",
            style_id=style_override or "technical_diagram",
        )
