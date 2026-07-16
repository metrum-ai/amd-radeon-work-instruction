# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Ingest application configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def env_int(name: str, default: int) -> int:
    """Get an environment variable as an integer."""
    raw = os.getenv(name)
    return int(raw) if raw else default


def env_float(name: str, default: float) -> float:
    """Get an environment variable as a float."""
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """Ingest application settings."""

    translation_provider: str = os.getenv("TRANSLATION_PROVIDER", "llm")
    llm_translation_base_url: str = os.getenv("LLM_TRANSLATION_BASE_URL", "")
    llm_translation_model: str = os.getenv("LLM_TRANSLATION_MODEL", "")
    llm_translation_api_key: str = os.environ["LLM_TRANSLATION_API_KEY"]
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "hash")
    milvus_host: str = os.getenv("MILVUS_HOST", "milvus-standalone")
    milvus_port: str = os.getenv("MILVUS_PORT", "19530")
    milvus_collection: str = os.getenv(
        "MILVUS_COLLECTION", "machine_manual_chunks"
    )
    milvus_dimension: int = env_int("MILVUS_DIMENSION", 384)
    milvus_connect_timeout_seconds: float = env_float(
        "MILVUS_CONNECT_TIMEOUT_SECONDS", 180.0
    )
    milvus_connect_interval_seconds: float = env_float(
        "MILVUS_CONNECT_INTERVAL_SECONDS", 5.0
    )
    mqtt_host: str = os.getenv("MQTT_HOST", "mosquitto")
    mqtt_port: int = env_int("MQTT_PORT", 1883)
    translation_workers: int = env_int("TRANSLATION_WORKERS", 4)
