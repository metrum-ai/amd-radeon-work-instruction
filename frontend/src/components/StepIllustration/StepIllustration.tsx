// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import './StepIllustration.css';

interface StepIllustrationProps {
  step: {
    step_id: string;
    step_number: number;
    title: string;
  } | null;
  illustration: {
    illustration_id: string;
    style: string;
    width: number;
    height: number;
    image_url?: string;
  } | null;
  isRefining?: boolean;
}

const STYLE_LABELS: Record<string, string> = {
  technical_diagram: 'Technical Diagram',
  exploded_view: 'Exploded View',
  callout: 'Line Diagram',
};

function LineDiagram() {
  return (
    <svg className="si-line-art" viewBox="0 0 420 320" xmlns="http://www.w3.org/2000/svg">
      {/* Grid */}
      <defs>
        <pattern id="si-la-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect width="420" height="320" fill="url(#si-la-grid)" />

      {/* Battery pack body */}
      <rect x="60" y="80" width="200" height="120" rx="6" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="1.2" />
      <rect x="68" y="88" width="184" height="104" rx="3" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="0.6" strokeDasharray="4 3" />

      {/* Module cells inside */}
      {[0, 1, 2, 3].map(i => (
        <rect key={i} x={78 + i * 44} y="100" width="36" height="76" rx="2"
          fill="none" stroke="rgba(242,101,34,0.35)" strokeWidth="0.8" />
      ))}
      {[0, 1, 2, 3].map(i => (
        <line key={`bus-${i}`} x1={96 + i * 44} y1="100" x2={96 + i * 44} y2="92"
          stroke="rgba(242,101,34,0.5)" strokeWidth="1" />
      ))}
      {/* Busbar across tops */}
      <line x1="96" y1="92" x2="228" y2="92" stroke="rgba(242,101,34,0.5)" strokeWidth="1.2" />

      {/* HV cables routing out */}
      <path d="M 260 130 C 280 130, 290 110, 310 110" fill="none" stroke="#ED1C24" strokeWidth="1.5" opacity="0.7" />
      <path d="M 260 160 C 280 160, 290 180, 310 180" fill="none" stroke="#60a5fa" strokeWidth="1.5" opacity="0.7" />

      {/* HV+ / HV- labels */}
      <text x="316" y="113" fill="#ED1C24" fontSize="8" fontFamily="monospace" fontWeight="700" opacity="0.9">HV+</text>
      <text x="316" y="183" fill="#60a5fa" fontSize="8" fontFamily="monospace" fontWeight="700" opacity="0.9">HV-</text>

      {/* Connector blocks */}
      <rect x="336" y="104" width="24" height="14" rx="2" fill="none" stroke="#ED1C24" strokeWidth="1" opacity="0.6" />
      <rect x="336" y="174" width="24" height="14" rx="2" fill="none" stroke="#60a5fa" strokeWidth="1" opacity="0.6" />

      {/* LOTO lockout point */}
      <circle cx="348" cy="148" r="10" fill="none" stroke="#fbbf24" strokeWidth="1.2" opacity="0.8" />
      <rect x="344" y="144" width="8" height="8" rx="1" fill="none" stroke="#fbbf24" strokeWidth="0.8" opacity="0.8" />
      <line x1="348" y1="152" x2="348" y2="160" stroke="#fbbf24" strokeWidth="0.8" opacity="0.6" />

      {/* Callout line from LOTO to label */}
      <line x1="358" y1="142" x2="390" y2="122" stroke="rgba(251,191,36,0.4)" strokeWidth="0.6" strokeDasharray="3 2" />
      <text x="370" y="118" fill="#fbbf24" fontSize="7" fontFamily="monospace" fontWeight="600" opacity="0.9">LOTO</text>
      <text x="370" y="126" fill="#fbbf24" fontSize="6" fontFamily="monospace" opacity="0.6">LOCK PT</text>

      {/* PPE callout */}
      <line x1="100" y1="210" x2="100" y2="240" stroke="rgba(52,211,153,0.3)" strokeWidth="0.6" strokeDasharray="3 2" />
      <line x1="100" y1="240" x2="140" y2="240" stroke="rgba(52,211,153,0.3)" strokeWidth="0.6" strokeDasharray="3 2" />

      {/* Glove icon (simplified) */}
      <ellipse cx="80" cy="258" rx="10" ry="14" fill="none" stroke="rgba(52,211,153,0.5)" strokeWidth="0.8" />
      <line x1="76" y1="248" x2="72" y2="240" stroke="rgba(52,211,153,0.5)" strokeWidth="0.6" />
      <line x1="84" y1="248" x2="88" y2="240" stroke="rgba(52,211,153,0.5)" strokeWidth="0.6" />
      <text x="96" y="255" fill="rgba(52,211,153,0.8)" fontSize="7" fontFamily="monospace" fontWeight="600">CLASS 0</text>
      <text x="96" y="263" fill="rgba(52,211,153,0.8)" fontSize="6" fontFamily="monospace" opacity="0.6">INS. GLOVES</text>

      {/* HV indicator panel */}
      <rect x="60" y="210" width="30" height="18" rx="2" fill="none" stroke="rgba(52,211,153,0.4)" strokeWidth="0.8" />
      <circle cx="70" cy="219" r="3" fill="rgba(52,211,153,0.6)" />
      <circle cx="82" cy="219" r="3" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="0.5" />
      <text x="60" y="236" fill="rgba(52,211,153,0.6)" fontSize="6" fontFamily="monospace">HV STATUS</text>

      {/* Title block (bottom right, engineering-style) */}
      <rect x="280" y="260" width="130" height="50" rx="2" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="0.6" />
      <line x1="280" y1="274" x2="410" y2="274" stroke="rgba(255,255,255,0.08)" strokeWidth="0.4" />
      <line x1="280" y1="288" x2="410" y2="288" stroke="rgba(255,255,255,0.08)" strokeWidth="0.4" />
      <text x="286" y="270" fill="rgba(255,255,255,0.35)" fontSize="6" fontFamily="monospace" fontWeight="700">EV BATTERY PACK GEN4</text>
      <text x="286" y="284" fill="rgba(255,255,255,0.25)" fontSize="5.5" fontFamily="monospace">HV HARNESS ROUTING</text>
      <text x="286" y="298" fill="rgba(255,255,255,0.2)" fontSize="5" fontFamily="monospace">CELL-HV-001 / REV 1.0</text>
      <text x="286" y="306" fill="rgba(242,101,34,0.4)" fontSize="5" fontFamily="monospace" fontWeight="700">OPENCLAW WI GENERATOR</text>

      {/* Dimension line across pack */}
      <line x1="60" y1="70" x2="260" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="0.4" />
      <line x1="60" y1="66" x2="60" y2="74" stroke="rgba(255,255,255,0.15)" strokeWidth="0.4" />
      <line x1="260" y1="66" x2="260" y2="74" stroke="rgba(255,255,255,0.15)" strokeWidth="0.4" />
      <text x="140" y="68" fill="rgba(255,255,255,0.2)" fontSize="6" fontFamily="monospace" textAnchor="middle">480mm</text>

      {/* Pack label */}
      <text x="120" y="147" fill="rgba(255,255,255,0.12)" fontSize="14" fontFamily="monospace" fontWeight="700" textAnchor="middle">BATTERY PACK</text>
    </svg>
  );
}

function StepIllustration({ step, illustration, isRefining = false }: StepIllustrationProps) {
  if (!step || !illustration) {
    return null;
  }

  return (
    <div className="si">
      <div className="si-header">
        <span className="si-header-label">ILLUSTRATION</span>
        <div className="si-header-right">
          <span className="si-style-tag">
            {isRefining ? 'Regenerating…' : (STYLE_LABELS[illustration.style] || illustration.style)}
          </span>
        </div>
      </div>

      <div className="si-step-label">
        <span className="si-step-num">Step {step.step_number}</span>
        <span className="si-step-title">{step.title}</span>
      </div>

      <div className="si-canvas">
        {isRefining && (
          <div className="si-refining-overlay">
            <div className="si-refining-spinner" />
            <span className="si-refining-text">Regenerating illustration…</span>
          </div>
        )}
        {illustration.image_url ? (
          <img
            src={illustration.image_url}
            alt={`Step ${step.step_number} illustration`}
            className="si-generated-image"
          />
        ) : (
          <LineDiagram />
        )}
      </div>
    </div>
  );
}

export default StepIllustration;
