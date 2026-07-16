// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { History, FolderOpen } from 'lucide-react';
import amdLogo from '../../../assets/AMD_WhiteLogo_DarkTheme.png';
import './TopBar.css';

interface TopBarProps {
  onHistoryClick?: () => void;
  onDocumentsClick?: () => void;
}

function TopBar({ onHistoryClick, onDocumentsClick }: TopBarProps) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-logo">
          <img src={amdLogo} alt="AMD" className="topbar-logo-img" />
        </div>
        <div className="topbar-divider" />
        <div className="topbar-title-block">
          <span className="topbar-title">WORK INSTRUCTION GENERATOR</span>
          <span className="topbar-subtitle">AMD RADEON AI PRO - OPENCLAW DYNAMIC PIPELINE</span>
        </div>
      </div>
      <div className="topbar-right">
        {onDocumentsClick && (
          <button className="topbar-history-btn" onClick={onDocumentsClick}>
            <FolderOpen size={14} />
            Documents
          </button>
        )}
        {onHistoryClick && (
          <button className="topbar-history-btn" onClick={onHistoryClick}>
            <History size={14} />
            History
          </button>
        )}
      </div>
    </header>
  );
}

export default TopBar;
