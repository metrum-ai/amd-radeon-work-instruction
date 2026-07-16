# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Pydantic models for WIG REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

# ── Document Models ────────────────────────────────────────────────────────


class DocumentCreate(BaseModel):
    """Create a new document."""

    title: str
    description: Optional[str] = None
    product_name: Optional[str] = None
    asset_id: Optional[str] = None
    procedure_id: Optional[str] = None
    station_id: Optional[str] = None
    procedure_stage: Optional[
        Literal[
            "cell_processing", "module_assembly", "pack_integration", "qc_eol"
        ]
    ] = None
    vendor_names: list[str] = []
    target_language: str = "en"
    created_by: Optional[str] = None


class DocumentResponse(BaseModel):
    """Response for a document."""

    document_id: str
    title: str
    description: Optional[str] = None
    product_name: Optional[str] = None
    asset_id: Optional[str] = None
    procedure_id: Optional[str] = None
    station_id: Optional[str] = None
    procedure_stage: Optional[str] = None
    vendor_names: list[str] = []
    target_language: str = "en"
    status: Literal["draft", "generating", "generated"] = "draft"
    step_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class DocumentSummary(BaseModel):
    """Summary of a document."""

    document_id: str
    title: str
    status: str
    step_count: int
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(BaseModel):
    """Paginated response for a list of documents."""

    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int


class DocumentDetail(DocumentResponse):
    """Detail of a document."""

    steps: list[StepResponse] = []
    revisions: list[RevisionSummary] = []
    exports: list[ExportSummary] = []


# ── Step Models ────────────────────────────────────────────────────────────


class StepResponse(BaseModel):
    """Response for a step."""

    step_id: str
    step_number: int
    title: str
    instruction_text: str
    machine_state_ref: Optional[str] = None
    interlock_status: Literal["pass", "blocked"] = "pass"
    tools_required: list[str] = []
    parts_required: list[str] = []
    safety_warnings: list[str] = []
    quality_checks: list[str] = []
    source_citations: list[str] = []
    terminology_mappings: dict[str, str] = {}
    tribal_knowledge_refs: list[str] = []
    illustration_url: Optional[str] = None
    difficulty: str = "medium"
    estimated_time_minutes: int = 5
    target_language: str = "en"
    # Degraded-content signals: set when the authoring LLM was offline or a
    # translation failed, so the UI can flag operator-facing content.
    degraded: bool = False
    llm_status: str = "ok"
    translation_failed: bool = False


class StepUpdate(BaseModel):
    """Update a step."""

    title: Optional[str] = None
    instruction_text: Optional[str] = None
    tools_required: Optional[list[str]] = None
    parts_required: Optional[list[str]] = None
    safety_warnings: Optional[list[str]] = None
    quality_checks: Optional[list[str]] = None


# ── Generation Models ──────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Request to generate a document."""

    illustration_style: str = "technical_diagram"
    include_safety: bool = True
    enforce_loto: bool = True
    enforce_plant_terminology: bool = True
    target_audience: Literal["operator", "technician", "engineer"] = "operator"
    target_language: str = "en"
    dynamic: bool = False
    station_id: Optional[str] = None
    use_latest_machine_state: bool = True
    machine_state_snapshot: Optional[dict[str, Any]] = None


class GenerateResponse(BaseModel):
    """Response to a generate request."""

    job_id: str
    status: Literal[
        "queued",
        "analyzing",
        "generating",
        "illustrating",
        "completed",
        "failed",
    ]
    progress_percent: int = 0
    current_step: Optional[str] = None


class GenerationStatus(BaseModel):
    """Status of a generation request."""

    job_id: str
    status: str
    progress_percent: int = 0
    current_step: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0
    estimated_remaining_seconds: Optional[int] = None
    context: Optional[dict[str, Any]] = None


