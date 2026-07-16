// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { FileText, ShieldCheck, Scale, BookOpen, ClipboardCheck, GraduationCap, X, FileStack, Cpu, AlertTriangle } from 'lucide-react';
import TopBar from './components/TopBar/TopBar';
import MachineFloor from './components/MachineFloor/MachineFloor';
import MetricsPanel from './components/MetricsPanel/MetricsPanel';
import StepViewer from './components/StepViewer/StepViewer';
import StepIllustration from './components/StepIllustration/StepIllustration';
import PreviewModal from './components/PreviewModal/PreviewModal';
import PreviewPane from './components/PreviewPane/PreviewPane';
import ExportBar from './components/ExportBar/ExportBar';
import HistoryDrawer from './components/HistoryDrawer/HistoryDrawer';
import DocumentsPopup from './components/DocumentsPopup/DocumentsPopup';
import type { FloorMachine, MachineState, InstructionStep, WigDocument, SourceArtifact, Procedure, HistoryReport, RefDoc, AvailableDoc } from './types';
import PipelineTracker from './components/PipelineTracker/PipelineTracker';
import type { GenerationStatus } from './types';
import { api } from './api/client';
import './App.css';

const CAT_ICON: Record<RefDoc['category'], typeof ShieldCheck> = {
  safety: ShieldCheck,
  compliance: Scale,
  sop: BookOpen,
  quality: ClipboardCheck,
  training: GraduationCap,
  procedure: FileText,
  manual: Cpu,
};

const COLLECTION_CATEGORY: Record<string, RefDoc['category']> = {
  procedure_docs: 'procedure',
  sop_docs: 'sop',
  machine_manuals: 'manual',
};

function RefDocModal({ doc, onClose }: { doc: RefDoc; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="mf-modal-backdrop" onClick={onClose}>
      <div className="mf-modal" onClick={e => e.stopPropagation()}>
        <div className="mf-modal__header">
          <div className="mf-modal__title-row">
            <FileText size={14} />
            <span className="mf-modal__title">{doc.fileName}</span>
          </div>
          <button className="mf-modal__close" onClick={onClose} aria-label="Close"><X size={14} /></button>
        </div>

        <div className="mf-modal__body">
          {doc.pdfUrl ? (
            <iframe
              src={doc.pdfUrl}
              className="mf-modal__pdf-embed"
              title={doc.fileName}
            />
          ) : (
            <div className="mf-modal__pdf-preview">
              <FileText size={48} strokeWidth={1} />
              <span className="mf-modal__placeholder-text">PDF not available</span>
            </div>
          )}
        </div>

        <div className="mf-modal__footer">
          {doc.version && <span className="mf-modal__file-type">{doc.version}</span>}
          {doc.description && <span className="mf-modal__file-type">{doc.description}</span>}
        </div>
      </div>
    </div>
  );
}

