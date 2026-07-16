# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Main module for ingest application."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .config import Settings
from .embedder import build_embedder
from .milvus_store import MilvusStore
from .models import ChunkItem, ChunkRecord, IngestRequest, IngestResponse
from .routes.context import router as context_router
from .subscriber import SparkplugSubscriber
from .translators import IdentityTranslator, Translator, build_translator

logger = logging.getLogger(__name__)

settings = Settings()
translator = build_translator(
    settings.translation_provider,
    llm_base_url=settings.llm_translation_base_url,
    llm_model=settings.llm_translation_model,
    llm_api_key=settings.llm_translation_api_key,
)
identity_translator = IdentityTranslator()
embedder = build_embedder(
    settings.embedding_provider, settings.milvus_dimension
)
store = MilvusStore(
    host=settings.milvus_host,
    port=settings.milvus_port,
    collection_name=settings.milvus_collection,
    dimension=settings.milvus_dimension,
    connect_timeout_seconds=settings.milvus_connect_timeout_seconds,
    connect_interval_seconds=settings.milvus_connect_interval_seconds,
)
subscriber = SparkplugSubscriber(
    mqtt_host=settings.mqtt_host,
    mqtt_port=settings.mqtt_port,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan for ingest application."""
    store.connect()
    subscriber.connect()
    yield
    subscriber.disconnect()


app = FastAPI(
    title="Ingestion & Retrieval Backend", version="0.1.0", lifespan=lifespan
)
app.include_router(context_router)


def _chunk_id(doc_id: str, chunk_index: int, content_english: str) -> str:
    """Generate a chunk ID for ingest application."""
    digest = hashlib.sha256(
        f"{doc_id}:{chunk_index}:{content_english}".encode()
    ).hexdigest()
    return f"{doc_id}-{digest[:12]}"


def _translate_chunk(
    item: ChunkItem,
    chunk_translator: Translator,
    identity: IdentityTranslator,
) -> ChunkRecord:
    """Translate a chunk for ingest application."""
    needs_translation = (
        not item.skip_translation
        and item.source_language != item.target_language
    )
    active = chunk_translator if needs_translation else identity
    result = active.translate(
        item.content_original,
        item.source_language,
        item.target_language,
    )
    return ChunkRecord(
        chunk_id=_chunk_id(
            item.doc_id, item.chunk_index, result.translated_text
        ),
        source_doc_id=item.doc_id,
        document_name=item.document_name,
        title=item.title,
        vendor=item.vendor,
        machine_id=item.machine_id,
        document_type=item.document_type,
        version=item.version,
        source_language=item.source_language,
        translated_language=item.target_language,
        translation_provider=result.provider,
        chunk_index=item.chunk_index,
        content_original=item.content_original,
        content_english=result.translated_text,
        element_type=item.element_type,
        page_number=item.page_number,
        source_anchor=item.source_anchor,
    )


def _translate_chunks(request: IngestRequest) -> list[ChunkRecord]:
    """Translate chunks for ingest application."""
    workers = max(settings.translation_workers, 1)
    if workers == 1 or len(request.chunks) <= 1:
        records: list[ChunkRecord] = []
        for item in request.chunks:
            try:
                records.append(
                    _translate_chunk(item, translator, identity_translator)
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Translation failed for chunk {item.chunk_index} "
                        f"of {item.doc_id}: {exc}"
                    ),
                ) from exc
        return records

    indexed: list[ChunkRecord | None] = [None] * len(request.chunks)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _translate_chunk, item, translator, identity_translator
            ): index
            for index, item in enumerate(request.chunks)
        }
        for future in as_completed(futures):
            index = futures[future]
            item = request.chunks[index]
            try:
                indexed[index] = future.result()
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Translation failed for chunk {item.chunk_index} "
                        f"of {item.doc_id}: {exc}"
                    ),
                ) from exc
    return [record for record in indexed if record is not None]


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for ingest application."""
    return {"status": "ok"}


@app.get("/api/v1/snapshot")
def snapshot() -> dict:
    """Snapshot for ingest application."""
    return subscriber.get_snapshot()


@app.get("/api/v1/machine-stream")
async def machine_stream() -> StreamingResponse:
    """Machine stream for ingest application."""

    async def _event_generator():
        while True:
            try:
                data = json.dumps(subscriber.get_snapshot())
                yield f"data: {data}\n\n"
            except Exception as exc:
                # Keep the stream alive if a snapshot build transiently fails.
                logger.warning(
                    "machine-stream snapshot failed (%s) — sending keep-alive.",
                    exc,
                )
                yield ": keep-alive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    """Ingest data for ingest application."""
    target_collection = request.collection or settings.milvus_collection

    if request.reset_collection:
        store.reset_collection(target_collection)

    try:
        collection = store.ensure_collection(target_collection)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    chunk_records = _translate_chunks(request)
    embeddings = embedder.embed_texts(
        [r.content_english for r in chunk_records]
    )
    store.upsert_chunks(collection, chunk_records, embeddings)

    return IngestResponse(
        ingested=len(chunk_records), collection=target_collection
    )
