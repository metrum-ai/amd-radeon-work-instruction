// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useEffect, useCallback } from 'react';
import { Eye } from 'lucide-react';
import type { HistoryReport } from '../../types';
import './HistoryDrawer.css';

interface HistoryDrawerProps {
  open: boolean;
  loading?: boolean;
  reports: HistoryReport[];
  onClose: () => void;
  onPreview: (report: HistoryReport) => void;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function HistoryDrawer({ open, loading = false, reports, onClose, onPreview }: HistoryDrawerProps) {
  const handleKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKey);
      return () => document.removeEventListener('keydown', handleKey);
    }
  }, [open, handleKey]);

  if (!open) return null;

  const recent = reports.slice(0, 5);

  return (
    <div className="hp-backdrop" onClick={onClose}>
      <div className="hp" onClick={e => e.stopPropagation()}>
        <div className="hp__header">
          <span className="hp__title">Recent Reports</span>
        </div>
        {loading
          ? [0, 1, 2].map(i => <div key={i} className="hp-item hp-item--skeleton" />)
          : recent.length === 0
            ? <div className="hp-empty">No generated documents yet.</div>
            : recent.map(report => (
                <div key={report.id} className="hp-item" onClick={() => onPreview(report)}>
                  <div className="hp-item__left">
                    <span className="hp-item__title">{report.title}</span>
                    <span className="hp-item__meta">
                      {report.procedure}
                      <span className="hp-item__dot" />
                      {report.stepCount} steps
                      <span className="hp-item__dot" />
                      {formatDate(report.generatedAt)}, {formatTime(report.generatedAt)}
                    </span>
                  </div>
                  <Eye size={13} className="hp-item__icon" />
                </div>
              ))
        }
      </div>
    </div>
  );
}

export default HistoryDrawer;
