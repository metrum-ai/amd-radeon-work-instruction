// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useEffect } from 'react';
import { FileText, Image, Eye, X, ListChecks } from 'lucide-react';
import type { FloorMachine, FloorMachineStatus, MachineDoc } from '../../types';
import './MachineFloor.css';

interface ProcDoc {
  id: string;
  name: string;
  pdfUrl?: string;
}

interface MachineFloorProps {
  machines: FloorMachine[];
  isLoading?: boolean;
  procedures: Array<{ id: string; name: string }>;
  selectedProcedure: string;
  onProcedureChange: (id: string) => void;
  onGenerateNextStep: () => void;
  isGenerating?: boolean;
  procDocs?: ProcDoc[];
}

// ISA-88 PackML state colours
const STATUS_COLOR: Record<FloorMachineStatus, string> = {
  Execute:    'var(--amd-orange)',    // production running
  Starting:   'var(--amd-teal)',     // ramping up
  Completing: 'var(--amd-teal)',     // finishing cycle
  Complete:   'var(--sev-safe)',     // cycle done
  Idle:       'var(--sev-safe)',     // waiting / ready
  Held:       'var(--text-dim)',     // production hold
  Aborted:    'var(--sev-critical)', // fault — requires Reset
};

const ARC_FULL = 207;

function WelderSvg() {
  return (
    <svg viewBox="0 0 80 80" className="mf-machine-svg">
      <defs>
        <linearGradient id="welder-arm" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="rgba(242,101,34,0.6)" />
          <stop offset="100%" stopColor="rgba(237,28,36,0.4)" />
        </linearGradient>
        <filter id="welder-glow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Base platform */}
      <ellipse cx="40" cy="72" rx="18" ry="4" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" strokeWidth="0.8" />
      <rect x="32" y="64" width="16" height="8" rx="2" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.2)" strokeWidth="1" />
      {/* Pivot base turret */}
      <rect x="35" y="58" width="10" height="8" rx="1.5" fill="rgba(242,101,34,0.15)" stroke="rgba(242,101,34,0.5)" strokeWidth="1" />
      <circle cx="40" cy="58" r="2" fill="rgba(242,101,34,0.6)" />
      {/* Lower arm segment */}
      <path d="M40,56 L40,42" stroke="url(#welder-arm)" strokeWidth="3.5" strokeLinecap="round" />
      <rect x="37" y="42" width="6" height="4" rx="1" fill="rgba(255,255,255,0.08)" stroke="rgba(242,101,34,0.4)" strokeWidth="0.8" />
      {/* Shoulder servo housing */}
      <circle cx="40" cy="42" r="4" fill="rgba(242,101,34,0.1)" stroke="rgba(242,101,34,0.6)" strokeWidth="1.2" />
      <circle cx="40" cy="42" r="1.8" fill="rgba(242,101,34,0.7)" />
      {/* Upper arm segment */}
      <path d="M40,38 Q50,30 56,26" stroke="url(#welder-arm)" strokeWidth="3" strokeLinecap="round" fill="none" />
      {/* Elbow joint */}
      <circle cx="56" cy="26" r="3.5" fill="rgba(242,101,34,0.1)" stroke="rgba(242,101,34,0.55)" strokeWidth="1" />
      <circle cx="56" cy="26" r="1.5" fill="rgba(242,101,34,0.7)" />
      {/* Forearm with wrist */}
      <path d="M56,26 Q54,20 50,14" stroke="url(#welder-arm)" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      {/* Wrist rotator */}
      <circle cx="50" cy="14" r="2.5" fill="rgba(242,101,34,0.1)" stroke="rgba(242,101,34,0.5)" strokeWidth="0.8" />
      {/* End effector / welding torch */}
      <path d="M50,14 L58,10 L62,10" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5" strokeLinecap="round" fill="none" />
      <polygon points="62,7.5 68,10 62,12.5" fill="rgba(242,101,34,0.7)" stroke="rgba(242,101,34,0.9)" strokeWidth="0.5" />
      {/* Welding arc effect */}
      <circle cx="68" cy="10" r="2.5" fill="rgba(242,101,34,0.6)" filter="url(#welder-glow)">
        <animate attributeName="r" values="2;4;2" dur="0.4s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.9;0.3;0.9" dur="0.4s" repeatCount="indefinite" />
      </circle>
      {/* Spark particles */}
      <circle cx="70" cy="8" r="0.6" fill="#fbbf24">
        <animate attributeName="cx" values="68;74;68" dur="0.6s" repeatCount="indefinite" />
        <animate attributeName="cy" values="10;6;10" dur="0.6s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1" dur="0.6s" repeatCount="indefinite" />
      </circle>
      <circle cx="72" cy="12" r="0.5" fill="#fbbf24">
        <animate attributeName="cx" values="68;73;68" dur="0.7s" begin="0.2s" repeatCount="indefinite" />
        <animate attributeName="cy" values="10;14;10" dur="0.7s" begin="0.2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.8;0;0.8" dur="0.7s" begin="0.2s" repeatCount="indefinite" />
      </circle>
      <circle cx="69" cy="7" r="0.4" fill="#fff">
        <animate attributeName="cx" values="68;71;68" dur="0.5s" begin="0.3s" repeatCount="indefinite" />
        <animate attributeName="cy" values="10;5;10" dur="0.5s" begin="0.3s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1" dur="0.5s" begin="0.3s" repeatCount="indefinite" />
      </circle>
      {/* Cable harness along arm */}
      <path d="M38,60 Q34,50 36,42 Q38,36 42,30 Q48,24 54,22" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" strokeDasharray="2 2" />
      {/* Status LED on base */}
      <circle cx="44" cy="67" r="1" fill="rgba(52,211,153,0.9)">
        <animate attributeName="opacity" values="1;0.4;1" dur="1.5s" repeatCount="indefinite" />
      </circle>
    </svg>
  );
}

