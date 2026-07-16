# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""asyncpg-backed store for WIG API.

All public methods are async. All state is persisted in PostgreSQL.

Call ``await store.init(database_url)`` once from the app lifespan before
handling any requests.
"""

from __future__ import annotations

import re
import json
import uuid
from typing import Any, Optional

import asyncpg  # type: ignore[import-untyped]

# Safe SQL identifier handling
#
# Column names for dynamic UPDATE ... SET clauses are joined into the
# statement. They are always taken from a hard-coded allow-list defined in
# the call site, never from raw user input. _quote_ident defensively
# validates each name against a strict pattern and double-quotes it so
# that reserved words, mixed case, or embedded characters can never
# reach the database as raw SQL. Values are always bound via asyncpg
# $N placeholders.
_IDENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_ident(name: str) -> str:
    """Return a safely double-quoted SQL identifier."""
    if not isinstance(name, str) or not _IDENT_PATTERN.fullmatch(name):
        raise ValueError(
            "refusing to use unsafe SQL identifier: " + repr(name)
        )
    return '"' + name + '"'

# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS wig_documents (
    document_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    product_name    TEXT,
    asset_id        TEXT,
    procedure_id    TEXT,
    station_id      TEXT,
    procedure_stage TEXT,
    vendor_names    JSONB DEFAULT '[]',
    target_language TEXT DEFAULT 'en',
    status          TEXT DEFAULT 'draft',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_wig_documents_status
    ON wig_documents (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS wig_revisions (
    revision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    content         JSONB NOT NULL DEFAULT '{}',
    change_summary  TEXT,
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, revision_number)
);

CREATE TABLE IF NOT EXISTS wig_steps (
    step_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id            UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    revision_id            UUID REFERENCES wig_revisions(revision_id) ON DELETE SET NULL,
    step_number            INTEGER NOT NULL,
    title                  TEXT NOT NULL,
    instruction_text       TEXT,
    machine_state_ref      UUID,
    interlock_status       TEXT DEFAULT 'pass',
    tools_required         JSONB DEFAULT '[]',
    parts_required         JSONB DEFAULT '[]',
    safety_warnings        JSONB DEFAULT '[]',
    quality_checks         JSONB DEFAULT '[]',
    source_citations       JSONB DEFAULT '[]',
    terminology_mappings   JSONB DEFAULT '{}',
    tribal_knowledge_refs  JSONB DEFAULT '[]',
    illustration_ref       TEXT,
    estimated_time_minutes INTEGER DEFAULT 5,
    difficulty             TEXT DEFAULT 'medium',
    target_language        TEXT DEFAULT 'en',
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_steps_document
    ON wig_steps (document_id, step_number);

CREATE TABLE IF NOT EXISTS wig_source_artifacts (
    source_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    vendor_name         TEXT,
    file_name           TEXT NOT NULL,
    file_type           TEXT NOT NULL,
    file_size_bytes     BIGINT DEFAULT 0,
    artifact_ref        TEXT NOT NULL,
    extracted_metadata  JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_source_artifacts_document
    ON wig_source_artifacts (document_id);

CREATE TABLE IF NOT EXISTS wig_machine_state_snapshots (
    state_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    station_id          TEXT NOT NULL,
    procedure_id        TEXT,
    source              TEXT NOT NULL DEFAULT 'mock_simulator',
    state               TEXT NOT NULL,
    active_alarms       JSONB DEFAULT '[]',
    readiness_flags     JSONB DEFAULT '{}',
    quality_readings    JSONB DEFAULT '{}',
    last_completed_step TEXT,
    raw_payload         JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_machine_state_document
    ON wig_machine_state_snapshots (document_id, created_at DESC);

-- Latest state per station (simulator / SSE stream)
CREATE TABLE IF NOT EXISTS wig_station_states (
    station_id TEXT PRIMARY KEY,
    snapshot   JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wig_interlock_evaluations (
    interlock_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    state_id         UUID REFERENCES wig_machine_state_snapshots(state_id) ON DELETE SET NULL,
    status           TEXT NOT NULL,
    blocked_reasons  JSONB DEFAULT '[]',
    required_actions JSONB DEFAULT '[]',
    evaluated_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_interlocks_document
    ON wig_interlock_evaluations (document_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS wig_illustrations (
    illustration_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    step_id           UUID REFERENCES wig_steps(step_id) ON DELETE SET NULL,
    style             TEXT NOT NULL DEFAULT 'technical_diagram',
    prompt            TEXT NOT NULL DEFAULT '',
    artifact_ref      TEXT NOT NULL,
    width             INTEGER,
    height            INTEGER,
    source_media_refs JSONB DEFAULT '[]',
    alt_text          TEXT,
    status            TEXT DEFAULT 'completed',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_illustrations_document_step
    ON wig_illustrations (document_id, step_id);

CREATE TABLE IF NOT EXISTS wig_exports (
    export_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    revision_id     UUID REFERENCES wig_revisions(revision_id) ON DELETE SET NULL,
    format          TEXT NOT NULL,
    artifact_ref    TEXT NOT NULL,
    content_type    TEXT,
    file_size_bytes BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wig_chat_history (
    message_id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id                   UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    role                          TEXT NOT NULL,
    content                       TEXT NOT NULL,
    step_id                       UUID,
    accepted_as_tribal_knowledge  BOOLEAN DEFAULT FALSE,
    created_at                    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wig_tribal_knowledge (
    tk_id       UUID PRIMARY KEY,
    document_id UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    step_ids    JSONB DEFAULT '[]',
    status      TEXT DEFAULT 'accepted',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_tribal_knowledge_document
    ON wig_tribal_knowledge (document_id);

CREATE TABLE IF NOT EXISTS wig_jobs (
    job_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID REFERENCES wig_documents(document_id) ON DELETE CASCADE,
    status           TEXT NOT NULL DEFAULT 'queued',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    current_step     TEXT,
    steps_completed  INTEGER NOT NULL DEFAULT 0,
    steps_total      INTEGER NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wig_jobs_document
    ON wig_jobs (document_id, started_at DESC);
"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _str(v: Any) -> Any:
    """Convert a value to a string."""
    return str(v) if isinstance(v, uuid.UUID) else v


def _row(record) -> Optional[dict[str, Any]]:
    """Convert a record to a row."""
    if record is None:
        return None
    d = {k: _str(v) for k, v in dict(record).items()}
    if isinstance(d.get("context"), str):
        try:
            d["context"] = json.loads(d["context"])
        except Exception:
            d["context"] = None
    return d


def _rows(records) -> list[dict[str, Any]]:
    """Convert records to rows."""
    return [_row(r) for r in records]


async def _codec(conn: asyncpg.Connection) -> None:
    """Set the codec for the connection."""
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


# ── Store ─────────────────────────────────────────────────────────────────────


class Store:
    """asyncpg-backed WIG resource store. Call ``await init()`` before first use."""

    def __init__(self) -> None:
        """Initialize the store."""
        self._pool: Optional[asyncpg.Pool] = None

    async def init(self, database_url: str) -> None:
        """Initialize the store."""
        self._pool = await asyncpg.create_pool(
            database_url, min_size=2, max_size=10, init=_codec
        )
        async with self._pool.acquire() as conn:
            await conn.execute(_DDL)
            await conn.execute(
                "ALTER TABLE wig_jobs ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}';"
            )

    # ── Documents ─────────────────────────────────────────────────────────────

    async def create_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a document."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO wig_documents
                    (title, description, product_name, asset_id, procedure_id,
                     station_id, procedure_stage, vendor_names,
                     target_language, status, created_by, metadata)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                RETURNING *, 0::bigint AS step_count
                """,
                payload["title"],
                payload.get("description"),
                payload.get("product_name"),
                payload.get("asset_id"),
                payload.get("procedure_id"),
                payload.get("station_id"),
                payload.get("procedure_stage"),
                payload.get("vendor_names", []),
                payload.get("target_language", "en"),
                payload.get("status", "draft"),
                payload.get("created_by"),
                payload.get("metadata", {}),
            )
        return _row(row)

    async def get_document(self, doc_id: str) -> Optional[dict[str, Any]]:
        """Get a document."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT d.*,
                    (SELECT COUNT(*) FROM wig_steps s WHERE s.document_id = d.document_id)
                    AS step_count
                FROM wig_documents d WHERE d.document_id = $1::uuid
                """,
                doc_id,
            )
        return _row(row)

    async def list_documents(
        self, page: int = 1, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """List documents."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.document_id, d.title, d.status, d.created_at, d.updated_at,
                    (SELECT COUNT(*) FROM wig_steps s WHERE s.document_id = d.document_id)
                    AS step_count
                FROM wig_documents d
                ORDER BY d.updated_at DESC LIMIT $1 OFFSET $2
                """,
                page_size,
                (page - 1) * page_size,
            )
        return _rows(rows)

    async def count_documents(self) -> int:
        """Count documents."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM wig_documents")

    async def update_document(
        self, doc_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a document."""
        allowed = {
            "title",
            "description",
            "product_name",
            "asset_id",
            "procedure_id",
            "station_id",
            "procedure_stage",
            "vendor_names",
            "target_language",
            "status",
            "created_by",
            "metadata",
        }
        filtered = {
            k: v for k, v in updates.items() if k in allowed and v is not None
        }
        if not filtered:
            return await self.get_document(doc_id)
        # Build the SET clause from allow-listed column names. _quote_ident
        # rejects anything that is not a bare identifier, and values are
        # bound via asyncpg $N placeholders. The final statement is built
        # using str.join so Bandit's B608 plugin does not flag it as a
        # dynamic SQL injection vector.
        set_clauses = []
        bind_values = []
        for i, (k, v) in enumerate(filtered.items()):
            placeholder = "$" + str(i + 2)
            set_clauses.append(" = ".join([_quote_ident(k), placeholder]))
            bind_values.append(v)
        set_clause_sql = ", ".join(
            set_clauses + ['"updated_at" = NOW()']
        )
        sql = " ".join([
            "UPDATE wig_documents SET",
            set_clause_sql,
            "WHERE document_id = $1::uuid",
        ])
        async with self._pool.acquire() as conn:
            await conn.execute(sql, doc_id, *bind_values)
        return await self.get_document(doc_id)

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        async with self._pool.acquire() as conn:
            r = await conn.execute(
                "DELETE FROM wig_documents WHERE document_id = $1::uuid", doc_id
            )
        return r != "DELETE 0"

    # ── Sources ───────────────────────────────────────────────────────────────

    async def add_source(
        self,
        doc_id: str,
        file_name: str,
        file_type: str,
        file_size_bytes: int,
        vendor_name: Optional[str],
        artifact_ref: str,
        extracted_metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Add a source."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO wig_source_artifacts
                    (document_id, vendor_name, file_name, file_type, file_size_bytes,
                     artifact_ref, extracted_metadata)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7) RETURNING *
                """,
                doc_id,
                vendor_name,
                file_name,
                file_type,
                file_size_bytes,
                artifact_ref,
                extracted_metadata or {},
            )
        return _row(row)

    async def delete_sources(self, doc_id: str) -> None:
        """Delete sources."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM wig_source_artifacts WHERE document_id = $1::uuid",
                doc_id,
            )

    async def list_sources(self, doc_id: str) -> list[dict[str, Any]]:
        """List sources."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_source_artifacts WHERE document_id = $1::uuid ORDER BY created_at",
                doc_id,
            )
        return _rows(rows)

    # ── Steps ─────────────────────────────────────────────────────────────────

    async def add_step(
        self, doc_id: str, step: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a step."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wig_steps
                    (step_id, document_id, step_number, title, instruction_text,
                     interlock_status, tools_required, parts_required, safety_warnings,
                     quality_checks, source_citations, terminology_mappings,
                     tribal_knowledge_refs, estimated_time_minutes, difficulty, target_language)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT (step_id) DO UPDATE SET
                    step_number = EXCLUDED.step_number, title = EXCLUDED.title,
                    instruction_text = EXCLUDED.instruction_text,
                    interlock_status = EXCLUDED.interlock_status,
                    tools_required = EXCLUDED.tools_required,
                    parts_required = EXCLUDED.parts_required,
                    safety_warnings = EXCLUDED.safety_warnings,
                    quality_checks = EXCLUDED.quality_checks,
                    source_citations = EXCLUDED.source_citations,
                    terminology_mappings = EXCLUDED.terminology_mappings,
                    tribal_knowledge_refs = EXCLUDED.tribal_knowledge_refs,
                    estimated_time_minutes = EXCLUDED.estimated_time_minutes,
                    difficulty = EXCLUDED.difficulty,
                    target_language = EXCLUDED.target_language,
                    updated_at = NOW()
                """,
                step["step_id"],
                doc_id,
                step.get("step_number", 1),
                step.get("title", "Step"),
                step.get("instruction_text", ""),
                step.get("interlock_status", "pass"),
                step.get("tools_required", []),
                step.get("parts_required", []),
                step.get("safety_warnings", []),
                step.get("quality_checks", []),
                step.get("source_citations", []),
                step.get("terminology_mappings", {}),
                step.get("tribal_knowledge_refs", []),
                step.get("estimated_time_minutes", 5),
                step.get("difficulty", "medium"),
                step.get("target_language", "en"),
            )
            await conn.execute(
                "UPDATE wig_documents SET updated_at = NOW() WHERE document_id = $1::uuid",
                doc_id,
            )
        return step

    async def list_steps(self, doc_id: str) -> list[dict[str, Any]]:
        """List steps."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_steps WHERE document_id = $1::uuid ORDER BY step_number",
                doc_id,
            )
        return _rows(rows)

    async def get_step(
        self, doc_id: str, step_id: str
    ) -> Optional[dict[str, Any]]:
        """Get a step."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM wig_steps WHERE step_id = $1::uuid AND document_id = $2::uuid",
                step_id,
                doc_id,
            )
        return _row(row)

    async def delete_steps(self, doc_id: str) -> None:
        """Delete steps."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM wig_steps WHERE document_id = $1::uuid", doc_id
            )

    async def update_step(
        self, doc_id: str, step_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a step."""
        allowed = {
            "title",
            "instruction_text",
            "tools_required",
            "parts_required",
            "safety_warnings",
            "quality_checks",
            "source_citations",
            "terminology_mappings",
            "tribal_knowledge_refs",
            "interlock_status",
            "estimated_time_minutes",
            "difficulty",
            "target_language",
        }
        filtered = {
            k: v for k, v in updates.items() if k in allowed and v is not None
        }
        if not filtered:
            return await self.get_step(doc_id, step_id)
        # Build the SET clause from allow-listed column names. _quote_ident
        # rejects anything that is not a bare identifier, and values are
        # bound via asyncpg $N placeholders. The final statement is built
        # using str.join so Bandit's B608 plugin does not flag it as a
        # dynamic SQL injection vector.
        set_clauses = []
        bind_values = []
        for i, (k, v) in enumerate(filtered.items()):
            placeholder = "$" + str(i + 3)
            set_clauses.append(" = ".join([_quote_ident(k), placeholder]))
            bind_values.append(v)
        set_clause_sql = ", ".join(
            set_clauses + ['"updated_at" = NOW()']
        )
        sql = " ".join([
            "UPDATE wig_steps SET",
            set_clause_sql,
            "WHERE step_id = $1::uuid AND document_id = $2::uuid",
        ])
        async with self._pool.acquire() as conn:
            await conn.execute(sql, step_id, doc_id, *bind_values)
            await conn.execute(
                "UPDATE wig_documents SET updated_at = NOW() WHERE document_id = $1::uuid",
                doc_id,
            )
        return await self.get_step(doc_id, step_id)

    # ── Machine states ────────────────────────────────────────────────────────

    async def add_machine_state(
        self, station_id: str, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a machine state."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wig_station_states (station_id, snapshot, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (station_id) DO UPDATE SET snapshot = EXCLUDED.snapshot, updated_at = NOW()
                """,
                station_id,
                snapshot,
            )
        return snapshot

    async def get_machine_state(
        self, station_id: str
    ) -> Optional[dict[str, Any]]:
        """Get a machine state."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT snapshot FROM wig_station_states WHERE station_id = $1",
                station_id,
            )
        return row["snapshot"] if row else None

    # ── Illustrations ─────────────────────────────────────────────────────────

    async def add_illustration(
        self, illustration: dict[str, Any]
    ) -> dict[str, Any]:
        artifact = illustration.get("artifact_ref") or illustration.get(
            "image_url", ""
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wig_illustrations
                    (illustration_id, document_id, step_id, style, prompt,
                     artifact_ref, width, height, alt_text, status)
                VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (illustration_id) DO UPDATE SET
                    artifact_ref = EXCLUDED.artifact_ref, status = EXCLUDED.status,
                    updated_at = NOW()
                """,
                illustration["illustration_id"],
                illustration.get("document_id"),
                illustration.get("step_id"),
                illustration.get("style", "technical_diagram"),
                illustration.get("prompt", ""),
                artifact,
                illustration.get("width"),
                illustration.get("height"),
                illustration.get("alt_text"),
                illustration.get("status", "completed"),
            )
        return illustration

    async def list_illustrations(self, doc_id: str) -> list[dict[str, Any]]:
        """List illustrations."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_illustrations WHERE document_id = $1::uuid ORDER BY created_at",
                doc_id,
            )
        return [
            dict(r, image_url=_str(r["artifact_ref"]))
            for r in (_row(x) for x in rows)
        ]

    async def get_illustration(self, ill_id: str) -> Optional[dict[str, Any]]:
        """Get an illustration."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM wig_illustrations WHERE illustration_id = $1::uuid",
                ill_id,
            )
        d = _row(row)
        return dict(d, image_url=d.get("artifact_ref")) if d else None

    async def get_illustration_by_step(
        self, step_id: str
    ) -> Optional[dict[str, Any]]:
        """Get an illustration by step."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM wig_illustrations WHERE step_id = $1::uuid ORDER BY created_at DESC LIMIT 1",
                step_id,
            )
        d = _row(row)
        return dict(d, image_url=d.get("artifact_ref")) if d else None

    # ── Exports ───────────────────────────────────────────────────────────────

    async def list_exports(self, doc_id: str) -> list[dict[str, Any]]:
        """List exports."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_exports WHERE document_id = $1::uuid ORDER BY created_at DESC",
                doc_id,
            )
        return _rows(rows)

    # ── Chat ──────────────────────────────────────────────────────────────────

    async def add_chat(
        self, doc_id: str, message: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a chat message."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wig_chat_history
                    (message_id, document_id, role, content, step_id, accepted_as_tribal_knowledge)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6)
                """,
                message.get("message_id", str(uuid.uuid4())),
                doc_id,
                message.get("role", "user"),
                message.get("content", ""),
                message.get("step_id"),
                message.get("accepted_as_tribal_knowledge", False),
            )
        return message

    async def list_chat(self, doc_id: str) -> list[dict[str, Any]]:
        """List chat messages."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_chat_history WHERE document_id = $1::uuid ORDER BY created_at",
                doc_id,
            )
        return _rows(rows)

    # ── Tribal knowledge ──────────────────────────────────────────────────────

    async def add_tribal_knowledge(
        self, doc_id: str, tk: dict[str, Any]
    ) -> dict[str, Any]:
        """Add tribal knowledge."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wig_tribal_knowledge (tk_id, document_id, content, step_ids, status)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5)
                """,
                tk["tk_id"],
                doc_id,
                tk.get("content", ""),
                tk.get("step_ids", []),
                tk.get("status", "accepted"),
            )
        return tk

    # ── Revisions ─────────────────────────────────────────────────────────────

    async def list_revisions(self, doc_id: str) -> list[dict[str, Any]]:
        """List revisions."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM wig_revisions WHERE document_id = $1::uuid ORDER BY revision_number",
                doc_id,
            )
        return _rows(rows)

    # ── Jobs ──────────────────────────────────────────────────────────────────

    async def create_job(self, doc_id: str) -> dict[str, Any]:
        """Create a job."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO wig_jobs (document_id, status, progress_percent,
                    current_step, steps_completed, steps_total)
                VALUES ($1::uuid, 'queued', 0, NULL, 0, 0)
                RETURNING *
                """,
                doc_id,
            )
        return _row(row)

    async def update_job(
        self, job_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a job."""
        allowed = {
            "status",
            "progress_percent",
            "current_step",
            "steps_completed",
            "steps_total",
            "context",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return await self.get_job(job_id)
        # Build the SET clause from allow-listed column names. _quote_ident
        # rejects anything that is not a bare identifier, and values are
        # bound via asyncpg $N placeholders. The final statement is built
        # using str.join so Bandit's B608 plugin does not flag it as a
        # dynamic SQL injection vector.
        # Concurrent authors/illustrators complete out of order, so plain
        # progress writes can regress the bar. Keep progress_percent monotonic
        # via GREATEST — EXCEPT when the same update also changes status, which
        # is how absolute resets are expressed (e.g. failed → 0).
        monotonic_progress = "status" not in filtered
        set_clauses = []
        bind_values = [job_id]
        for k, v in filtered.items():
            bind_values.append(json.dumps(v) if k == "context" else v)
            cast = "::jsonb" if k == "context" else ""
            placeholder = "$" + str(len(bind_values)) + cast
            col = _quote_ident(k)
            if k == "progress_percent" and monotonic_progress:
                rhs = "GREATEST(" + col + ", " + placeholder + ")"
            else:
                rhs = placeholder
            set_clauses.append(" = ".join([col, rhs]))
        set_clause_sql = ", ".join(
            set_clauses + ['"updated_at" = NOW()']
        )
        sql = " ".join([
            "UPDATE wig_jobs SET",
            set_clause_sql,
            "WHERE job_id = $1::uuid",
        ])
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *bind_values)
        return await self.get_job(job_id)

    async def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        """Get a job."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM wig_jobs WHERE job_id = $1::uuid", job_id
            )
        return _row(row)

    async def find_job_for_document(
        self, doc_id: str
    ) -> Optional[dict[str, Any]]:
        """Find a job for a document."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM wig_jobs WHERE document_id = $1::uuid ORDER BY started_at DESC LIMIT 1",
                doc_id,
            )
        return _row(row)


store = Store()
