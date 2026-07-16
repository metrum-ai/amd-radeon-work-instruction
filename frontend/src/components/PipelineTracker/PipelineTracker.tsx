// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  FileSearch,
  BookOpen,
  Cpu,
  MapPin,
  ShieldCheck,
  PenTool,
  Image,
  LayoutDashboard,
  Check,
} from 'lucide-react';
import './PipelineTracker.css';

type AgentStatus = 'completed' | 'active' | 'pending' | 'blocked';

interface PipelineAgent {
  id: string;
  name: string;
  shortName: string;
  description: string;
  icon: React.ReactNode;
  status: AgentStatus;
}

interface GenerationContext {
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

interface GenerationStatusLike {
  status: string;
  current_step?: string | null;
  progress_percent?: number;
  context?: GenerationContext | null;
}

interface PipelineTrackerProps {
  hasDocument: boolean;
  isGenerating?: boolean;
  generationStatus?: GenerationStatusLike | null;
}

const AGENT_ORDER = [
  'source_document', 'machine_state', 'procedure_context', 'sop_reference',
  'orchestrator', 'safety_interlock', 'instruction_author', 'illustration',
];

// ── Agentic graph layout — SVG coordinate space (viewBox 0 0 1000 520) ──
const NODE_POS: Record<string, { x: number; y: number }> = {
  source_document:    { x: 120,  y: 95  },
  machine_state:      { x: 370,  y: 95  },
  procedure_context:  { x: 630,  y: 95  },
  sop_reference:      { x: 880,  y: 95  },
  orchestrator:       { x: 250,  y: 285 },
  safety_interlock:   { x: 750,  y: 285 },
  instruction_author: { x: 390,  y: 455 },
  illustration:       { x: 700,  y: 455 },
};

// Visual edges: 4 inputs converge into decision pair → outputs
const VISUAL_EDGES: Array<{ from: string; to: string }> = [
  { from: 'source_document',    to: 'orchestrator'       },
  { from: 'machine_state',      to: 'orchestrator'       },
  { from: 'procedure_context',  to: 'safety_interlock'   },
  { from: 'sop_reference',      to: 'safety_interlock'   },
  { from: 'orchestrator',       to: 'safety_interlock'   },
  { from: 'safety_interlock',   to: 'instruction_author' },
  { from: 'instruction_author', to: 'illustration'       },
];

const NODE_HALF = 54; // half-size in SVG units, used for edge offset from center

function edgePath(fromId: string, toId: string): string {
  const { x: x1, y: y1 } = NODE_POS[fromId];
  const { x: x2, y: y2 } = NODE_POS[toId];
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / len, uy = dy / len;
  const sx = x1 + ux * NODE_HALF, sy = y1 + uy * NODE_HALF;
  const ex = x2 - ux * NODE_HALF, ey = y2 - uy * NODE_HALF;
  // subtle perpendicular curve for organic feel
  const perp = Math.min(len * 0.12, 38);
  const mx = (sx + ex) / 2 - uy * perp;
  const my = (sy + ey) / 2 + ux * perp;
  return `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;
}

function parseCurrentStep(s: string | null | undefined): { agentId: string; done: number; total: number } | null {
  if (!s) return null;
  const [agentId, progress] = s.split(':');
  if (!progress) return { agentId, done: 0, total: 0 };
  const [done, total] = progress.split('/').map(Number);
  return { agentId, done, total };
}

function resolveStatus(
  agentId: string,
  genStatus: GenerationStatusLike | null | undefined,
  hasDocument: boolean,
  isGenerating: boolean,
): AgentStatus {
  if (genStatus?.status === 'failed') return 'pending';
  if ((genStatus?.progress_percent ?? 0) >= 100) return 'completed';

  const parsed = parseCurrentStep(genStatus?.current_step);
  const activeAgentId = parsed?.agentId ?? null;

  if (!activeAgentId) {
    if (isGenerating) return agentId === 'source_document' ? 'active' : 'pending';
    return hasDocument ? 'completed' : 'pending';
  }

  const myIdx = AGENT_ORDER.indexOf(agentId);
  const activeIdx = AGENT_ORDER.indexOf(activeAgentId);
  if (myIdx < activeIdx) return 'completed';
  if (myIdx === activeIdx) return 'active';
  return 'pending';
}

function useElapsedTimer(running: boolean) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);

  useEffect(() => {
    if (running) {
      startRef.current = Date.now() - elapsed * 1000;
      tickRef.current = window.setInterval(() => {
        setElapsed(Math.floor((Date.now() - startRef.current!) / 1000));
      }, 1000);
    } else {
      if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
      if (!running) setElapsed(0);
    }
    return () => { if (tickRef.current) clearInterval(tickRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const ss = String(elapsed % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function PipelineTracker({
  hasDocument,
  isGenerating = false,
  generationStatus,
}: PipelineTrackerProps) {
  const parsed = parseCurrentStep(generationStatus?.current_step);
  const timer = useElapsedTimer(isGenerating);

  const AGENT_DEFS: Omit<PipelineAgent, 'status'>[] = [
    { id: 'source_document',    name: 'Source Document Agent',         shortName: 'Source Doc',    description: 'Extracts OEM manuals, images, warnings & citations',      icon: <FileSearch size={26} /> },
    { id: 'machine_state',      name: 'Machine State Agent',           shortName: 'Machine State', description: 'Reads simulator state, alarms & readiness',               icon: <Cpu size={26} /> },
    { id: 'procedure_context',  name: 'Procedure Context Agent',       shortName: 'Proc Context',  description: 'Maps procedure to station context',                       icon: <MapPin size={26} /> },
    { id: 'sop_reference',      name: 'SOP Reference Agent',           shortName: 'SOP Ref',       description: 'Enforces SOP, LOTO, PPE & quality rules',                 icon: <BookOpen size={26} /> },
    { id: 'orchestrator',       name: 'Work Instruction Orchestrator', shortName: 'Orchestrator',  description: 'Routes state-aware pipeline & interlock gates',           icon: <LayoutDashboard size={26} /> },
    { id: 'safety_interlock',   name: 'Safety & Interlock Agent',      shortName: 'Safety',        description: 'Validates safety gates before generation',               icon: <ShieldCheck size={26} /> },
    { id: 'instruction_author', name: 'Instruction Author Agent',      shortName: 'Author',        description: 'Creates state-aware multilingual operator steps',        icon: <PenTool size={26} /> },
    { id: 'illustration',       name: 'Technical Illustration Agent',  shortName: 'Illustration',  description: 'Unified line art from photos, blueprints & schematics', icon: <Image size={26} /> },
  ];

  const agents: PipelineAgent[] = AGENT_DEFS.map(def => ({
    ...def,
    status: resolveStatus(def.id, generationStatus, hasDocument, isGenerating),
  }));

  const agentMap = new Map<string, AgentStatus>(agents.map(a => [a.id, a.status]));
  const completedCount = agents.filter(a => a.status === 'completed').length;
  const activeAgent = agents.find(a => a.status === 'active');
  const progress = generationStatus?.progress_percent ?? 0;
  const ctx = generationStatus?.context;
  const showCtx = (isGenerating || hasDocument) && !!ctx;

  return (
    <div className={`ptc${showCtx ? ' ptc--split' : ''}`}>

      {/* ── Header — spans full width ── */}
      <div className="ptc__header">
        <div className="ptc__title-group">
          <span className="ptc__accent" />
          <div className="ptc__title-text">
            <span className="ptc__title">OPENCLAW DYNAMIC PIPELINE</span>
            <span className="ptc__subtitle">State-Aware Generation Agents</span>
          </div>
        </div>
        <div className="ptc__stats">
          {isGenerating ? (
            <span className="ptc__timer">
              <span className="ptc__timer-dot" />
              <span className="ptc__timer-val">{timer}</span>
            </span>
          ) : hasDocument ? (
            <span className="ptc__timer ptc__timer--done">
              <Check size={11} strokeWidth={2.5} />
              <span className="ptc__timer-val">{completedCount} / {agents.length}</span>
            </span>
          ) : null}
          {activeAgent && isGenerating && (
            <span className="ptc__active-badge">
              <span className="ptc__active-dot" />
              {activeAgent.shortName}
            </span>
          )}
        </div>
      </div>

      {showCtx && <div className="ptc__h-sep" />}

      {/* ── Agentic graph canvas ── */}
      <div className="ptc__pipeline">
        <div className="ptc__canvas">

          {/* SVG edge layer */}
          <svg className="ptc__edges" viewBox="0 0 1000 520" preserveAspectRatio="none">
            <defs>
              <filter id="ptc-glow-g" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="4" result="blur"/>
                <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
              <filter id="ptc-glow-o" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="6" result="blur"/>
                <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
              <pattern id="ptc-dots" x="0" y="0" width="44" height="44" patternUnits="userSpaceOnUse">
                <circle cx="22" cy="22" r="1" fill="rgba(255,255,255,0.035)"/>
              </pattern>
            </defs>

            {/* Atmospheric dot grid */}
            <rect width="1000" height="520" fill="url(#ptc-dots)"/>

            {/* Edges */}
            {VISUAL_EDGES.map(({ from, to }) => {
              const d = edgePath(from, to);
              const edgeId = `ptce-${from.replace(/_/g,'-')}-${to.replace(/_/g,'-')}`;
              const fromSt = agentMap.get(from) ?? 'pending';
              const toSt   = agentMap.get(to)   ?? 'pending';
              const completed = fromSt === 'completed' && toSt === 'completed';
              const active    = fromSt === 'completed' && toSt === 'active';
              return (
                <g key={edgeId}>
                  {/* Dim track */}
                  <path d={d} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="1.5"/>
                  {/* Glowing completed path */}
                  {completed && (
                    <path d={d} fill="none" stroke="rgba(34,197,94,0.5)" strokeWidth="2"
                      filter="url(#ptc-glow-g)"/>
                  )}
                  {/* Animated active flow */}
                  {active && (
                    <>
                      <path d={d} fill="none" stroke="rgba(242,101,34,0.4)" strokeWidth="2.5"
                        filter="url(#ptc-glow-o)"/>
                      <path id={edgeId} d={d} fill="none"
                        stroke="rgba(242,101,34,0.95)" strokeWidth="2"
                        strokeDasharray="7 15"
                        className="ptc-edge--active"/>
                      {/* Particle */}
                      <circle r="5" fill="#f26522"
                        style={{ filter: 'drop-shadow(0 0 6px rgba(242,101,34,1))' }}>
                        <animateMotion dur="1.3s" repeatCount="indefinite"
                          calcMode="spline" keyTimes="0;1" keySplines="0.42 0 0.58 1">
                          <mpath href={`#${edgeId}`}/>
                        </animateMotion>
                      </circle>
                    </>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Agent nodes */}
          {agents.map(agent => (
            <AgentNode key={agent.id} agent={agent} parsed={parsed}/>
          ))}
        </div>
      </div>