function DispenserSvg() {
  return (
    <svg viewBox="0 0 80 80" className="mf-machine-svg">
      <defs>
        <linearGradient id="disp-frame" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(52,211,153,0.5)" />
          <stop offset="100%" stopColor="rgba(52,211,153,0.15)" />
        </linearGradient>
        <linearGradient id="disp-fluid" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(52,211,153,0.8)" />
          <stop offset="100%" stopColor="rgba(52,211,153,0.2)" />
        </linearGradient>
      </defs>
      {/* Work surface */}
      <rect x="10" y="68" width="60" height="3" rx="1" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.12)" strokeWidth="0.6" />
      {/* Gantry left pillar */}
      <rect x="12" y="18" width="4" height="50" rx="1" fill="rgba(255,255,255,0.06)" stroke="url(#disp-frame)" strokeWidth="1" />
      {/* Gantry right pillar */}
      <rect x="64" y="18" width="4" height="50" rx="1" fill="rgba(255,255,255,0.06)" stroke="url(#disp-frame)" strokeWidth="1" />
      {/* Cross beam */}
      <rect x="12" y="16" width="56" height="5" rx="1.5" fill="rgba(52,211,153,0.08)" stroke="rgba(52,211,153,0.45)" strokeWidth="1.2" />
      {/* Beam rail groove */}
      <line x1="16" y1="18.5" x2="64" y2="18.5" stroke="rgba(52,211,153,0.2)" strokeWidth="0.5" />
      {/* Carriage block */}
      <rect x="33" y="13" width="14" height="10" rx="2" fill="rgba(52,211,153,0.12)" stroke="rgba(52,211,153,0.6)" strokeWidth="1">
        <animate attributeName="x" values="33;36;33" dur="4s" repeatCount="indefinite" />
      </rect>
      {/* Pump/reservoir on carriage */}
      <rect x="36" y="14" width="8" height="4" rx="1" fill="rgba(52,211,153,0.2)" stroke="rgba(52,211,153,0.4)" strokeWidth="0.5">
        <animate attributeName="x" values="36;39;36" dur="4s" repeatCount="indefinite" />
      </rect>
      {/* Dispenser tube */}
      <line x1="40" y1="23" x2="40" y2="38" stroke="rgba(52,211,153,0.5)" strokeWidth="2" strokeLinecap="round">
        <animate attributeName="x1" values="40;43;40" dur="4s" repeatCount="indefinite" />
        <animate attributeName="x2" values="40;43;40" dur="4s" repeatCount="indefinite" />
      </line>
      {/* Nozzle tip */}
      <polygon points="37,38 43,38 40,46" fill="rgba(52,211,153,0.3)" stroke="rgba(52,211,153,0.7)" strokeWidth="0.8">
        <animate attributeName="points" values="37,38 43,38 40,46;40,38 46,38 43,46;37,38 43,38 40,46" dur="4s" repeatCount="indefinite" />
      </polygon>
      {/* Pressure gauge on tube */}
      <circle cx="42" cy="30" r="2.5" fill="none" stroke="rgba(52,211,153,0.3)" strokeWidth="0.5">
        <animate attributeName="cx" values="42;45;42" dur="4s" repeatCount="indefinite" />
      </circle>
      <line x1="42" y1="30" x2="43" y2="28.5" stroke="rgba(52,211,153,0.6)" strokeWidth="0.5">
        <animate attributeName="x1" values="42;45;42" dur="4s" repeatCount="indefinite" />
        <animate attributeName="x2" values="43;46;43" dur="4s" repeatCount="indefinite" />
      </line>
      {/* Adhesive drip animation */}
      <ellipse cx="40" cy="50" rx="1.2" ry="2" fill="url(#disp-fluid)">
        <animate attributeName="cy" values="46;62" dur="1s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.9;0" dur="1s" repeatCount="indefinite" />
        <animate attributeName="cx" values="40;43;40" dur="4s" repeatCount="indefinite" />
      </ellipse>
      <ellipse cx="40" cy="50" rx="1" ry="1.5" fill="url(#disp-fluid)">
        <animate attributeName="cy" values="46;62" dur="1s" begin="0.4s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.7;0" dur="1s" begin="0.4s" repeatCount="indefinite" />
        <animate attributeName="cx" values="40;43;40" dur="4s" repeatCount="indefinite" />
      </ellipse>
      {/* Adhesive bead on surface */}
      <path d="M18,65 Q28,61 38,65 Q48,69 58,65" fill="none" stroke="rgba(52,211,153,0.4)" strokeWidth="2" strokeLinecap="round">
        <animate attributeName="stroke-dasharray" values="0 100;60 100" dur="3s" repeatCount="indefinite" />
      </path>
      {/* Substrate piece on surface */}
      <rect x="22" y="63" width="36" height="5" rx="1" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
      {/* Status LEDs on pillar */}
      <circle cx="14" cy="62" r="1" fill="rgba(52,211,153,0.9)">
        <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
      </circle>
      <circle cx="14" cy="56" r="1" fill="rgba(251,191,36,0.6)" />
    </svg>
  );
}

