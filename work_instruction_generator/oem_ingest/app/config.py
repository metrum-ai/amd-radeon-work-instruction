# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Configuration for OEM ingest application."""

from __future__ import annotations

import os
from dataclasses import dataclass


def env_int(name: str, default: int) -> int:
    """Get an integer environment variable."""
    raw = os.getenv(name)
    return int(raw) if raw else default


def env_bool(name: str, default: bool) -> bool:
    """Get a boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Settings for OEM ingest application."""

    documents_dir: str = os.getenv("DOCUMENTS_DIR", "/app/documents")
    target_language: str = os.getenv("TARGET_LANGUAGE", "en")
    chunk_words: int = env_int("CHUNK_WORDS", 120)
    chunk_overlap_words: int = env_int("CHUNK_OVERLAP_WORDS", 30)
    reset_collection: bool = env_bool("RESET_COLLECTION", False)
    backend_url: str = os.getenv("BACKEND_URL", "http://backend:8080")
    analyze_images: bool = env_bool("ANALYZE_IMAGES", True)
    inference_base_url: str = os.getenv(
        "INFERENCE_BASE_URL", "http://inference:8000/v1"
    )
    inference_model: str = os.getenv("INFERENCE_MODEL", "language-model")
    inference_api_key: str = os.environ["INFERENCE_API_KEY"]
    ingest_batch_size: int = env_int("INGEST_BATCH_SIZE", 10)
    ingest_batch_timeout_seconds: float = float(
        os.getenv("INGEST_BATCH_TIMEOUT_SECONDS", "600")
    )
    ingest_max_retries: int = env_int("INGEST_MAX_RETRIES", 3)
    ingest_retry_backoff_seconds: float = float(
        os.getenv("INGEST_RETRY_BACKOFF_SECONDS", "15")
    )
