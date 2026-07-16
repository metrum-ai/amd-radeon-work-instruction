// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useGenerationPeak } from '../../hooks/useGenerationPeak';
import type { GpuWorkloadRowConfig } from './gpuWorkloadConfig';

interface GpuWorkloadRowProps {
  config: GpuWorkloadRowConfig;
  isGenerating: boolean;
  metricValue: number | null;
}

function formatMetric(value: number | null): string {
  if (value === null) {
    return '—';
  }
  if (value >= 100) {
    return Math.round(value).toString();
  }
  return value.toFixed(1);
}

export default function GpuWorkloadRow({
  config,
  isGenerating,
  metricValue: liveMetric,
}: GpuWorkloadRowProps) {
  const peak = useGenerationPeak(isGenerating, liveMetric);

  return (
    <div className="gpu-workload-row">
      <span className="gpu-workload-row__title">{config.title}</span>
      <span className="gpu-workload-row__model">{config.model}</span>

      <div className="gpu-workload-row__metric">
        {(peak.showingHeldPeak || peak.trackingLive) && (
          <span
            className={
              'gpu-workload-row__peak-tag'
              + (peak.trackingLive ? ' gpu-workload-row__peak-tag--live' : '')
            }
          >
            {peak.showingHeldPeak ? 'last generated max' : 'tracking'}
          </span>
        )}
        <div className="gpu-workload-row__metric-value-row">
          <span className="gpu-workload-row__metric-value">
            {formatMetric(peak.displayMetric)}
          </span>
          <span className="gpu-workload-row__metric-unit">{config.metricUnit}</span>
        </div>
      </div>
    </div>
  );
}