function InspectorSvg() {
  return (
    <svg viewBox="0 0 80 80" className="mf-machine-svg">
      <defs>
        <linearGradient id="insp-beam" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(96,165,250,0.7)" />
          <stop offset="100%" stopColor="rgba(96,165,250,0.05)" />
        </linearGradient>
        <filter id="insp-glow">
          <feGaussianBlur stdDeviation="1" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Mounting bracket */}
      <rect x="35" y="6" width="10" height="4" rx="1" fill="rgba(255,255,255,0.06)" stroke="rgba(96,165,250,0.3)" strokeWidth="0.8" />
      <line x1="40" y1="10" x2="40" y2="16" stroke="rgba(96,165,250,0.4)" strokeWidth="2" strokeLinecap="round" />
      {/* Camera body */}
      <rect x="24" y="16" width="32" height="22" rx="4" fill="rgba(96,165,250,0.06)" stroke="rgba(96,165,250,0.4)" strokeWidth="1.2" />
      {/* Ventilation slots */}
      <line x1="28" y1="19" x2="34" y2="19" stroke="rgba(255,255,255,0.08)" strokeWidth="0.4" />
      <line x1="28" y1="21" x2="34" y2="21" stroke="rgba(255,255,255,0.08)" strokeWidth="0.4" />
      <line x1="28" y1="23" x2="34" y2="23" stroke="rgba(255,255,255,0.08)" strokeWidth="0.4" />
      {/* Lens barrel outer ring */}
      <circle cx="40" cy="27" r="9" fill="none" stroke="rgba(96,165,250,0.35)" strokeWidth="1.5" />
      {/* Lens barrel inner */}
      <circle cx="40" cy="27" r="6.5" fill="rgba(96,165,250,0.04)" stroke="rgba(96,165,250,0.5)" strokeWidth="1" />
      {/* Lens glass */}
      <circle cx="40" cy="27" r="4" fill="rgba(96,165,250,0.15)" stroke="rgba(96,165,250,0.7)" strokeWidth="0.8" />
      {/* Lens reflection */}
      <ellipse cx="38" cy="25" rx="1.5" ry="1" fill="rgba(255,255,255,0.15)" />
      {/* Iris detail */}
      <circle cx="40" cy="27" r="2" fill="rgba(96,165,250,0.3)" />
      <circle cx="40" cy="27" r="0.8" fill="rgba(96,165,250,0.8)" />
      {/* Lens glow pulse */}
      <circle cx="40" cy="27" r="9" fill="none" stroke="rgba(96,165,250,0.3)" strokeWidth="0.5" filter="url(#insp-glow)">
        <animate attributeName="r" values="9;12;9" dur="2.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2.5s" repeatCount="indefinite" />
      </circle>
      {/* Status indicator on body */}
      <circle cx="52" cy="20" r="1.2" fill="rgba(96,165,250,0.9)">
        <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite" />
      </circle>
      {/* Structured light projection cone */}
      <path d="M34,38 L20,68" stroke="url(#insp-beam)" strokeWidth="0.6" fill="none" opacity="0.5">
        <animate attributeName="opacity" values="0.5;0.15;0.5" dur="1.8s" repeatCount="indefinite" />
      </path>
      <path d="M37,38 L28,68" stroke="url(#insp-beam)" strokeWidth="0.6" fill="none" opacity="0.4">
        <animate attributeName="opacity" values="0.4;0.1;0.4" dur="1.8s" begin="0.15s" repeatCount="indefinite" />
      </path>
      <path d="M40,38 L40,68" stroke="url(#insp-beam)" strokeWidth="0.6" fill="none" opacity="0.5">
        <animate attributeName="opacity" values="0.5;0.15;0.5" dur="1.8s" begin="0.3s" repeatCount="indefinite" />
      </path>
      <path d="M43,38 L52,68" stroke="url(#insp-beam)" strokeWidth="0.6" fill="none" opacity="0.4">
        <animate attributeName="opacity" values="0.4;0.1;0.4" dur="1.8s" begin="0.45s" repeatCount="indefinite" />
      </path>
      <path d="M46,38 L60,68" stroke="url(#insp-beam)" strokeWidth="0.6" fill="none" opacity="0.5">
        <animate attributeName="opacity" values="0.5;0.15;0.5" dur="1.8s" begin="0.6s" repeatCount="indefinite" />
      </path>
      {/* Scan grid pattern on surface */}
      <rect x="22" y="62" width="36" height="8" rx="1" fill="none" stroke="rgba(96,165,250,0.15)" strokeWidth="0.5" />
      {/* Grid lines */}
      <line x1="22" y1="65" x2="58" y2="65" stroke="rgba(96,165,250,0.1)" strokeWidth="0.3" />
      <line x1="31" y1="62" x2="31" y2="70" stroke="rgba(96,165,250,0.1)" strokeWidth="0.3" />
      <line x1="40" y1="62" x2="40" y2="70" stroke="rgba(96,165,250,0.1)" strokeWidth="0.3" />
      <line x1="49" y1="62" x2="49" y2="70" stroke="rgba(96,165,250,0.1)" strokeWidth="0.3" />
      {/* Scanning line sweep */}
      <line x1="22" y1="64" x2="58" y2="64" stroke="rgba(96,165,250,0.8)" strokeWidth="1" strokeLinecap="round" filter="url(#insp-glow)">
        <animate attributeName="y1" values="62;70;62" dur="2s" repeatCount="indefinite" />
        <animate attributeName="y2" values="62;70;62" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.8;0.2;0.8" dur="2s" repeatCount="indefinite" />
      </line>
      {/* Target crosshair on inspection area */}
      <line x1="38" y1="66" x2="42" y2="66" stroke="rgba(96,165,250,0.5)" strokeWidth="0.4" />
      <line x1="40" y1="64" x2="40" y2="68" stroke="rgba(96,165,250,0.5)" strokeWidth="0.4" />
      {/* Data stream indicator */}
      <rect x="48" y="22" width="5" height="2" rx="0.5" fill="rgba(96,165,250,0.2)" stroke="rgba(96,165,250,0.4)" strokeWidth="0.3" />
      <rect x="48" y="25" width="5" height="2" rx="0.5" fill="rgba(96,165,250,0.15)" stroke="rgba(96,165,250,0.3)" strokeWidth="0.3" />
      <rect x="48" y="28" width="5" height="2" rx="0.5" fill="rgba(96,165,250,0.1)" stroke="rgba(96,165,250,0.3)" strokeWidth="0.3" />
      {/* Work surface */}
      <line x1="14" y1="72" x2="66" y2="72" stroke="rgba(255,255,255,0.12)" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

// Maps known OEM filenames (without language suffix) to their served PDF paths
const MANUAL_PDF_PATHS: Record<string, string> = {
  'ZYRO_Assembly_Guide_Rev_C.pdf':           '/manuals/ZYRO_Assembly_Guide_Rev_C.de.pdf',
  'ZYRO_Assembly_Guide_Rev_C.de.pdf':        '/manuals/ZYRO_Assembly_Guide_Rev_C.de.pdf',
  'Veltrix_Routing_Specification.pdf':       '/manuals/Veltrix_Routing_Specification.en.pdf',
  'Veltrix_Routing_Specification.en.pdf':    '/manuals/Veltrix_Routing_Specification.en.pdf',
  'Nexora_KS200_Inspection_Standard.pdf':    '/manuals/Nexora_KS200_Inspection_Standard.ja.pdf',
  'Nexora_KS200_Inspection_Standard.ja.pdf': '/manuals/Nexora_KS200_Inspection_Standard.ja.pdf',
};

const MACHINE_SVGS: Record<string, () => React.ReactNode> = {
  'zyro-welder':       WelderSvg,
  'veltrix-dispenser': DispenserSvg,
  'nexora-scanner':    InspectorSvg,
};

const FLAG_LABELS: Record<string, string> = {
  fixture_clamped: 'Fixture',
  laser_aligned: 'Laser',
  shield_gas_ok: 'Gas',
  purge_complete: 'Purge',
  head_homed: 'Homed',
  bead_sensor_cal: 'Bead Cal',
  calibrated: 'Cal',
  lens_clean: 'Lens',
  focus_locked: 'Focus',
};

function DocIcon({ type }: { type: string }) {
  if (type === 'image') return <Image size={11} />;
  return <FileText size={11} />;
}

function DocPreviewModal({ doc, onClose }: { doc: MachineDoc; onClose: () => void }) {
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
            <DocIcon type={doc.file_type} />
            <span className="mf-modal__title">{doc.display_name ?? doc.file_name}</span>
          </div>
          <button className="mf-modal__close" onClick={onClose} aria-label="Close"><X size={14} /></button>
        </div>

        <div className="mf-modal__body">
          {doc.pdf_path ? (
            <iframe
              src={doc.pdf_path}
              className="mf-modal__pdf-embed"
              title={doc.display_name ?? doc.file_name}
            />
          ) : doc.file_type === 'image' ? (
            <div className="mf-modal__image-preview">
              <Image size={48} strokeWidth={1} />
              <span className="mf-modal__placeholder-text">Image preview not available</span>
            </div>
          ) : (
            <div className="mf-modal__pdf-preview">
              <FileText size={48} strokeWidth={1} />
              <span className="mf-modal__placeholder-text">PDF not available</span>
              {doc.pages && <span className="mf-modal__meta">{doc.pages} pages</span>}
            </div>
          )}
        </div>

        <div className="mf-modal__footer">
          <span className="mf-modal__lang-tag">{doc.language}</span>
          <span className="mf-modal__file-type">{doc.file_type.toUpperCase()}</span>
        </div>
      </div>
    </div>
  );
}

