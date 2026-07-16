// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useEffect, useCallback } from 'react';
import { Eye, FileText } from 'lucide-react';
import type { AvailableDoc } from '../../types';
import './DocumentsPopup.css';

interface DocumentsPopupProps {
  open: boolean;
  loading?: boolean;
  documents: AvailableDoc[];
  onClose: () => void;
  onPreview: (doc: AvailableDoc) => void;
}

const CAT_LABELS: Record<string, string> = {
  sop: 'SOP',
  procedure: 'Procedure Doc',
};

function DocumentsPopup({ open, loading = false, documents, onClose, onPreview }: DocumentsPopupProps) {
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

  return (
    <div className="dp-backdrop" onClick={onClose}>
      <div className="dp" onClick={e => e.stopPropagation()}>
        <div className="dp__header">
          <span className="dp__title">All Documents</span>
          <span className="dp__count">{documents.length}</span>
        </div>
        <div className="dp__list">
          {loading
            ? [0, 1, 2, 3].map(i => <div key={i} className="dp-item dp-item--skeleton" />)
            : documents.length === 0
              ? <div className="dp-empty">No documents found.</div>
              : documents.map(doc => (
                  <div key={doc.id} className="dp-item" onClick={() => onPreview(doc)}>
                    <div className="dp-item__left">
                      <FileText size={12} className="dp-item__file-icon" />
                      <div className="dp-item__info">
                        <span className="dp-item__title">{doc.title}</span>
                        <span className="dp-item__meta">
                          <span className="dp-item__cat">{CAT_LABELS[doc.category] ?? doc.category}</span>
                          {doc.vendor && (
                            <>
                              <span className="dp-item__dot" />
                              {doc.vendor}
                            </>
                          )}
                          <span className="dp-item__dot" />
                          {doc.version}
                        </span>
                      </div>
                    </div>
                    <Eye size={13} className="dp-item__icon" />
                  </div>
                ))
          }
        </div>
      </div>
    </div>
  );
}

export default DocumentsPopup;
