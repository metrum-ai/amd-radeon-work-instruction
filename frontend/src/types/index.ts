// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

export type DocumentStatus = 'draft' | 'generating' | 'generated';
export type ProcedureStage = 'cell_processing' | 'module_assembly' | 'pack_integration' | 'qc_eol';
export type InterlockStatus = 'pass' | 'blocked';
export type Difficulty = 'easy' | 'medium' | 'hard';

export interface WigDocument {
  document_id: string;
  title: string;
  description: string | null;
  product_name: string | null;
  asset_id: string | null;
  procedure_id: string | null;
  station_id: string | null;
  procedure_stage: ProcedureStage | null;
  vendor_names: string[];
  target_language: string;
  status: DocumentStatus;
  step_count: number;
  created_at: string;
  updated_at: string;
}

export interface InstructionStep {
  step_id: string;
  step_number: number;
  title: string;
  instruction_text: string;
  machine_state_ref: string | null;
  interlock_status: InterlockStatus;
  tools_required: string[];
  parts_required: string[];
  safety_warnings: string[];
  quality_checks: string[];
  source_citations: string[];
  terminology_mappings: Record<string, string>;
  tribal_knowledge_refs: string[];
  illustration_url: string | null;
  difficulty: Difficulty;
  estimated_time_minutes: number;
}

export interface MachineState {
  state_id: string;
  station_id: string;
  procedure_id: string | null;
  source: string;
  state: string;
  active_alarms: Alarm[];
  readiness_flags: Record<string, boolean>;
  quality_readings: Record<string, string | number>;
  last_completed_step: string | null;
  created_at: string;
}

export interface Alarm {
  code: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  message?: string;
}

export interface Illustration {
  illustration_id: string;
  step_id: string | null;
  style: string;
  image_url: string;
  width: number;
  height: number;
}

export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  step_id: string | null;
  accepted_as_tribal_knowledge: boolean;
  created_at: string;
}

export interface SourceArtifact {
  source_id: string;
  vendor_name: string | null;
  file_name: string;
  file_type: string;
  artifact_ref: string | null;
  extracted_metadata: Record<string, unknown>;
}

export interface StationSummary {
  station_id: string;
  name: string;
  type: string;
  status: 'online' | 'offline' | 'fault';
}

export interface Procedure {
  id: string;
  name: string;
  stage: ProcedureStage;
  station_id: string;
  wiDocId?: string;
}

export interface RefDoc {
  id: string;
  name: string;
  category: 'safety' | 'compliance' | 'sop' | 'quality' | 'training' | 'procedure' | 'manual';
  fileName: string;
  pages: number;
  version: string;
  description: string;
  pdfUrl?: string;
}

export interface HistoryReport {
  id: string;
  title: string;
  procedure: string;
  status: string;
  stepCount: number;
  generatedAt: string;
  language: string;
}

export interface AvailableDoc {
  id: string;
  fileName: string;
  title: string;
  category: 'sop' | 'procedure';
  pages: number;
  version: string;
  vendor?: string;
  pdf_path?: string;
}

export interface GenerationContext {
  doc_title?: string;
  procedure_name?: string;
  station_id?: string;
  machine_id?: string;
  machine_state?: string;
  active_alarms?: number;
  readiness_flags?: Record<string, boolean>;
  quality_readings?: Record<string, string | number>;
  safety_warnings?: number;
  loto_rules?: number;
  proc_chunks?: number;
  sop_chunks?: number;
  manual_chunks?: number;
  llm_model?: string;
  translate_model?: string;
  interlock_status?: string;
  interlock_reasons?: string[];
  steps_planned?: number;
  current_step_desc?: string;
}

export interface GenerationStatus {
  job_id: string;
  status: string;
  progress_percent: number;
  current_step?: string | null;
  steps_completed: number;
  steps_total: number;
  estimated_remaining_seconds?: number | null;
  context?: GenerationContext | null;
}

// ISA-88 / IEC 62264 PackML states
export type FloorMachineStatus =
  | 'Execute'
  | 'Idle'
  | 'Starting'
  | 'Completing'
  | 'Complete'
  | 'Held'
  | 'Aborted';

export interface MachineGauge {
  key: string;
  label: string;
  value: number;
  unit: string;
  max: number;
}

export interface MachineDoc {
  doc_id: string;
  file_name: string;
  display_name?: string; // localized title for display, e.g. native-language manual name
  file_type: string;
  language: string;
  pages?: number;
  pdf_path?: string; // URL path served by nginx, e.g. /manuals/KUKA_Assembly_Guide_Rev_C.de.pdf
}

export interface FloorMachine {
  id: string;
  name: string;
  vendor: string;
  origin: string;
  type: string;
  serial_number: string;
  firmware_version: string;
  install_date: string;
  cycles_completed: number;
  hours_run: number;
  status: FloorMachineStatus;
  gauges: MachineGauge[];
  readiness: Record<string, boolean>;
  fault_prone: boolean;
  docs: MachineDoc[];
}
