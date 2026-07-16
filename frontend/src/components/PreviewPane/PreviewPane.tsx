// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  AlertTriangle,
  FileText,
} from 'lucide-react';
import './PreviewPane.css';

interface PreviewPaneProps {
  document: {
    title: string;
    asset_id: string | null;
    procedure_id: string | null;
    status: string;
  } | null;
  steps: Array<{
    step_id?: string;
    step_number: number;
    title: string;
    instruction_text: string;
    safety_warnings: string[];
    source_citations: string[];
    tools_required: string[];
    quality_checks: string[];
    illustration_url?: string | null;
    interlock_status?: string | null;
  }>;
  selectedStepId: string | null;
  refinedStepIds?: Set<string>;
}

type ImageInfo = { dataUrl: string; w: number; h: number };

async function fetchImageInfo(url: string): Promise<ImageInfo | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const blob = await res.blob();
    const dataUrl = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsDataURL(blob);
    });
    const dims = await new Promise<{ w: number; h: number }>((resolve) => {
      const img = new Image();
      img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
      img.onerror = () => resolve({ w: 768, h: 512 });
      img.src = dataUrl;
    });
    return { dataUrl, ...dims };
  } catch {
    return null;
  }
}

function PreviewPane({ document, steps, selectedStepId, refinedStepIds }: PreviewPaneProps) {
  const [format, setFormat] = useState<'pdf' | 'html'>('pdf');
  const [zoom, setZoom] = useState(100);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<Map<number, HTMLElement>>(new Map());

  const selectedStepNumber = selectedStepId
    ? parseInt(selectedStepId.replace(/\D/g, ''), 10) || null
    : null;

  useEffect(() => {
    if (selectedStepNumber === null) return;
    const el = stepRefs.current.get(selectedStepNumber);
    if (el && scrollRef.current) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [selectedStepNumber]);

  const setStepRef = useCallback(
    (stepNumber: number, el: HTMLElement | null) => {
      if (el) {
        stepRefs.current.set(stepNumber, el);
      } else {
        stepRefs.current.delete(stepNumber);
      }
    },
    [],
  );

  const handleZoomIn = () => setZoom((z: number) => Math.min(z + 10, 150));
  const handleZoomOut = () => setZoom((z: number) => Math.max(z - 10, 60));
  const handleZoomReset = () => setZoom(100);

  // Escape untrusted (LLM/user) text before interpolating into the export HTML.
  const esc = (s: string) =>
    s.replace(
      /[&<>"']/g,
      (c) =>
        ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        })[c] as string,
    );

  const buildDocHtml = (imageCache: Record<string, ImageInfo>) => {
    const title = esc(document?.title ?? 'Work Instruction');
    const stepsHtml = steps
      .map((step) => {
        const warnings = step.safety_warnings.length
          ? `<div class="warning"><strong>⚠ SAFETY WARNING</strong>${step.safety_warnings.map((w) => `<p>${esc(w)}</p>`).join('')}</div>`
          : '';
        const tools = step.tools_required.length
          ? `<p><strong>Tools:</strong> ${esc(step.tools_required.join(', '))}</p>`
          : '';
        const checks = step.quality_checks.length
          ? `<div><strong>Quality Checks</strong><ul>${step.quality_checks.map((c) => `<li>${esc(c)}</li>`).join('')}</ul></div>`
          : '';
        const sources = step.source_citations.length
          ? `<div class="sources">${step.source_citations.map((s, i) => `<span>[${i + 1}] ${esc(s)}</span>`).join(' ')}</div>`
          : '';
        const body = `<p>${esc(step.instruction_text)}</p>`;
        const illUrl = step.illustration_url;
        const illHtml = illUrl && imageCache[illUrl]
          ? `<figure style="margin:12px 0"><img src="${imageCache[illUrl].dataUrl}" alt="${esc(step.title)}" style="max-width:100%;height:auto;border-radius:4px"/></figure>`
          : '';
        const isBlocked = step.interlock_status === 'blocked';
        const isRefined = step.step_id ? refinedStepIds?.has(step.step_id) : false;
        const interlockBanner = isBlocked
          ? `<div style="background:#b71c1c;color:#fff;padding:6px 10px;margin-bottom:8px;font-weight:bold;font-size:.8rem;letter-spacing:.04em">⛔ INTERLOCK BLOCKED — Resolve this prerequisite before proceeding</div>`
          : '';
        const refinedBadge = isRefined
          ? `<span style="display:inline-flex;align-items:center;gap:3px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#7c3aed;background:#ede9fe;padding:1px 7px;border-radius:10px;margin-left:8px">✦ Refined</span>`
          : '';
        const stepBg = isBlocked ? '#fff8f8' : '#fff';
        const borderColor = isBlocked ? '#b71c1c' : '#003366';
        const titleColor = isBlocked ? '#b71c1c' : '#003366';
        return `<div class="step" style="background:${stepBg};border-left-color:${borderColor}">${interlockBanner}<div class="step-header"><span class="step-num" style="background:${borderColor}">Step ${step.step_number}</span> <span class="step-title" style="color:${titleColor}">${esc(step.title)}</span>${refinedBadge}</div>${warnings}${body}${illHtml}${tools}${checks}${sources}<hr/></div>`;
      })
      .join('');

    return `<!DOCTYPE html><html><head><meta charset="utf-8"/><title>${title}</title><style>
body{font-family:system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 24px;color:#1a1a2e;line-height:1.6}
h1{font-size:1.6rem;margin-bottom:4px}.meta{display:flex;gap:24px;font-size:.8rem;color:#666;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid #e2e8f0}
.meta span{display:flex;flex-direction:column}.meta strong{font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:#999}
.step{margin-bottom:28px}.step-header{display:flex;align-items:baseline;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.step-num{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;background:#1a1a2e;color:#fff;padding:2px 8px;border-radius:3px;flex-shrink:0}
.step-title{font-weight:600;font-size:1rem;min-width:0;overflow-wrap:break-word}.warning{background:#fff8f0;border-left:3px solid #f59e0b;padding:10px 14px;margin:10px 0;border-radius:0 4px 4px 0}
.sources{font-size:.75rem;color:#888;margin-top:8px}hr{border:none;border-top:1px solid #e2e8f0;margin:20px 0}
@media print{body{margin:0}.step{page-break-inside:avoid}}
</style></head><body>
<div style="font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#999;margin-bottom:4px">WORK INSTRUCTION</div>
<h1>${title}</h1>
<div class="meta">
${document?.asset_id ? `<span><strong>Asset ID</strong>${esc(document.asset_id)}</span>` : ''}
${document?.procedure_id ? `<span><strong>Procedure</strong>${esc(document.procedure_id)}</span>` : ''}
<span><strong>Status</strong>${esc(document?.status ?? '')}</span>
<span><strong>Revision</strong>1.0</span>
</div>
${stepsHtml}
</body></html>`;
  };

  const handleDownload = async () => {
    // Pre-fetch all illustrations in parallel before generating output
    const imageCache: Record<string, ImageInfo> = {};
    await Promise.all(
      steps
        .filter((s) => s.illustration_url)
        .map(async (s) => {
          const info = await fetchImageInfo(s.illustration_url!);
          if (info) imageCache[s.illustration_url!] = info;
        }),
    );

    if (format === 'html') {
      const html = buildDocHtml(imageCache);
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement('a');
      a.href = url;
      a.download = `${document?.title ?? 'work-instruction'}.html`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }

    const { default: jsPDF } = await import('jspdf');

    const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const ml = 18;
    const mr = 18;
    const contentW = pageW - ml - mr;
    let y = 18;

    const lineH = (fs: number) => fs * 0.45;

    const needPage = (h: number) => {
      if (y + h > pageH - 14) { pdf.addPage(); y = 18; }
    };

    const writeText = (text: string, fs: number, bold = false, color: [number,number,number] = [30,30,50]) => {
      pdf.setFont('helvetica', bold ? 'bold' : 'normal');
      pdf.setFontSize(fs);
      pdf.setTextColor(...color);
      const lines = pdf.splitTextToSize(text, contentW);
      const blockH = lines.length * lineH(fs);
      needPage(blockH);
      pdf.text(lines, ml, y);
      y += blockH + 1;
    };

    const hRule = (color: [number,number,number] = [220,220,230]) => {
      pdf.setDrawColor(...color);
      pdf.line(ml, y, pageW - mr, y);
      y += 4;
    };

    // ── Document header ──────────────────────────────────────────
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(7);
    pdf.setTextColor(160, 160, 180);
    pdf.text('WORK INSTRUCTION', ml, y);
    y += 5;

    writeText(document?.title ?? 'Work Instruction', 18, true, [20, 20, 45]);
    y += 1;

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(120, 120, 140);
    const metaParts = [
      document?.asset_id ? `Asset: ${document.asset_id}` : null,
      document?.procedure_id ? `Procedure: ${document.procedure_id}` : null,
      `Status: ${document?.status ?? ''}`,
      'Rev: 1.0',
    ].filter(Boolean).join('    ');
    pdf.text(metaParts, ml, y);
    y += 6;

    hRule([180, 180, 200]);

    // ── Steps ────────────────────────────────────────────────────
    steps.forEach((step) => {
      needPage(20);

      // Interlock banner
      const interlockStatus = step.interlock_status;
      if (interlockStatus === 'blocked') {
        needPage(10);
        pdf.setFillColor(183, 28, 28);
        pdf.rect(ml, y - 4, contentW, 8, 'F');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(8);
        pdf.setTextColor(255, 255, 255);
        pdf.text('INTERLOCK BLOCKED — Resolve this prerequisite before proceeding', ml + 3, y);
        y += 8;
      }

      // Step badge + title
      const badge = `Step ${step.step_number}`;
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(7);
      const bw = pdf.getTextWidth(badge) + 6;

      // Measure the (possibly wrapped) title before drawing anything, so we
      // can page-break for the whole header block rather than splitting it.
      pdf.setFontSize(10);
      const titleX = ml + bw + 3;
      const titleW = Math.max(contentW - bw - 3, 20);
      const titleLines = pdf.splitTextToSize(step.title, titleW);
      const titleBlockH = Math.max(titleLines.length * lineH(10), 5);
      needPage(titleBlockH);

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(7);
      pdf.setTextColor(255, 255, 255);
      pdf.setFillColor(interlockStatus === 'blocked' ? 183 : 30, interlockStatus === 'blocked' ? 28 : 30, interlockStatus === 'blocked' ? 28 : 50);
      pdf.roundedRect(ml, y - 3.5, bw, 5, 1, 1, 'F');
      pdf.text(badge, ml + 3, y);

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.setTextColor(interlockStatus === 'blocked' ? 183 : 20, interlockStatus === 'blocked' ? 28 : 20, interlockStatus === 'blocked' ? 28 : 45);
      titleLines.forEach((line: string, i: number) => {
        pdf.text(line, titleX, y + i * lineH(10));
      });

      // Refined badge — placed after the last title line, wrapping below if
      // it doesn't fit alongside a long final line.
      const isRefined = step.step_id ? refinedStepIds?.has(step.step_id) : false;
      if (isRefined) {
        const lastLine = titleLines[titleLines.length - 1];
        const lastLineW = pdf.getTextWidth(lastLine);
        const lastLineY = y + (titleLines.length - 1) * lineH(10);
        const rbLabel = '• Refined'; // jsPDF's standard fonts only support WinAnsi; ✦ renders as garbage
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(6);
        const rbW = pdf.getTextWidth(rbLabel) + 5;
        const inlineX = titleX + lastLineW + 4;
        const fitsInline = inlineX + rbW <= ml + contentW;
        const rbX = fitsInline ? inlineX : titleX;
        const rbY = fitsInline ? lastLineY : lastLineY + 5;
        pdf.setFillColor(237, 233, 254);
        pdf.roundedRect(rbX, rbY - 3, rbW, 4.5, 1, 1, 'F');
        pdf.setTextColor(124, 58, 237);
        pdf.text(rbLabel, rbX + 2, rbY);
      }

      y += titleBlockH + 2;

      // Safety warnings — before instruction text (safety-critical info first)
      if (step.safety_warnings.length > 0) {
        needPage(10);
        pdf.setFillColor(255, 248, 235);
        const warnStartY = y - 2;
        const warnLines = step.safety_warnings.flatMap((w) =>
          pdf.splitTextToSize(w, contentW - 8),
        );
        const warnH = lineH(8) * (1 + warnLines.length) + 6;
        pdf.roundedRect(ml, warnStartY, contentW, warnH, 1.5, 1.5, 'F');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(7.5);
        pdf.setTextColor(180, 90, 0);
        pdf.text('[!] SAFETY WARNING', ml + 4, y + 1);
        y += lineH(8) + 1;
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(8);
        pdf.setTextColor(140, 70, 0);
        warnLines.forEach((line: string) => {
          pdf.text(line, ml + 4, y);
          y += lineH(8);
        });
        y += 4;
      }

      // Instruction text (strip HTML tags)
      const plain = step.instruction_text.replace(/<[^>]+>/g, '').replace(/&[a-z]+;/gi, ' ').trim();
      writeText(plain, 9, false, [50, 50, 70]);

      // Illustration
      const illUrl = step.illustration_url;
      if (illUrl && imageCache[illUrl]) {
        const { dataUrl, w, h } = imageCache[illUrl];
        const imgW = contentW;
        const imgH = Math.min((h / w) * imgW, 70); // cap at 70mm so it never swamps a page
        needPage(imgH + 4);
        const imgFmt = dataUrl.startsWith('data:image/jpeg') ? 'JPEG' : 'PNG';
        pdf.addImage(dataUrl, imgFmt, ml, y, imgW, imgH);
        y += imgH + 4;
      }

      // Tools
      if (step.tools_required.length > 0) {
        needPage(6);
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(8);
        pdf.setTextColor(80, 80, 100);
        pdf.text('Tools:', ml, y);
        pdf.setFont('helvetica', 'normal');
        pdf.setTextColor(60, 60, 80);
        const toolsLines = pdf.splitTextToSize(step.tools_required.join(', '), contentW - 14);
        pdf.text(toolsLines, ml + 14, y);
        y += toolsLines.length * lineH(8) + 3;
      }

      // Quality checks
      if (step.quality_checks.length > 0) {
        needPage(8);
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(8);
        pdf.setTextColor(40, 120, 80);
        pdf.text('Quality Checks', ml, y);
        y += lineH(8) + 1;
        pdf.setFont('helvetica', 'normal');
        step.quality_checks.forEach((c) => {
          const lines = pdf.splitTextToSize(`•  ${c}`, contentW - 4);
          needPage(lines.length * lineH(8));
          pdf.setFontSize(8);
          pdf.setTextColor(50, 100, 70);
          pdf.text(lines, ml + 2, y);
          y += lines.length * lineH(8) + 1;
        });
        y += 2;
      }

      // Source citations
      if (step.source_citations.length > 0) {
        needPage(5);
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(7);
        pdf.setTextColor(150, 150, 170);
        const cites = step.source_citations.map((s, i) => `[${i + 1}] ${s}`).join('  ');
        const cLines = pdf.splitTextToSize(cites, contentW);
        pdf.text(cLines, ml, y);
        y += cLines.length * lineH(7) + 2;
      }

      hRule();
    });

    pdf.save(`${document?.title ?? 'work-instruction'}.pdf`);
  };

  return (
    <div className="preview-pane">
      <div className="preview-toolbar">
        <div className="preview-toolbar-zoom">
          <button className="preview-toolbar-btn" onClick={handleZoomOut}>
            <ZoomOut size={14} />
          </button>
          <span className="preview-toolbar-zoom-value mono">{zoom}%</span>
          <button className="preview-toolbar-btn" onClick={handleZoomReset}>
            <RotateCcw size={12} />
          </button>
          <button className="preview-toolbar-btn" onClick={handleZoomIn}>
            <ZoomIn size={14} />
          </button>
        </div>

        <div className="preview-toolbar-right">
          <div className="preview-format-toggle">
            <button
              className={`preview-format-btn${format === 'pdf' ? ' preview-format-btn--active' : ''}`}
              onClick={() => setFormat('pdf')}
            >
              PDF
            </button>
            <button
              className={`preview-format-btn${format === 'html' ? ' preview-format-btn--active' : ''}`}
              onClick={() => setFormat('html')}
            >
              HTML
            </button>
          </div>
          <button className="preview-toolbar-download" onClick={handleDownload} disabled={steps.length === 0}>
            <Download size={13} />
            Download
          </button>
        </div>
      </div>

      <div className="preview-scroll-area" ref={scrollRef}>
        <div
          className="preview-document"
          style={{
            transform: `scale(${zoom / 100})`,
            transformOrigin: 'top center',
          }}
        >
          {document && (
            <div className="preview-doc-header">
              <div className="preview-doc-type">WORK INSTRUCTION</div>
              <h1 className="preview-doc-title">{document.title}</h1>
              <div className="preview-doc-meta">
                {document.asset_id && (
                  <div className="preview-doc-meta-item">
                    <span className="preview-doc-meta-label">Asset ID</span>
                    <span className="preview-doc-meta-value">
                      {document.asset_id}
                    </span>
                  </div>
                )}
                {document.procedure_id && (
                  <div className="preview-doc-meta-item">
                    <span className="preview-doc-meta-label">Procedure</span>
                    <span className="preview-doc-meta-value">
                      {document.procedure_id}
                    </span>
                  </div>
                )}
                <div className="preview-doc-meta-item">
                  <span className="preview-doc-meta-label">Status</span>
                  <span className="preview-doc-meta-value preview-doc-status">
                    {document.status}
                  </span>
                </div>
                <div className="preview-doc-meta-item">
                  <span className="preview-doc-meta-label">Revision</span>
                  <span className="preview-doc-meta-value">1.0</span>
                </div>
              </div>
              <div className="preview-doc-divider" />
            </div>
          )}

          {steps.map((step) => {
            const isHighlighted = step.step_number === selectedStepNumber;
            const isRefined = step.step_id ? refinedStepIds?.has(step.step_id) : false;
            return (
              <div
                key={step.step_number}
                ref={(el) => setStepRef(step.step_number, el)}
                className={`preview-step${isHighlighted ? ' preview-step--highlighted' : ''}${step.interlock_status === 'blocked' ? ' preview-step--blocked' : ''}`}
              >
                {step.interlock_status === 'blocked' && (
                  <div className="preview-step-interlock-banner preview-step-interlock-banner--blocked">
                    ⛔ INTERLOCK BLOCKED — Resolve this prerequisite before proceeding
                  </div>
                )}

                <div className="preview-step-header">
                  <span className={`preview-step-number${step.interlock_status === 'blocked' ? ' preview-step-number--blocked' : ''}`}>
                    Step {step.step_number}
                  </span>
                  <span className="preview-step-title">{step.title}</span>
                  {isRefined && (
                    <span className="preview-step-refined-badge">✦ Refined</span>
                  )}
                </div>

                <p className="preview-step-text">{step.instruction_text}</p>

                {step.illustration_url && (
                  <img
                    src={step.illustration_url}
                    alt={step.title}
                    style={{ maxWidth: '100%', height: 'auto', margin: '10px 0', borderRadius: 4 }}
                  />
                )}

                {step.tools_required.length > 0 && (
                  <div className="preview-step-tools">
                    <span className="preview-step-tools-label">Tools: </span>
                    {step.tools_required.join(', ')}
                  </div>
                )}

                {step.quality_checks.length > 0 && (
                  <div className="preview-step-checks">
                    <span className="preview-step-checks-label">
                      Quality Checks
                    </span>
                    <ul className="preview-step-checks-list">
                      {step.quality_checks.map((check, i) => (
                        <li key={i}>{check}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {step.safety_warnings.length > 0 && (
                  <div className="preview-step-warnings">
                    <div className="preview-step-warning-header">
                      <AlertTriangle size={13} />
                      SAFETY WARNING
                    </div>
                    {step.safety_warnings.map((warning, i) => (
                      <p key={i} className="preview-step-warning-text">
                        {warning}
                      </p>
                    ))}
                  </div>
                )}

                {step.source_citations.length > 0 && (
                  <div className="preview-step-sources">
                    {step.source_citations.map((source, i) => (
                      <span key={i} className="preview-step-source">
                        [{i + 1}] {source}
                      </span>
                    ))}
                  </div>
                )}

                <div className="preview-step-divider" />
              </div>
            );
          })}

          {steps.length === 0 && !document && (
            <div className="preview-empty">
              <FileText size={32} />
              <span>No document loaded</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PreviewPane;
