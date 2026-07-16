# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Main application for OEM ingest application."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException

from .chunking import element_chunks
from .config import Settings
from .image_analyzer import ImageAnalyzer
from .loader import DocumentLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
DetectorFactory.seed = 0

# Each subdirectory under DOCUMENTS_DIR maps to a Milvus collection name.
SUBDIR_COLLECTION_MAP = {
    "machine_manuals": "machine_manuals",
    "procedure_docs": "procedure_docs",
    "sop_docs": "sop_docs",
}


def _detect_language(text: str, declared: str | None) -> str:
    """Detect the language of a text."""
    if declared:
        normalized = declared.strip().lower().split("-")[0]
        if normalized:
            return normalized
    try:
        return detect(text).split("-")[0]
    except LangDetectException:
        return "unknown"


def _post_batch_with_retry(
    client: httpx.Client,
    settings: Settings,
    batch: list[dict],
    reset: bool,
    collection_name: str,
    batch_number: int,
) -> dict:
    """POST one batch, retrying transient failures (timeouts, connection errors,
    5xx) with backoff. The backend's /api/v1/ingest upserts by chunk_id, so a
    retried (or fully rerun) batch never creates duplicates — safe to retry.
    """
    last_exc: Exception | None = None
    for attempt in range(1, settings.ingest_max_retries + 1):
        try:
            response = client.post(
                f"{settings.backend_url}/api/v1/ingest",
                json={
                    "chunks": batch,
                    "reset_collection": reset,
                    "collection": collection_name,
                },
            )
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code < 500
            ):
                raise  # client error (bad payload) — retrying won't help
            if attempt == settings.ingest_max_retries:
                break
            wait = settings.ingest_retry_backoff_seconds * attempt
            logger.warning(
                "batch %d: attempt %d failed (%s) — retrying in %.0fs...",
                batch_number,
                attempt,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"batch {batch_number} failed after {settings.ingest_max_retries} attempts"
    ) from last_exc


def _send_batches(
    client: httpx.Client,
    settings: Settings,
    chunks_payload: list[dict],
    collection_name: str,
    first_batch: bool,
) -> int:
    """POST chunks in batches to the backend for a specific Milvus collection.

    Returns total ingested count.
    """
    total = len(chunks_payload)
    batch_size = max(settings.ingest_batch_size, 1)
    ingested = 0
    batch_number = 0

    for offset in range(0, total, batch_size):
        batch_number += 1
        batch = chunks_payload[offset : offset + batch_size]
        reset = settings.reset_collection and first_batch and offset == 0
        logger.info(
            "batch %d: sending %d chunks (%d-%d of %d)...",
            batch_number,
            len(batch),
            offset + 1,
            offset + len(batch),
            total,
        )
        result = _post_batch_with_retry(
            client, settings, batch, reset, collection_name, batch_number
        )
        batch_ingested = int(result.get("ingested", 0))
        ingested += batch_ingested
        logger.info(
            "batch %d: stored %d chunks → '%s'",
            batch_number,
            batch_ingested,
            result.get("collection", collection_name),
        )

    return ingested


def _ingest_subdir(
    subdir: Path,
    collection_name: str,
    settings: Settings,
    image_analyzer: ImageAnalyzer | None,
    client: httpx.Client,
) -> int:
    """Ingest a subdirectory of documents."""
    loader = DocumentLoader(
        str(subdir),
        analyze_images=settings.analyze_images,
        image_analyzer=image_analyzer,
    )

    logger.info(
        "Loading documents from %s/...",
        subdir.name,
    )
    try:
        documents = loader.load_documents()
    except ValueError as exc:
        logger.warning(
            "Skipping %s/: %s",
            subdir.name,
            exc,
        )
        return 0

    logger.info(
        "Loaded %d documents",
        len(documents),
    )

    detected_languages = {
        doc.doc_id: _detect_language(doc.content, doc.declared_language)
        for doc in documents
    }

    chunks_payload: list[dict] = []
    for doc in documents:
        source_language = detected_languages[doc.doc_id]
        if source_language == "unknown":
            raise RuntimeError(
                f"Could not determine source language for {doc.source_path.name}. "
                "Add a 'language' field to its .meta.yaml."
            )

        doc_chunks = element_chunks(
            doc.elements,
            settings.chunk_words,
            settings.chunk_overlap_words,
        )
        tables = sum(1 for c in doc_chunks if c.element_type == "table")
        images = sum(
            1 for c in doc_chunks if c.element_type == "image_explanation"
        )
        logger.info(
            "%s: %s, %d chunks (%d tables, %d images)",
            doc.source_path.name,
            source_language,
            len(doc_chunks),
            tables,
            images,
        )

        for chunk_index, chunk in enumerate(doc_chunks):
            chunk_language = (
                settings.target_language
                if chunk.skip_translation
                else source_language
            )
            chunks_payload.append(
                {
                    "doc_id": doc.doc_id,
                    "document_name": doc.document_name,
                    "title": doc.title,
                    "vendor": doc.vendor,
                    "machine_id": doc.machine_id,
                    "document_type": doc.document_type,
                    "version": doc.version,
                    "source_language": chunk_language,
                    "target_language": settings.target_language,
                    "chunk_index": chunk_index,
                    "content_original": chunk.text,
                    "element_type": chunk.element_type,
                    "page_number": chunk.page_number,
                    "source_anchor": chunk.source_anchor,
                    "skip_translation": chunk.skip_translation,
                }
            )

    if not chunks_payload:
        logger.warning(
            "No chunks produced for %s/ — skipping.",
            subdir.name,
        )
        return 0

    logger.info(
        "  Sending %d chunks → collection '%s' "
        "(batch size %d)...",
        len(chunks_payload),
        collection_name,
        settings.ingest_batch_size,
    )
    return _send_batches(
        client, settings, chunks_payload, collection_name, first_batch=True
    )


def main() -> None:
    """Main function for OEM ingest application."""
    settings = Settings()
    image_analyzer = None
    if settings.analyze_images:
        image_analyzer = ImageAnalyzer(
            base_url=settings.inference_base_url,
            model=settings.inference_model,
            api_key=settings.inference_api_key,
        )

    base_dir = Path(settings.documents_dir)
    timeout = httpx.Timeout(settings.ingest_batch_timeout_seconds)

    total_ingested = 0
    with httpx.Client(timeout=timeout) as client:
        for subdir_name, collection_name in SUBDIR_COLLECTION_MAP.items():
            subdir = base_dir / subdir_name
            if not subdir.exists():
                logger.warning(
                    "[%s] directory not found — skipping.",
                    subdir_name,
                )
                continue

            logger.info(
                "[%s] → collection '%s'",
                subdir_name,
                collection_name,
            )
            ingested = _ingest_subdir(
                subdir, collection_name, settings, image_analyzer, client
            )
            total_ingested += ingested
            logger.info(
                "[%s] done: %d chunks ingested.",
                subdir_name,
                ingested,
            )

    logger.info(
        "Ingestion complete: %d total chunks across all collections.",
        total_ingested,
    )


if __name__ == "__main__":
    main()