      {/* ── Footer — spans full width ── */}
      <div className="ptc__footer">
        <div className="ptc__progress-track">
          <div className="ptc__progress-fill" style={{ width: `${progress}%` }}/>
        </div>
        <span className="ptc__progress-label">
          {isGenerating
            ? `${Math.round(progress)}% — ${activeAgent?.name ?? 'processing'}`
            : hasDocument
            ? 'Generation complete'
            : 'Select a procedure and press Generate to run the pipeline'}
        </span>
      </div>

      {/* ── Vertical divider + sidebar ── */}
      {showCtx && ctx && (
        <>
          <div className="ptc__divider"/>
          <div className="ptc__sidebar">
            <ContextStrip ctx={ctx} isGenerating={isGenerating}/>
          </div>
        </>
      )}
    </div>
  );
}

function ContextStrip({ ctx, isGenerating }: { ctx: GenerationContext; isGenerating: boolean }) {
  type Pill = { label: string; value: string; variant?: 'warn' | 'ok' | 'info' | 'model' | 'step' };

  const pills: Pill[] = [];

  if (ctx.procedure_name) pills.push({ label: 'PROCEDURE', value: ctx.procedure_name });
  if (ctx.station_id)     pills.push({ label: 'STATION',   value: ctx.station_id });
  if (ctx.machine_id)     pills.push({ label: 'MACHINE',   value: ctx.machine_id });

  if (ctx.machine_state) {
    const variant = ctx.machine_state === 'unknown' ? 'warn'
      : ctx.active_alarms ? 'warn' : 'ok';
    pills.push({ label: 'MACHINE STATE', value: ctx.machine_state.toUpperCase(), variant });
  }

  if (typeof ctx.active_alarms === 'number') {
    pills.push({
      label: 'ALARMS',
      value: ctx.active_alarms === 0 ? 'NONE' : `${ctx.active_alarms} ACTIVE`,
      variant: ctx.active_alarms > 0 ? 'warn' : 'ok',
    });
  }

  if (ctx.interlock_status) {
    pills.push({
      label: 'INTERLOCK',
      value: ctx.interlock_status.toUpperCase(),
      variant: ctx.interlock_status === 'pass' ? 'ok' : ctx.interlock_status === 'blocked' ? 'warn' : 'info',
    });
  }

  if (ctx.safety_warnings !== undefined)
    pills.push({ label: 'SAFETY RULES', value: `${ctx.safety_warnings}`, variant: 'info' });

  if (ctx.loto_rules !== undefined)
    pills.push({ label: 'LOTO RULES', value: `${ctx.loto_rules}`, variant: 'info' });

  if (ctx.steps_planned !== undefined)
    pills.push({ label: 'STEPS PLANNED', value: `${ctx.steps_planned}`, variant: 'info' });

  if (ctx.current_step_desc && isGenerating)
    pills.push({ label: 'AUTHORING', value: ctx.current_step_desc, variant: 'step' });

  if (ctx.readiness_flags) {
    const flagEntries = Object.entries(ctx.readiness_flags);
    if (flagEntries.length) {
      const ready = flagEntries.filter(([, v]) => v).length;
      pills.push({
        label: 'READINESS',
        value: `${ready}/${flagEntries.length} READY`,
        variant: ready === flagEntries.length ? 'ok' : 'warn',
      });
    }
  }

  if (!pills.length) return null;

  return (
    <div className="ptc__ctx">
      {pills.map((p, i) => (
        <span key={i} className={`ptc__ctx-pill${p.variant ? ` ptc__ctx-pill--${p.variant}` : ''}`}>
          <span className="ptc__ctx-label">{p.label}</span>
          <MarqueeValue value={p.value} className="ptc__ctx-value"/>
        </span>
      ))}
    </div>
  );
}

