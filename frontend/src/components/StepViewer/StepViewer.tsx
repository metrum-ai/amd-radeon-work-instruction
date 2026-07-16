// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { type MouseEvent, useState, useCallback, useRef, useEffect } from 'react';
import {
  Wrench,
  Package,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  BookOpen,
  Sparkles,
  Send,
  X,
} from 'lucide-react';
import './StepViewer.css';

interface TooltipData {
  label: string;
  items: string[];
  x: number;
  y: number;
}

interface StepViewerProps {
  hasDocument?: boolean;
  isGenerating?: boolean;
  steps: Array<{
    step_id: string;
    step_number: number;
    title: string;
    instruction_text: string;
    interlock_status: 'pass' | 'blocked';
    tools_required: string[];
    parts_required: string[];
    safety_warnings: string[];
    quality_checks: string[];
    source_citations: string[];
    tribal_knowledge_refs: string[];
    difficulty: 'easy' | 'medium' | 'hard';
    estimated_time_minutes: number;
  }>;
  selectedStepId: string | null;
  onSelectStep: (stepId: string) => void;
  onEditStep: (stepId: string) => void;
  onRegenerateStep: (stepId: string) => void;
  onRefineStep?: (stepId: string, instruction: string) => Promise<void>;
  onStepRefined?: (stepId: string) => void;
}

const DIFFICULTY_MAP = {
  easy: { label: 'Easy', className: 'step-difficulty--safe' },
  medium: { label: 'Medium', className: 'step-difficulty--medium' },
  hard: { label: 'Hard', className: 'step-difficulty--critical' },
} as const;

const INTERLOCK_CONFIG = {
  pass: { icon: ShieldCheck, label: 'Pass', className: 'step-interlock--pass' },
  blocked: { icon: ShieldAlert, label: 'Blocked', className: 'step-interlock--blocked' },
} as const;