class DynamicInstructionRequest(BaseModel):
    """Request to generate a dynamic instruction."""

    procedure_id: str
    station_id: str
    target_language: str = "en"
    target_audience: Literal["operator", "technician", "engineer"] = "operator"
    use_latest_machine_state: bool = True
    operator_context: dict[str, Any] = {}


class RegenerateRequest(BaseModel):
    """Request to regenerate a step."""

    step_description: Optional[str] = None
    target_language: Optional[str] = None
    target_audience: Optional[Literal["operator", "technician", "engineer"]] = (
        None
    )


# ── Station / Machine State Models ─────────────────────────────────────────


class StationSummary(BaseModel):
    """Summary of a station."""

    station_id: str
    name: str
    procedure_area: str
    state: str = "unknown"
    has_simulator: bool = True


class ProcedureSummary(BaseModel):
    """Summary of an assembly procedure selectable on the machine floor."""

    procedure_id: str
    name: str
    stage: Literal[
        "cell_processing", "module_assembly", "pack_integration", "qc_eol"
    ]
    station_id: str
    work_instruction_doc_id: Optional[str] = None


class MachineStateResponse(BaseModel):
    """Response for a machine state."""

    state_id: str
    station_id: str
    procedure_id: Optional[str] = None
    source: Literal[
        "mock_simulator",
        "python_machine_simulator",
        "opcua",
        "mqtt",
        "mes",
        "scada",
        "historian",
    ] = "mock_simulator"
    state: str
    active_alarms: list[dict[str, Any]] = []
    readiness_flags: dict[str, bool] = {}
    quality_readings: dict[str, Any] = {}
    last_completed_step: Optional[str] = None
    created_at: datetime


class SimulatorStateUpdate(BaseModel):
    """Update a machine state."""

    state: str
    active_alarms: list[dict[str, Any]] = []
    readiness_flags: dict[str, bool] = {}
    quality_readings: dict[str, Any] = {}
    last_completed_step: Optional[str] = None


# ── Illustration Models ────────────────────────────────────────────────────


class IllustrationResponse(BaseModel):
    """Response for an illustration."""

    illustration_id: str
    step_id: Optional[str] = None
    style: str
    image_url: str
    width: int
    height: int
    status: str = "completed"


class IllustrationRequest(BaseModel):
    """Request for an illustration."""

    style: Optional[str] = None
    prompt_override: Optional[str] = None


# ── Export Models ──────────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    """Request for an export."""

    format: Literal["pdf", "html", "json"] = "pdf"
    include_illustrations: bool = True


class ExportResponse(BaseModel):
    """Response for an export."""

    export_id: str
    format: str
    status: Literal["generating", "completed", "failed"] = "completed"
    download_url: Optional[str] = None
    file_size_bytes: Optional[int] = None


class ExportSummary(BaseModel):
    """Summary of an export."""

    export_id: str
    format: str
    file_size_bytes: Optional[int] = None
    created_at: datetime


class RevisionSummary(BaseModel):
    """Summary of a revision."""

    revision_id: str
    revision_number: int
    change_summary: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


# ── Chat Models ────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """Message for a chat."""

    content: str
    step_id: Optional[str] = None
    mark_as_tribal_knowledge: bool = False


class ChatResponse(BaseModel):
    """Response for a chat."""

    message_id: str
    content: str
    suggestions: list[str] = []
    affected_steps: list[str] = []


# ── Reference Document Models ──────────────────────────────────────────────


class ReferenceDocument(BaseModel):
    """Bundled SOP or work-instruction PDF available for reference/preview."""

    document_id: str
    file_name: str
    title: str
    category: Literal["sop", "procedure"]
    pages: int = 0
    version: str = "v1"
    vendor: Optional[str] = None
    pdf_path: Optional[str] = None


# ── Source Artifact Models ─────────────────────────────────────────────────


class SourceArtifact(BaseModel):
    """Source artifact."""

    source_id: str
    vendor_name: Optional[str] = None
    file_name: str
    file_type: str
    artifact_ref: Optional[str] = None
    extracted_metadata: dict[str, Any] = {}
