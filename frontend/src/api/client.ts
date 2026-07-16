// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import type { InstructionStep, WigDocument, SourceArtifact, GenerationStatus, ProcedureStage } from '../types';

const BASE = '/api/v1/wig';

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} → ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface DocumentCreate {
  title: string;
  description?: string;
  procedure_id?: string;
  station_id?: string;
  vendor_names?: string[];
  target_language?: string;
}

export interface PaginatedDocuments {
  items: Array<{
    document_id: string;
    title: string;
    status: string;
    step_count: number;
    created_at: string;
    updated_at: string;
  }>;
  total: number;
  page: number;
  page_size: number;
}

export interface GenerateRequest {
  illustration_style?: string;
  target_language?: string;
  dynamic?: boolean;
  station_id?: string;
  machine_state_snapshot?: Record<string, unknown> | null;
}

export interface GenerateResponse {
  job_id: string;
  status: string;
  progress_percent: number;
  current_step: string | null;
}

export interface ExportRequest {
  format: 'pdf' | 'html' | 'json';
  include_illustrations?: boolean;
}

export interface ExportResponse {
  export_id: string;
  format: string;
  status: string;
  download_url: string | null;
  file_size_bytes: number | null;
}

export interface ChatMessageRequest {
  content: string;
  role?: string;
  step_id?: string | null;
  mark_as_tribal_knowledge?: boolean;
}

export interface ChatResponse {
  message_id: string;
  content: string;
  suggestions: string[];
  affected_steps: string[];
}

export interface ProcedureSummary {
  procedure_id: string;
  name: string;
  stage: ProcedureStage;
  station_id: string;
  work_instruction_doc_id: string | null;
}

export interface ReferenceDocument {
  document_id: string;
  file_name: string;
  title: string;
  category: 'sop' | 'procedure';
  pages: number;
  version: string;
  vendor: string | null;
  pdf_path: string | null;
}

export const api = {
  // Documents
  createDocument: (payload: DocumentCreate) =>
    req<WigDocument>('POST', `${BASE}/documents`, payload),

  listDocuments: (page = 1, pageSize = 20) =>
    req<PaginatedDocuments>('GET', `${BASE}/documents?page=${page}&page_size=${pageSize}`),

  // Generation
  generate: (docId: string, payload?: GenerateRequest) =>
    req<GenerateResponse>('POST', `${BASE}/documents/${docId}/generate`, payload ?? {}),

  getStatus: (docId: string) =>
    req<GenerationStatus>('GET', `${BASE}/documents/${docId}/status`),

  // Steps
  listSteps: (docId: string) =>
    req<InstructionStep[]>('GET', `${BASE}/documents/${docId}/steps`),

  regenerateStep: (docId: string, stepId: string, payload?: { step_description?: string; target_language?: string }) =>
    req<InstructionStep>('POST', `${BASE}/documents/${docId}/steps/${stepId}/regenerate`, payload),

  // Chat
  postChat: (docId: string, msg: ChatMessageRequest) =>
    req<ChatResponse>('POST', `${BASE}/documents/${docId}/chat`, msg),

  // Export
  exportDocument: (docId: string, payload: ExportRequest) =>
    req<ExportResponse>('POST', `${BASE}/documents/${docId}/export`, payload),

  // Sources
  listSources: (docId: string) =>
    req<SourceArtifact[]>('GET', `${BASE}/documents/${docId}/sources`),

  // Catalog
  listProcedures: () =>
    req<ProcedureSummary[]>('GET', `${BASE}/procedures`),

  listReferenceDocuments: () =>
    req<ReferenceDocument[]>('GET', `${BASE}/reference-documents`),
};