/* ── MarqueeValue: ellipsis at rest; on hover → reveal once then loop with ◆ ── */
function MarqueeValue({ value, className }: { value: string; className: string }) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const measureRef   = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [phase, setPhase]     = useState<'idle' | 'reveal' | 'loop'>('idle');
  const overflows             = useRef(false);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure   = measureRef.current;
    if (container && measure) {
      overflows.current = measure.scrollWidth > container.clientWidth + 1;
    }
  }, [value]);

  const onEnter = () => { if (overflows.current) { setHovered(true); setPhase('reveal'); } };
  const onLeave = () => { setHovered(false); setPhase('idle'); };
  const onAnimEnd = () => { if (phase === 'reveal') setPhase('loop'); };

  const DIAMOND = '  ◆  ';
  const displayText = hovered ? `${value}${DIAMOND}${value}${DIAMOND}` : value;

  return (
    <span
      ref={containerRef}
      className={`${className}${phase !== 'idle' ? ` ptc__ctx-value--${phase}` : ''}`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <span ref={measureRef} className="ptc__ctx-measure">{value}</span>
      <span className="ptc__ctx-scroll-inner" onAnimationEnd={onAnimEnd}>
        {displayText}
      </span>
    </span>
  );
}

/* ── AgentNode — absolute-positioned graph node ── */
interface AgentNodeProps {
  agent: PipelineAgent;
  parsed: { agentId: string; done: number; total: number } | null;
}

