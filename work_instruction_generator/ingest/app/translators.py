# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Translators for ingest application."""

from __future__ import annotations

import re
from typing import Protocol

from openai import OpenAI

from .models import TranslationResult


class Translator(Protocol):
    """Translator protocol."""

    provider_name: str

    def translate(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult: ...


class IdentityTranslator:
    """Identity translator."""

    provider_name = "identity"

    def translate(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult:
        """Translate text."""
        return TranslationResult(
            source_language=source_language,
            target_language=target_language,
            provider=self.provider_name,
            translated_text=text,
        )


class LLMTranslator:
    """LLM translator."""

    provider_name = "llm"

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        """Initialize the LLM translator."""
        self._model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def translate(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult:
        """Translate text."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional technical translator. "
                        f"Translate the user's text from {source_language} to {target_language}. "
                        "Preserve all technical terms, part numbers, units, and formatting. "
                        "Return only the translated text with no explanations or commentary."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            # A translated chunk should never need more than a few hundred tokens
            # (source chunks are ~120 words). Without a cap, a chunk that fails to
            # terminate cleanly (garbled OCR input, a repetition loop, etc.) can run
            # all the way to the model's full context length before stopping —
            # at ~18 tok/s that's ~15 minutes for one chunk. This bounds worst case
            # latency to well under a minute while leaving generous headroom for
            # legitimate translation expansion.
            max_tokens=1024,
            # Disable Qwen3 chain-of-thought thinking mode — translation doesn't
            # benefit from it and it adds latency + <think> tags to the output.
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        translated = response.choices[0].message.content or ""
        translated = re.sub(
            r"<think>.*?</think>", "", translated, flags=re.DOTALL
        ).strip()
        return TranslationResult(
            source_language=source_language,
            target_language=target_language,
            provider=self.provider_name,
            translated_text=translated.strip(),
        )


def build_translator(
    provider: str,
    llm_base_url: str = "",
    llm_model: str = "",
    llm_api_key: str = "",
) -> Translator:
    """Build a translator."""
    normalized = provider.strip().lower()
    if normalized == "identity":
        return IdentityTranslator()
    if normalized == "llm":
        if not llm_base_url:
            raise ValueError(
                "LLM_TRANSLATION_BASE_URL must be set when TRANSLATION_PROVIDER=llm"
            )
        if not llm_model:
            raise ValueError(
                "LLM_TRANSLATION_MODEL must be set when TRANSLATION_PROVIDER=llm"
            )
        if not llm_api_key:
            raise ValueError(
                "LLM_TRANSLATION_API_KEY must be set when TRANSLATION_PROVIDER=llm"
            )
        return LLMTranslator(
            base_url=llm_base_url, model=llm_model, api_key=llm_api_key
        )
    raise ValueError(f"Unsupported translation provider '{provider}'.")