function MachineCard({ machine, onPreviewDoc, onToggleFaultMode }: { machine: FloorMachine; onPreviewDoc: (doc: MachineDoc) => void; onToggleFaultMode: (id: string) => void }) {
  const SvgComp = MACHINE_SVGS[machine.id];
  const statusColor = STATUS_COLOR[machine.status];
  const flags = Object.entries(machine.readiness);
  const passCount = flags.filter(([, v]) => v).length;
  const healthPct = flags.length ? passCount / flags.length : 0;

  return (
    <div className={`mf-card mf-card--${machine.status.toLowerCase()}`}>
      {/* Fault mode toggle — top-left corner */}
      <button
        className={`mf-fault-toggle ${machine.fault_prone ? 'mf-fault-toggle--on' : ''}`}
        onClick={() => onToggleFaultMode(machine.id)}
        title={machine.fault_prone ? 'Fault mode ON — click to restore normal cycle' : 'Click to enable fault-prone cycle'}
      >
        <span className="mf-fault-toggle__dot" />
        {machine.fault_prone ? 'FAULT MODE' : 'NORMAL'}
      </button>

      {/* Status ring + machine SVG */}
      <div className="mf-card__visual">
        <div className="mf-card__ring-wrap">
          <svg viewBox="0 0 96 96" className="mf-card__ring-svg">
            <circle cx="48" cy="48" r="33" className="mf-card__ring-track" />
            <circle
              cx="48" cy="48" r="33"
              className="mf-card__ring-arc"
              style={{
                stroke: statusColor,
                strokeDasharray: `${healthPct * ARC_FULL} ${ARC_FULL}`,
              }}
            />
            {machine.status !== 'Held' && machine.status !== 'Aborted' && (
              <circle cx="48" cy="48" r="33" className="mf-card__ring-glow" style={{ stroke: statusColor }} />
            )}
          </svg>
          <div className="mf-card__svg-container">
            {SvgComp && <SvgComp />}
          </div>
        </div>
        <div className="mf-card__status-pip" style={{ background: statusColor }}>
          {(machine.status === 'Execute' || machine.status === 'Starting' || machine.status === 'Completing') && <span className="mf-card__pip-pulse" style={{ borderColor: statusColor }} />}
        </div>
      </div>

      {/* Vendor origin + machine name */}
      <div className="mf-card__identity">
        <span className="mf-card__origin">{machine.origin}</span>
        <span className="mf-card__name">{machine.vendor}</span>
      </div>

      {/* Gauges */}
      <div className="mf-card__gauges">
        {machine.gauges.map(g => {
          const pct = Math.min(g.value / g.max, 1);
          const arcLen = pct * 75;
          return (
            <div key={g.key} className="mf-gauge">
              <svg viewBox="0 0 44 28" className="mf-gauge__svg">
                <path d="M6,26 A16,16 0 0,1 38,26" className="mf-gauge__track" />
                <path
                  d="M6,26 A16,16 0 0,1 38,26"
                  className="mf-gauge__fill"
                  style={{ stroke: statusColor, strokeDasharray: `${arcLen} 100` }}
                />
              </svg>
              <span className="mf-gauge__val">{g.value}<span className="mf-gauge__unit">{g.unit}</span></span>
              <span className="mf-gauge__label">{g.label}</span>
            </div>
          );
        })}
      </div>

      {/* Readiness dots + inline OEM doc */}
      <div className="mf-card__bottom-row">
        <div className="mf-card__flags">
          {flags.map(([key, value]) => (
            <div key={key} className={`mf-flag ${value ? 'mf-flag--pass' : 'mf-flag--fail'}`}>
              <span className="mf-flag__dot" />
              <span className="mf-flag__label">{FLAG_LABELS[key] || key}</span>
            </div>
          ))}
        </div>
        {machine.docs[0] && (
          <button
            className="mf-doc-inline"
            onClick={() => {
              const doc = machine.docs[0];
              onPreviewDoc({ ...doc, pdf_path: doc.pdf_path ?? MANUAL_PDF_PATHS[doc.file_name] });
            }}
            title={machine.docs[0].display_name ?? machine.docs[0].file_name}
          >
            <FileText size={10} />
            <span className="mf-doc-inline__name">{machine.docs[0].display_name ?? machine.docs[0].file_name}</span>
            <span className="mf-doc-inline__lang">{machine.docs[0].language}</span>
            <Eye size={9} />
          </button>
        )}
      </div>
    </div>
  );
}

