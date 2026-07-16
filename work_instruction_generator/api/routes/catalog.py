# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Static procedure and reference-document catalog routes for WIG.

Backs the machine-floor procedure selector and the bundled-documents
popup — both previously read from a hardcoded frontend mock (removed).
"""

from fastapi import APIRouter

from work_instruction_generator.api.models import (
    ProcedureSummary,
    ReferenceDocument,
)

router = APIRouter(prefix="/api/v1/wig", tags=["catalog"])

# The 9 EV battery pack assembly procedures loaded and selectable from the
# machine floor (see README "Introduction").
_PROCEDURES: list[ProcedureSummary] = [
    ProcedureSummary(
        procedure_id="cell_inspection",
        name="Cell Inspection & Sorting",
        stage="cell_processing",
        station_id="cell_tester",
        work_instruction_doc_id="wi-001",
    ),
    ProcedureSummary(
        procedure_id="module_bonding",
        name="Module Bonding & Adhesive",
        stage="module_assembly",
        station_id="dispenser",
        work_instruction_doc_id="wi-002",
    ),
    ProcedureSummary(
        procedure_id="tab_busbar_welding",
        name="Electrical Joining / Laser Welding",
        stage="module_assembly",
        station_id="welder",
        work_instruction_doc_id="wi-003",
    ),
    ProcedureSummary(
        procedure_id="tim_application",
        name="Thermal Interface Assembly",
        stage="module_assembly",
        station_id="tim_dispenser",
        work_instruction_doc_id="wi-004",
    ),
    ProcedureSummary(
        procedure_id="hv_harness_routing",
        name="HV Integration",
        stage="pack_integration",
        station_id="hv_bench",
        work_instruction_doc_id="wi-005",
    ),
    ProcedureSummary(
        procedure_id="enclosure_sealing",
        name="Enclosure Sealing",
        stage="pack_integration",
        station_id="sealing_dispenser",
        work_instruction_doc_id="wi-006",
    ),
    ProcedureSummary(
        procedure_id="leak_test_troubleshooting",
        name="Leak Testing",
        stage="qc_eol",
        station_id="leak_tester",
        work_instruction_doc_id="wi-007",
    ),
    ProcedureSummary(
        procedure_id="hipot_testing",
        name="Hi-Pot Testing",
        stage="qc_eol",
        station_id="hipot_tester",
        work_instruction_doc_id="wi-008",
    ),
    ProcedureSummary(
        procedure_id="eol_functional_test",
        name="EOL Functional Test",
        stage="qc_eol",
        station_id="eol_rig",
        work_instruction_doc_id="wi-009",
    ),
]

# Bundled SOPs and per-procedure work-instruction PDFs served by nginx from
# /sop-docs and /procedure-docs (see oem_ingest/documents/).
_REFERENCE_DOCUMENTS: list[ReferenceDocument] = [
    ReferenceDocument(
        document_id="sop-001",
        file_name="SOP-LOTO-001_Lockout-Tagout-Policy.pdf",
        title="LOTO-001: Lockout/Tagout Policy",
        category="sop",
        pdf_path="/sop-docs/SOP-LOTO-001_Lockout-Tagout-Policy.pdf",
    ),
    ReferenceDocument(
        document_id="sop-002",
        file_name="SOP-PPE-002_PPE-Requirements-By-Station.pdf",
        title="PPE-002: PPE Requirements by Station",
        category="sop",
        pdf_path="/sop-docs/SOP-PPE-002_PPE-Requirements-By-Station.pdf",
    ),
    ReferenceDocument(
        document_id="sop-003",
        file_name="SOP-TERM-003_Plant-Terminology-Dictionary.pdf",
        title="TERM-003: Plant Terminology Dictionary",
        category="sop",
        pdf_path="/sop-docs/SOP-TERM-003_Plant-Terminology-Dictionary.pdf",
    ),
    ReferenceDocument(
        document_id="sop-004",
        file_name="SOP-INTLK-004_EV-Station-Interlock-Rules.pdf",
        title="INTLK-004: EV Station Interlock Rules",
        category="sop",
        pdf_path="/sop-docs/SOP-INTLK-004_EV-Station-Interlock-Rules.pdf",
    ),
    ReferenceDocument(
        document_id="sop-005",
        file_name="SOP-SAFE-005_EV-HV-Safety-Guidelines.pdf",
        title="SAFE-005: EV HV Safety Guidelines",
        category="sop",
        pdf_path="/sop-docs/SOP-SAFE-005_EV-HV-Safety-Guidelines.pdf",
    ),
    ReferenceDocument(
        document_id="sop-006",
        file_name="SOP-QUAL-006_Quality-Standards-Reference.pdf",
        title="QUAL-006: Quality Standards Reference",
        category="sop",
        pdf_path="/sop-docs/SOP-QUAL-006_Quality-Standards-Reference.pdf",
    ),
    ReferenceDocument(
        document_id="sop-007",
        file_name="SOP-MAT-007_Material-Handling-Guide.pdf",
        title="MAT-007: Material Handling Guide",
        category="sop",
        pdf_path="/sop-docs/SOP-MAT-007_Material-Handling-Guide.pdf",
    ),
    ReferenceDocument(
        document_id="sop-008",
        file_name="SOP-TRBL-008_Troubleshooting-Trees.pdf",
        title="TRBL-008: Troubleshooting Trees",
        category="sop",
        pdf_path="/sop-docs/SOP-TRBL-008_Troubleshooting-Trees.pdf",
    ),
    ReferenceDocument(
        document_id="sop-009",
        file_name="SOP-TRIBAL-009_Approved-Workarounds.pdf",
        title="TRIBAL-009: Approved Workarounds",
        category="sop",
        pdf_path="/sop-docs/SOP-TRIBAL-009_Approved-Workarounds.pdf",
    ),
    ReferenceDocument(
        document_id="wi-001",
        file_name="WI-CEL-001_Cell-Inspection-Sorting.pdf",
        title="WI-CEL-001: Cell Inspection & Sorting",
        category="procedure",
        pdf_path="/procedure-docs/WI-CEL-001_Cell-Inspection-Sorting.pdf",
    ),
    ReferenceDocument(
        document_id="wi-002",
        file_name="WI-MOD-002_Module-Bonding-Adhesive.pdf",
        title="WI-MOD-002: Module Bonding & Adhesive",
        category="procedure",
        pdf_path="/procedure-docs/WI-MOD-002_Module-Bonding-Adhesive.pdf",
    ),
    ReferenceDocument(
        document_id="wi-003",
        file_name="WI-ELJ-003_Electrical-Joining-Laser-Welding.pdf",
        title="WI-ELJ-003: Electrical Joining / Laser Welding",
        category="procedure",
        pdf_path=(
            "/procedure-docs/"
            "WI-ELJ-003_Electrical-Joining-Laser-Welding.pdf"
        ),
    ),
    ReferenceDocument(
        document_id="wi-004",
        file_name="WI-TIM-004_Thermal-Interface-Assembly.pdf",
        title="WI-TIM-004: Thermal Interface Assembly",
        category="procedure",
        pdf_path="/procedure-docs/WI-TIM-004_Thermal-Interface-Assembly.pdf",
    ),
    ReferenceDocument(
        document_id="wi-005",
        file_name="WI-HVI-005_HV-Integration.pdf",
        title="WI-HVI-005: HV Integration",
        category="procedure",
        pdf_path="/procedure-docs/WI-HVI-005_HV-Integration.pdf",
    ),
    ReferenceDocument(
        document_id="wi-006",
        file_name="WI-ENC-006_Enclosure-Sealing.pdf",
        title="WI-ENC-006: Enclosure Sealing",
        category="procedure",
        pdf_path="/procedure-docs/WI-ENC-006_Enclosure-Sealing.pdf",
    ),
    ReferenceDocument(
        document_id="wi-007",
        file_name="WI-LKT-007_Leak-Testing.pdf",
        title="WI-LKT-007: Leak Testing",
        category="procedure",
        pdf_path="/procedure-docs/WI-LKT-007_Leak-Testing.pdf",
    ),
    ReferenceDocument(
        document_id="wi-008",
        file_name="WI-HPT-008_HiPot-Testing.pdf",
        title="WI-HPT-008: Hi-Pot Testing",
        category="procedure",
        pdf_path="/procedure-docs/WI-HPT-008_HiPot-Testing.pdf",
    ),
    ReferenceDocument(
        document_id="wi-009",
        file_name="WI-EOL-009_EOL-Functional-Test.pdf",
        title="WI-EOL-009: EOL Functional Test",
        category="procedure",
        pdf_path="/procedure-docs/WI-EOL-009_EOL-Functional-Test.pdf",
    ),
]


@router.get("/procedures", response_model=list[ProcedureSummary])
async def list_procedures() -> list[ProcedureSummary]:
    """List the assembly procedures selectable on the machine floor."""
    return _PROCEDURES


@router.get(
    "/reference-documents", response_model=list[ReferenceDocument]
)
async def list_reference_documents() -> list[ReferenceDocument]:
    """List bundled SOP and work-instruction reference documents."""
    return _REFERENCE_DOCUMENTS