function AgentNode({ agent, parsed }: AgentNodeProps) {
  const pos = NODE_POS[agent.id];
  const stepProgress = parsed?.agentId === agent.id && parsed.total > 0
    ? `${parsed.done}/${parsed.total}`
    : null;

  return (
    <div
      className={`ptc-node ptc-node--${agent.status}`}
      style={{ left: `${pos.x / 10}%`, top: `${pos.y / 5.2}%` }}
      title={agent.description}
    >
      <div className="ptc-node__inner">
        <div className="ptc-node__icon">
          {agent.status === 'completed'
            ? <Check size={26} strokeWidth={2.5}/>
            : agent.icon}
        </div>
        <span className="ptc-node__name">{agent.shortName}</span>
        {stepProgress ? (
          <span className="ptc-node__step">{stepProgress}</span>
        ) : agent.status === 'active' ? (
          <span className="ptc-node__dots">
            <span className="ptc-node__dot" style={{ animationDelay: '0ms' }}/>
            <span className="ptc-node__dot" style={{ animationDelay: '160ms' }}/>
            <span className="ptc-node__dot" style={{ animationDelay: '320ms' }}/>
          </span>
        ) : null}
      </div>
      {agent.status === 'active' && <div className="ptc-node__scan"/>}
    </div>
  );
}

export default PipelineTracker;
