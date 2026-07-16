// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { Download, Globe } from 'lucide-react';
import './ExportBar.css';

interface ExportBarProps {
  format: string;
  language: string;
  onFormatChange: (f: string) => void;
  onLanguageChange: (l: string) => void;
  onExport: () => void;
  onPublish: () => void;
  documentStatus: string;
}

const FORMATS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
  { value: 'json', label: 'JSON' },
];

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'de', label: 'German' },
  { value: 'ja', label: 'Japanese' },
  { value: 'zh', label: 'Chinese' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'ko', label: 'Korean' },
];

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  generating: 'Generating',
  generated: 'Generated',
};

function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] || status;
  return (
    <span className={`export-bar-status export-bar-status--${status}`}>
      {label}
    </span>
  );
}

function ExportBar({
  format,
  language,
  onFormatChange,
  onLanguageChange,
  onExport,
  onPublish,
  documentStatus,
}: ExportBarProps) {
  return (
    <div className="export-bar">
      <div className="export-bar-left">
        <div className="export-bar-group">
          <span className="export-bar-label">Format:</span>
          <select
            className="export-bar-select"
            value={format}
            onChange={(e) => onFormatChange(e.target.value)}
          >
            {FORMATS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>

        <div className="export-bar-group">
          <span className="export-bar-label">Language:</span>
          <select
            className="export-bar-select"
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
          >
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="export-bar-right">
        <StatusBadge status={documentStatus} />
        <button className="export-bar-export-btn" onClick={onExport}>
          <Download size={12} />
          Export
        </button>
        <button className="export-bar-publish-btn" onClick={onPublish}>
          <Globe size={12} />
          Publish
          <span className="export-bar-publish-dot" />
        </button>
      </div>
    </div>
  );
}

export default ExportBar;
