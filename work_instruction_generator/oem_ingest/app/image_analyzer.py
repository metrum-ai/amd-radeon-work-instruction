# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""VLM image explanation via the shared inference service."""

from __future__ import annotations

import base64
import io
import logging
import re

from openai import OpenAI
from PIL import Image

from .extraction_types import ExtractedElement

logger = logging.getLogger(__name__)

_MAX_IMAGE_EDGE = 768
_IMAGE_PROMPT = """Analyze this technical manual figure from an OEM document.

Describe in clear English:
1. What the figure shows (diagram type, equipment, layout).
2. Components, labels, and part references visible.
3. Operator actions or procedures implied by the figure.
4. Materials, tools, dimensions, or tolerances if visible.
5. Warnings, cautions, or safety symbols if visible.

Return only the explanation text. Do not invent details that are not visible."""


class ImageAnalyzer:
    """Generates English explanations for PDF figures using a VLM."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 180.0,
    ) -> None:
        """Initialize the image analyzer."""
        self._model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
        )

    def explain_elements(
        self, elements: list[ExtractedElement]
    ) -> list[ExtractedElement]:
        """Fill text on image elements that have PNG bytes.

        Args:
            elements: Parsed elements; image rows are updated in place.

        Returns:
            The same list with image explanations attached or dropped.

        """
        updated: list[ExtractedElement] = []
        for element in elements:
            if element.element_type != "image_explanation":
                updated.append(element)
                continue
            if not element.image_bytes:
                continue
            try:
                explanation = self._explain_image(element.image_bytes)
            except Exception as exc:
                logger.error(
                    "VLM failed for %s: %s", element.source_anchor, exc
                )
                continue
            if not explanation.strip():
                logger.warning("Empty VLM output for %s", element.source_anchor)
                continue
            updated.append(
                ExtractedElement(
                    element_type=element.element_type,
                    page_number=element.page_number,
                    source_anchor=element.source_anchor,
                    text=explanation.strip(),
                    skip_translation=True,
                )
            )
        return updated

    def _explain_image(self, png_bytes: bytes) -> str:
        """Explain an image."""
        encoded = base64.b64encode(_resize_png(png_bytes)).decode("ascii")
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded}",
                            },
                        },
                        {"type": "text", "text": _IMAGE_PROMPT},
                    ],
                },
            ],
            temperature=0.1,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = response.choices[0].message.content or ""
        return re.sub(
            r"<think>.*?</think>",
            "",
            content,
            flags=re.DOTALL,
        ).strip()


def _resize_png(png_bytes: bytes, max_edge: int = _MAX_IMAGE_EDGE) -> bytes:
    """Downscale large figures before VLM inference."""
    with Image.open(io.BytesIO(png_bytes)) as image:
        longest = max(image.width, image.height)
        if longest <= max_edge:
            return png_bytes
        scale = max_edge / longest
        resized = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.LANCZOS,
        )
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
        return buffer.getvalue()
