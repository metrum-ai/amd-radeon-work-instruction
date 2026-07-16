// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useEffect, useCallback, type ReactNode } from 'react';
import { X } from 'lucide-react';
import './PreviewModal.css';

interface PreviewModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

function PreviewModal({ open, onClose, title = 'DOCUMENT PREVIEW', children }: PreviewModalProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="preview-modal" onClick={onClose}>
      <div className="preview-modal__container" onClick={e => e.stopPropagation()}>
        <div className="preview-modal__top-bar">
          <span className="preview-modal__title">{title}</span>
          <button className="preview-modal__close" onClick={onClose} title="Close (Esc)">
            <X size={16} />
          </button>
        </div>
        <div className="preview-modal__body">
          {children}
        </div>
      </div>
    </div>
  );
}

export default PreviewModal;