function App() {
  // Machine floor — live via SSE from /api/v1/machine-stream
  const [liveMachines, setLiveMachines] = useState<FloorMachine[] | null>(null);
  const [stationState, setStationState] = useState<MachineState | null>(null);
  // Mirror stationState into a ref so handleGenerate always reads the latest SSE
  // snapshot without being recreated (and re-memoized) on every stream tick.
  const stationStateRef = useRef<MachineState | null>(null);
  useEffect(() => {
    stationStateRef.current = stationState;
  }, [stationState]);

  useEffect(() => {
    const es = new EventSource('/api/v1/machine-stream');
    es.onmessage = (event) => {
      try {
        const snapshot = JSON.parse(event.data);
        if (Array.isArray(snapshot.machines) && snapshot.machines.length > 0) {
          setLiveMachines(snapshot.machines as FloorMachine[]);
        }
        if (snapshot.station_state) {
          setStationState(snapshot.station_state as MachineState);
        }
      } catch {
        // ignore malformed frames
      }
    };
    return () => es.close();
  }, []);

  const machines = liveMachines ?? [];

  // API-backed document + steps state
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [apiDocument, setApiDocument] = useState<WigDocument | null>(null);
  const [apiSteps, setApiSteps] = useState<InstructionStep[] | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showPipeline, setShowPipeline] = useState(false);
  const [genStatus, setGenStatus] = useState<GenerationStatus | null>(null);
  const [apiHistoryItems, setApiHistoryItems] = useState<HistoryReport[] | null>(null);
  const [apiSources, setApiSources] = useState<SourceArtifact[] | null>(null);
  const [apiProcedures, setApiProcedures] = useState<Procedure[]>([]);
  const [apiAllDocs, setApiAllDocs] = useState<AvailableDoc[]>([]);
  const [refiningStepId, setRefiningStepId] = useState<string | null>(null);
  const [refinedStepIds, setRefinedStepIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<number | null>(null);
  const refineIllPollRef = useRef<number | null>(null);
  // Synchronous re-entrancy guard: prevents a double-click from firing a second
  // generation (which would clear the first run's poll interval and orphan its
  // pending promise). A ref is used because setIsGenerating is async.
  const generatingRef = useRef(false);

  const steps = apiSteps ?? [];
  const activeDocument = apiDocument;

  const [selectedProcedure, setSelectedProcedure] = useState('module_bonding');
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [format, setFormat] = useState('pdf');
  const [language, setLanguage] = useState('en');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [generateKey, setGenerateKey] = useState(0);
  // Separate trigger for refetching the document history, bumped after a
  // generation completes (generateKey remounts StepViewer at generation start).
  const [historyKey, setHistoryKey] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(true);
  const [historyPreview, setHistoryPreview] = useState<HistoryReport | null>(null);
  const [historySteps, setHistorySteps] = useState<InstructionStep[]>([]);
  const [refDocPreview, setRefDocPreview] = useState<RefDoc | null>(null);
  const [docsOpen, setDocsOpen] = useState(false);
  const [docPreview, setDocPreview] = useState<AvailableDoc | null>(null);
  const [refDocsOpen, setRefDocsOpen] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);

  // Reset document when procedure changes
  useEffect(() => {
    setDocumentId(null);
    setApiDocument(null);
    setApiSteps(null);
    setApiSources(null);
    setSelectedStepId(null);
    setGenStatus(null);
    setRefinedStepIds(new Set());
  }, [selectedProcedure]);

  // Fetch generated document list on mount and after each generation (drives history drawer)
  useEffect(() => {
    api.listDocuments().then(data => {
      // Always set the mapped array (including []) so an empty backend resolves
      // the loading state instead of staying stuck on null forever.
      setApiHistoryItems(data.items.map(d => ({
        id: d.document_id,
        title: d.title,
        procedure: d.title,
        status: d.status,
        stepCount: d.step_count,
        generatedAt: d.created_at,
        language: 'EN',
      })));
    }).catch(() => {});
  }, [historyKey]);

  // Fetch the procedure and reference-document catalogs once on mount
  useEffect(() => {
    api.listProcedures().then(data => {
      setApiProcedures(data.map(p => ({
        id: p.procedure_id,
        name: p.name,
        stage: p.stage,
        station_id: p.station_id,
        wiDocId: p.work_instruction_doc_id ?? undefined,
      })));
    }).catch(() => {});
    api.listReferenceDocuments().then(data => {
      setApiAllDocs(data.map(d => ({
        id: d.document_id,
        fileName: d.file_name,
        title: d.title,
        category: d.category,
        pages: d.pages,
        version: d.version,
        vendor: d.vendor ?? undefined,
        pdf_path: d.pdf_path ?? undefined,
      })));
    }).catch(() => {});
  }, []);

  // Fetch source artifacts when a document is active
  useEffect(() => {
    if (!documentId) return;
    api.listSources(documentId).then(setApiSources).catch(() => {});
  }, [documentId]);

  const handleGenerate = useCallback(async () => {
    if (generatingRef.current) return; // ignore re-entrant clicks
    generatingRef.current = true;
    setGenerateKey(k => k + 1);
    setIsGenerating(true);
    setShowPipeline(true);
    try {
      let docId = documentId;
      if (!docId) {
        const proc = apiProcedures.find(p => p.id === selectedProcedure);
        const doc = await api.createDocument({
          title: `${proc?.name ?? selectedProcedure} — ${new Date().toLocaleString()}`,
          procedure_id: selectedProcedure,
          station_id: proc?.station_id,
          target_language: language,
        });
        setDocumentId(doc.document_id);
        setApiDocument(doc);
        docId = doc.document_id;
      }

      setGenStatus(null);

      // Fire generate without awaiting — the endpoint blocks until all LLM steps finish.
      // We poll concurrently so the pipeline tracker can animate through each agent.
      const generatePromise = api.generate(docId, {
        target_language: language,
        machine_state_snapshot: stationStateRef.current as Record<string, unknown> | null ?? null,
      });

      await new Promise<void>((resolve) => {
        if (pollRef.current) clearInterval(pollRef.current);
        let generateDone = false;
        generatePromise
          .then(() => { generateDone = true; })
          .catch(() => { generateDone = true; });
        pollRef.current = window.setInterval(async () => {
          try {
            const status = await api.getStatus(docId!);
            setGenStatus(status);

            const done = generateDone && (status.status === 'failed' || status.progress_percent >= 100);
            if (done) {
              clearInterval(pollRef.current!);
              pollRef.current = null;
              resolve();
            }
          } catch {
            if (generateDone) {
              clearInterval(pollRef.current!);
              pollRef.current = null;
              resolve();
            }
          }
        }, 500);
      });

      const [newSteps, newSources] = await Promise.all([
        api.listSteps(docId),
        api.listSources(docId),
      ]);
      if (newSteps.length > 0) {
        setApiSteps(newSteps);
        setSelectedStepId(newSteps[0].step_id);
      }
      setApiSources(newSources);
    } catch (err) {
      console.error('Generation failed:', err);
    } finally {
      generatingRef.current = false;
      setIsGenerating(false);
      setShowPipeline(false);
      // Refetch history now that the new document exists (generateKey was
      // bumped at the start to remount StepViewer, too early for the refetch).
      setHistoryKey(k => k + 1);
    }
  }, [documentId, selectedProcedure, language, apiProcedures]);

  // Cleanup polls on unmount
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (refineIllPollRef.current) clearInterval(refineIllPollRef.current);
  }, []);

  // Review & Feedback — called by StepViewer Refine button.
  // Waits for BOTH text regeneration AND illustration regeneration before resolving,
  // so the Refined badge + new image appear together.
  const handleRefineStep = useCallback(async (stepId: string, instruction: string) => {
    if (!documentId) return;
    setRefiningStepId(stepId);
    try {
      await api.postChat(documentId, { content: instruction, step_id: stepId, mark_as_tribal_knowledge: false });
      const updated = await api.regenerateStep(documentId, stepId, { step_description: instruction });
      setApiSteps(prev => prev ? prev.map(s => s.step_id === stepId ? updated : s) : [updated]);

      // If the step had an illustration, the backend launched a BG task to regenerate it (~55s Flux).
      // Poll until the illustration URL changes, then update the step and let the badge fire.
      if (updated.illustration_url) {
        const oldUrl = updated.illustration_url;
        const MAX_POLLS = 80; // 80 × 3s = 4 min ceiling
        let pollCount = 0;
        await new Promise<void>((resolve) => {
          refineIllPollRef.current = window.setInterval(async () => {
            pollCount++;
            try {
              const freshSteps = await api.listSteps(documentId);
              const refreshed = freshSteps.find(s => s.step_id === stepId);
              const newUrlArrived = refreshed && refreshed.illustration_url !== oldUrl;
              if (newUrlArrived || pollCount >= MAX_POLLS) {
                clearInterval(refineIllPollRef.current!);
                refineIllPollRef.current = null;
                if (refreshed) setApiSteps(prev => prev ? prev.map(s => s.step_id === stepId ? refreshed : s) : [refreshed]);
                resolve();
              }
            } catch {
              if (pollCount >= MAX_POLLS) {
                clearInterval(refineIllPollRef.current!);
                refineIllPollRef.current = null;
                resolve();
              }
            }
          }, 3000);
        });
      }
    } catch (err) {
      console.error('Refine step failed:', err);
      const msg = err instanceof Error ? err.message : String(err);
      setRefineError(msg.includes('404') ? 'Document not found — re-generate first.' : `Refine failed: ${msg}`);
      setTimeout(() => setRefineError(null), 6000);
      throw err; // propagate so StepViewer skips the Refined badge
    } finally {
      setRefiningStepId(null);
    }
  }, [documentId]);

  const handleExport = useCallback(async () => {
    if (!documentId) {
      // No real document yet — fall back to triggering generate first is UX decision;
      // for now just no-op since ExportBar is in preview modal which implies doc exists
      return;
    }
    try {
      const result = await api.exportDocument(documentId, { format: format as 'pdf' | 'html' | 'json' });
      if (result.download_url) {
        window.open(result.download_url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      console.error('Export failed:', err);
    }
  }, [documentId, format]);

  const historyReports = apiHistoryItems ?? [];

  const refDocs = useMemo<RefDoc[]>(() => {
    if (!apiSources) return [];
    return apiSources.map(s => {
      const collection = (s.extracted_metadata?.collection as string | undefined) ?? '';
      return {
        id: s.source_id,
        name: s.file_name,
        category: (COLLECTION_CATEGORY[collection] ?? 'sop') as RefDoc['category'],
        fileName: s.file_name,
        pages: (s.extracted_metadata?.page_number as number | undefined) ?? 0,
        version: s.vendor_name ?? '',
        description: (s.extracted_metadata?.document_type as string | undefined) ?? '',
        pdfUrl: s.artifact_ref || undefined,
      };
    });
  }, [apiSources]);

  const handleHistoryPreview = useCallback(async (report: HistoryReport) => {
    setHistoryOpen(false);
    setHistoryPreview(report);
    setHistorySteps([]);
    try {
      const fetched = await api.listSteps(report.id);
      setHistorySteps(fetched);
    } catch {
      // leave empty — preview still shows document header
    }
  }, []);

  const handleDocPreview = useCallback((doc: AvailableDoc) => {
    setDocsOpen(false);
    setDocPreview(doc);
  }, []);

  const handleRefDocPopupPreview = useCallback((doc: RefDoc) => {
    setRefDocsOpen(false);
    setRefDocPreview(doc);
  }, []);

  const historyDocument = useMemo(() => {
    if (!historyPreview) return null;
    return {
      title: historyPreview.title,
      asset_id: null,
      procedure_id: historyPreview.procedure,
      status: historyPreview.status,
    };
  }, [historyPreview]);

  const selectedStep = useMemo(
    () => steps.find(s => s.step_id === selectedStepId) ?? null,
    [steps, selectedStepId],
  );

  // Show illustration column when the selected step has a generated image
  const selectedIllustration = useMemo(() => {
    if (!selectedStep?.illustration_url) return null;
    return {
      illustration_id: selectedStep.step_id,
      step_id: selectedStep.step_id,
      style: 'technical_diagram',
      image_url: selectedStep.illustration_url,
      width: 768,
      height: 512,
    };
  }, [selectedStep]);

  // Memoized so it doesn't produce a new array every render (which would defeat
  // MachineFloor's memoization).
  const procDocs = useMemo(() => {
    const proc = apiProcedures.find(p => p.id === selectedProcedure);
    const wiDoc = proc?.wiDocId ? apiAllDocs.find(d => d.id === proc.wiDocId) : undefined;
    return wiDoc ? [{ id: wiDoc.id, name: wiDoc.title, pdfUrl: wiDoc.pdf_path }] : [];
  }, [apiProcedures, selectedProcedure, apiAllDocs]);

  return (
    <div className="app">
      <TopBar onHistoryClick={() => setHistoryOpen(true)} onDocumentsClick={() => setDocsOpen(true)} />

      <div className="app__body">
        <div className="app__left-of-metrics">
          <MachineFloor
            isLoading={liveMachines === null}
            machines={machines}
            procedures={apiProcedures}
            selectedProcedure={selectedProcedure}
            onProcedureChange={setSelectedProcedure}
            onGenerateNextStep={handleGenerate}
            isGenerating={isGenerating}
            procDocs={procDocs}
          />
          <div className="app__main">
            <div className="app__center">
              {steps.length === 0 || showPipeline ? (
                <PipelineTracker
                  hasDocument={documentId !== null}
                  isGenerating={isGenerating}
                  generationStatus={genStatus}
                />
              ) : (
                <>
                  <div className="app__workspace-header">
                    <span className="app__workspace-title">
                      INSTRUCTION STEPS
                    </span>
                    <div className="app__workspace-actions">
                      <div className="app__refdocs-wrap">
                        <button className="app__report-btn" onClick={() => setRefDocsOpen(o => !o)}>
                          <FileStack size={13} />
                          Ref Docs
                          <span className="app__report-btn-count">{refDocs.length}</span>
                        </button>
                        {refDocsOpen && (
                          <>
                            <div className="rdp-backdrop" onClick={() => setRefDocsOpen(false)} />
                            <div className="rdp">
                              <div className="rdp__header">
                                <span className="rdp__title">Reference Documents</span>
                                <span className="rdp__count">{refDocs.length}</span>
                              </div>
                              <div className="rdp__list">
                                {refDocs.map(doc => {
                                  const CatIcon = CAT_ICON[doc.category];
                                  return (
                                    <div key={doc.id} className="rdp-item" onClick={() => handleRefDocPopupPreview(doc)}>
                                      <div className="rdp-item__left">
                                        <FileText size={12} className="rdp-item__file-icon" />
                                        <div className="rdp-item__info">
                                          <span className="rdp-item__name">{doc.name}</span>
                                          <span className="rdp-item__meta">
                                            <span className={`rdp-item__cat rdp-item__cat--${doc.category}`}>
                                              <CatIcon size={8} />
                                              {doc.category.toUpperCase()}
                                            </span>
                                            <span className="rdp-item__dot" />
                                            {doc.pages} pages
                                            <span className="rdp-item__dot" />
                                            {doc.version}
                                          </span>
                                        </div>
                                      </div>
                                      <FileText size={13} className="rdp-item__icon" />
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                      <button className="app__report-btn" onClick={() => setPreviewOpen(true)}>
                        <FileText size={13} />
                        Report
                      </button>
                    </div>
                  </div>

                  <div className="app__workspace">
                    <div className={`app__steps-col${!selectedIllustration ? ' app__steps-col--full' : ''}`}>
                      {refineError && (
                        <div className="refine-error-banner">
                          <AlertTriangle size={13} className="refine-error-banner__icon" />
                          <span className="refine-error-banner__msg">{refineError}</span>
                          <button className="refine-error-banner__close" onClick={() => setRefineError(null)} aria-label="Dismiss">
                            <X size={12} />
                          </button>
                        </div>
                      )}
                      <StepViewer
                        key={generateKey}
                        steps={steps}
                        hasDocument={documentId !== null}
                        isGenerating={isGenerating}
                        selectedStepId={selectedStepId}
                        onSelectStep={setSelectedStepId}
                        onEditStep={() => {}}
                        onRegenerateStep={async (stepId) => {
                          if (!documentId) return;
                          try {
                            const updated = await api.regenerateStep(documentId, stepId);
                            setApiSteps(prev => prev
                              ? prev.map(s => s.step_id === stepId ? updated : s)
                              : [updated]);
                          } catch (err) { console.error('Regenerate failed:', err); }
                        }}
                        onRefineStep={handleRefineStep}
                        onStepRefined={(id) => setRefinedStepIds(prev => new Set(prev).add(id))}
                      />
                    </div>
                    {selectedIllustration && (
                      <div className="app__illus-col">
                        <StepIllustration
                          step={selectedStep}
                          illustration={selectedIllustration}
                          isRefining={refiningStepId === selectedStep?.step_id}
                        />
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        <MetricsPanel
          open={metricsOpen}
          onToggle={() => setMetricsOpen(o => !o)}
          isGenerating={isGenerating}
        />
      </div>

      <PreviewModal open={previewOpen} onClose={() => setPreviewOpen(false)}>
        <PreviewPane
          document={activeDocument}
          steps={steps}
          selectedStepId={selectedStepId}
          refinedStepIds={refinedStepIds}
        />
        <ExportBar
          format={format}
          language={language}
          onFormatChange={setFormat}
          onLanguageChange={(v) => setLanguage(v)}
          onExport={handleExport}
          onPublish={() => {}}
          documentStatus={activeDocument?.status ?? 'draft'}
        />
      </PreviewModal>

      <HistoryDrawer
        open={historyOpen}
        loading={apiHistoryItems === null}
        reports={historyReports}
        onClose={() => setHistoryOpen(false)}
        onPreview={handleHistoryPreview}
      />

      <PreviewModal
        open={historyPreview !== null}
        onClose={() => setHistoryPreview(null)}
        title={`HISTORY — ${historyPreview?.title ?? ''}`}
      >
        <PreviewPane
          document={historyDocument}
          steps={historySteps}
          selectedStepId={null}
        />
      </PreviewModal>

      {refDocPreview && <RefDocModal doc={refDocPreview} onClose={() => setRefDocPreview(null)} />}

      <DocumentsPopup
        open={docsOpen}
        loading={false}
        documents={apiAllDocs.filter(d => d.category === 'sop')}
        onClose={() => setDocsOpen(false)}
        onPreview={handleDocPreview}
      />

      {docPreview && (
        <div className="mf-modal-backdrop" onClick={() => setDocPreview(null)}>
          <div className="mf-modal" onClick={e => e.stopPropagation()}>
            <div className="mf-modal__header">
              <div className="mf-modal__title-row">
                <FileText size={14} />
                <span className="mf-modal__title">{docPreview.title}</span>
              </div>
              <button className="mf-modal__close" onClick={() => setDocPreview(null)} aria-label="Close"><X size={14} /></button>
            </div>
            <div className="mf-modal__body">
              {docPreview.pdf_path ? (
                <iframe
                  src={docPreview.pdf_path}
                  className="mf-modal__pdf-embed"
                  title={docPreview.fileName}
                />
              ) : (
                <div className="mf-modal__pdf-preview">
                  <FileText size={48} strokeWidth={1} />
                  <span className="mf-modal__placeholder-text">PDF not available</span>
                </div>
              )}
            </div>
            <div className="mf-modal__footer">
              <span className="mf-modal__lang-tag">{docPreview.category.toUpperCase()}</span>
              <span className="mf-modal__file-type">PDF</span>
              {docPreview.vendor && <span className="mf-modal__file-type">{docPreview.vendor}</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