function MachineFloor({
  machines,
  isLoading = false,
  procedures,
  selectedProcedure,
  onProcedureChange,
  onGenerateNextStep,
  isGenerating = false,
  procDocs = [],
}: MachineFloorProps) {
  const [previewDoc, setPreviewDoc] = useState<MachineDoc | null>(null);
  const [procDocPreview, setProcDocPreview] = useState<ProcDoc | null>(null);
  const handlePreview = useCallback((doc: MachineDoc) => setPreviewDoc(doc), []);
  const closePreview = useCallback(() => setPreviewDoc(null), []);

  const handleToggleFaultMode = useCallback(async (machineId: string) => {
    try {
      await fetch(`/api/v1/wig/machines/${machineId}/fault-mode`, { method: 'POST' });
    } catch {
      // ignore — SSE will reflect the new state within 1s regardless
    }
  }, []);

  return (
    <div className="mf">
      <div className="mf__header">
        <div className="mf__header-left">
          <span className="mf__accent-bar" />
          <span className="mf__title">ASSEMBLY FLOOR</span>
        </div>
        <div className="mf__header-right">
          <div className="mf__field">
            <span className="mf__field-label">Procedure</span>
            <select
              className="mf__select"
              value={selectedProcedure}
              onChange={e => onProcedureChange(e.target.value)}
            >
              {procedures.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          {procDocs.length > 0 && (
            <div className="mf__proc-docs">
              {procDocs.map(d => {
                const colonIdx = d.name.indexOf(':');
                const code = colonIdx > -1 ? d.name.slice(0, colonIdx).trim() : '';
                const title = colonIdx > -1 ? d.name.slice(colonIdx + 1).trim() : d.name;
                return (
                  <button
                    key={d.id}
                    className="mf__proc-doc-pill"
                    onClick={() => setProcDocPreview(d)}
                    title={d.name}
                  >
                    <span className="mf__proc-doc-pill__icon"><FileText size={10} /></span>
                    {code && <span className="mf__proc-doc-pill__code">{code}</span>}
                    <span className="mf__proc-doc-pill__title">{title}</span>
                  </button>
                );
              })}
            </div>
          )}
          <button className="mf__generate-btn" onClick={onGenerateNextStep} disabled={isGenerating} aria-label="Generate Instructions">
            Generate
            <ListChecks size={13} />
          </button>
        </div>
      </div>

      <div className="mf__cards">
        {isLoading
          ? [0, 1, 2].map(i => <div key={i} className="mf-card mf-card--skeleton" />)
          : machines.map(m => <MachineCard key={m.id} machine={m} onPreviewDoc={handlePreview} onToggleFaultMode={handleToggleFaultMode} />)
        }
      </div>

      {previewDoc && <DocPreviewModal doc={previewDoc} onClose={closePreview} />}

      {procDocPreview && (
        <div className="mf-modal-backdrop" onClick={() => setProcDocPreview(null)}>
          <div className="mf-modal mf-modal--wide" onClick={e => e.stopPropagation()}>
            <div className="mf-modal__header">
              <div className="mf-modal__title-row">
                <FileText size={14} />
                <span className="mf-modal__title">{procDocPreview.name}</span>
              </div>
              <button className="mf-modal__close" onClick={() => setProcDocPreview(null)} aria-label="Close"><X size={14} /></button>
            </div>
            <div className="mf-modal__body">
              {procDocPreview.pdfUrl ? (
                <iframe src={procDocPreview.pdfUrl} className="mf-modal__pdf-embed" title={procDocPreview.name} />
              ) : (
                <div className="mf-modal__pdf-preview">
                  <FileText size={48} strokeWidth={1} />
                  <span className="mf-modal__placeholder-text">PDF not available</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default MachineFloor;