function StepViewer({
  hasDocument = false,
  isGenerating = false,
  steps,
  selectedStepId,
  onSelectStep,
  onRefineStep,
  onStepRefined,
}: StepViewerProps) {
  const [refineOpenId, setRefineOpenId] = useState<string | null>(null);
  const [refineInput, setRefineInput] = useState('');
  const [refiningId, setRefiningId] = useState<string | null>(null);
  const [refinedStepIds, setRefinedStepIds] = useState<Set<string>>(new Set());
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const tooltipTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showTooltip = useCallback((e: React.MouseEvent, label: string, items: string[]) => {
    if (tooltipTimeout.current) clearTimeout(tooltipTimeout.current);
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTooltip({ label, items, x: rect.left + rect.width / 2, y: rect.top });
  }, []);

  const hideTooltip = useCallback(() => {
    tooltipTimeout.current = setTimeout(() => setTooltip(null), 100);
  }, []);

  useEffect(() => {
    if (refineOpenId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [refineOpenId]);

  const openRefine = useCallback((e: MouseEvent, stepId: string) => {
    e.stopPropagation();
    setRefineOpenId(prev => prev === stepId ? null : stepId);
    setRefineInput('');
  }, []);

  const closeRefine = useCallback((e: MouseEvent) => {
    e.stopPropagation();
    setRefineOpenId(null);
    setRefineInput('');
  }, []);

  const submitRefine = useCallback((e: MouseEvent, stepId: string) => {
    e.stopPropagation();
    const instruction = refineInput.trim();
    if (!instruction) return;
    setRefineOpenId(null);
    setRefineInput('');
    setRefiningId(stepId);
    onRefineStep?.(stepId, instruction)
      .then(() => {
        setRefinedStepIds(prev => new Set(prev).add(stepId));
        onStepRefined?.(stepId);
      })
      .catch(() => {}) // error already surfaced in App.tsx; just suppress badge
      .finally(() => setRefiningId(null));
  }, [refineInput, onRefineStep]);

  if (steps.length === 0 && !isGenerating) {
    return (
      <div className="step-viewer">
        <div className="step-viewer-empty">
          {hasDocument
            ? <span className="step-viewer-empty__text">No steps generated yet.</span>
            : <>
                <span className="step-viewer-empty__text">No work instructions loaded.</span>
                <span className="step-viewer-empty__hint">Select a procedure and press Generate.</span>
              </>
          }
        </div>
      </div>
    );
  }

  return (
    <div className="step-viewer">
      <div className="step-viewer-body">
        {steps.map((step) => {
          const isSelected = step.step_id === selectedStepId;
          const isRefining = refiningId === step.step_id;
          const isRefined = refinedStepIds.has(step.step_id);
          const displayText = step.instruction_text;
          const isRefineOpen = refineOpenId === step.step_id;
          const diff = DIFFICULTY_MAP[step.difficulty];
          const interlock = INTERLOCK_CONFIG[step.interlock_status];
          const InterlockIcon = interlock.icon;

          const isPrereq = step.interlock_status === 'blocked';

          return (
            <div
              key={step.step_id}
              className={`step-card${isSelected ? ' step-card--selected' : ''}${isRefined ? ' step-card--refined' : ''}${isPrereq ? ' step-card--prereq' : ''}${isRefining ? ' step-card--refining' : ''}`}
              onClick={() => onSelectStep(step.step_id)}
            >
              <div
                className={`step-card-number${isSelected ? ' step-card-number--active' : ''}`}
              >
                {step.step_number}
              </div>

              <div className="step-card-content">
                {isRefining && (
                  <div className="step-card-refining-overlay">
                    <span className="step-card-refining-spinner" />
                    <span className="step-card-refining-label">Updating instruction…</span>
                  </div>
                )}
                <div className="step-card-top">
                  <span className="step-card-title">{step.title}</span>
                  <div className="step-card-top-right">
                    {isRefined && (
                      <span className="step-card-refined-tag">
                        <Sparkles size={9} />
                        Refined
                      </span>
                    )}
                    <span className={`step-card-difficulty ${diff.className}`}>
                      {diff.label}
                    </span>
                    <span className="step-card-time">
                      {step.estimated_time_minutes}m
                    </span>
                  </div>
                </div>

                <p className={`step-card-text${isRefining ? ' step-card-text--refining' : ''}`}>{displayText}</p>

                {step.safety_warnings.length > 0 && (
                  <div className="step-card-warnings">
                    {step.safety_warnings.map((warning, i) => (
                      <span
                        key={i}
                        className="step-card-warning-badge"
                        title={warning}
                      >
                        <AlertTriangle size={10} />
                        <span className="step-card-warning-text">{warning}</span>
                      </span>
                    ))}
                  </div>
                )}

                <div className="step-card-footer">
                  <div className="step-card-badges">
                    {step.tools_required.length > 0 && (
                      <span
                        className="step-card-badge"
                        onMouseEnter={(e) => showTooltip(e, 'Tools Required', step.tools_required)}
                        onMouseLeave={hideTooltip}
                      >
                        <Wrench size={10} />
                        {step.tools_required.length}
                      </span>
                    )}
                    {step.parts_required.length > 0 && (
                      <span
                        className="step-card-badge"
                        onMouseEnter={(e) => showTooltip(e, 'Parts Required', step.parts_required)}
                        onMouseLeave={hideTooltip}
                      >
                        <Package size={10} />
                        {step.parts_required.length}
                      </span>
                    )}
                    <span
                      className={`step-card-badge ${interlock.className}`}
                      onMouseEnter={(e) => showTooltip(e, 'Interlock Status', [interlock.label])}
                      onMouseLeave={hideTooltip}
                    >
                      <InterlockIcon size={10} />
                      {interlock.label}
                    </span>
                    {step.source_citations.length > 0 && (
                      <span
                        className="step-card-badge step-card-badge--teal"
                        onMouseEnter={(e) => showTooltip(e, 'Source Citations', step.source_citations)}
                        onMouseLeave={hideTooltip}
                      >
                        <BookOpen size={10} />
                        {step.source_citations.length}
                      </span>
                    )}
                  </div>
                  {!isPrereq && (
                    <button
                      className="step-card-refine-btn"
                      onClick={(e) => openRefine(e, step.step_id)}
                      disabled={isRefining}
                    >
                      <Sparkles size={11} />
                      Refine
                    </button>
                  )}
                </div>

                {!isPrereq && isRefineOpen && (
                  <div className="step-refine-box" onClick={e => e.stopPropagation()}>
                    <textarea
                      ref={inputRef}
                      className="step-refine-input"
                      placeholder="Describe how to refine this instruction..."
                      value={refineInput}
                      onChange={e => setRefineInput(e.target.value)}
                      rows={2}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          submitRefine(e as unknown as MouseEvent, step.step_id);
                        }
                      }}
                    />
                    <div className="step-refine-actions">
                      <button className="step-refine-cancel" onClick={closeRefine}>
                        <X size={11} />
                      </button>
                      <button
                        className="step-refine-submit"
                        onClick={(e) => submitRefine(e, step.step_id)}
                        disabled={!refineInput.trim()}
                      >
                        <Send size={11} />
                        Refine Instruction
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {tooltip && (
        <div
          className="sv-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <span className="sv-tooltip__label">{tooltip.label}</span>
          <ul className="sv-tooltip__list">
            {tooltip.items.map((item, i) => (
              <li key={i} className="sv-tooltip__item">{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default StepViewer;
