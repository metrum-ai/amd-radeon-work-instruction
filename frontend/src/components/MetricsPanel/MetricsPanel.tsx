// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useCallback, useMemo } from "react";
import gpuImg from "../../../assets/AMDRadeonAIPROR9700S.webp";
import MetricGraph from "../MetricGraph/MetricGraph";
import { usePrometheusQuery, QUERIES, MB_TO_GB } from "../../hooks/usePrometheusQuery";
import { useGpuWorkloads } from "../../hooks/useGpuWorkloads";
import GpuWorkloadRow from "./GpuWorkloadRow";
import { GPU_WORKLOAD_ROWS } from "./gpuWorkloadConfig";
import "./MetricsPanel.css";

const SPECS = [
  { key: "Ray Accel", val: "64" },
  { key: "AI Accel", val: "128" },
  { key: "CUs",       val: "64" },
  { key: "VRAM",      val: "32 GB" },
] as const;

interface MetricsPanelProps {
  open: boolean;
  onToggle: () => void;
  isGenerating?: boolean;
}

export default function MetricsPanel({
  open,
  onToggle,
  isGenerating = false,
}: MetricsPanelProps) {
  // Only poll while the panel is open — collapsed, all these stay idle.
  const gpuWorkloads = useGpuWorkloads(open);
  const gpuCompute   = usePrometheusQuery(QUERIES.gpuCompute, { enabled: open });
  const gpuMemory    = usePrometheusQuery(QUERIES.gpuMemory, { transform: MB_TO_GB, enabled: open });
  const gpuTemp      = usePrometheusQuery(QUERIES.gpuTemp, { enabled: open });
  const gpuPower     = usePrometheusQuery(QUERIES.gpuPower, { enabled: open });
  const cpuUtil      = usePrometheusQuery(QUERIES.cpuUtil, { enabled: open });
  const sysMem       = usePrometheusQuery(QUERIES.sysMem, { enabled: open });

  const allQueries = useMemo(
    () => [gpuCompute, gpuMemory, gpuTemp, gpuPower, cpuUtil, sysMem],
    [gpuCompute, gpuMemory, gpuTemp, gpuPower, cpuUtil, sysMem],
  );
  const anyConnected = allQueries.some((q) => q.connected === true)
    || gpuWorkloads.connected === true;
  const allChecked = allQueries.every((q) => q.connected !== null)
    && gpuWorkloads.connected !== null;

  const handleToggle = useCallback(() => onToggle(), [onToggle]);

  return (
    <div className={"metrics-panel" + (open ? "" : " metrics-panel--collapsed")}>
      {!open && (
        <div className="metrics-panel__collapsed-inner" onClick={handleToggle}>
          <span className="metrics-panel__collapsed-label">
            AMD Radeon&#8482; AI PRO R9700S
          </span>
          <span className="metrics-panel__collapsed-chevron">&#8249;</span>
        </div>
      )}

      {open && (
        <>
          <div className="metrics-panel__header">
            <div className="metrics-panel__close-btn" onClick={handleToggle}>&#8250;</div>
          </div>

          <div className="metrics-hero-showcase">
            <div className="metrics-hero-img">
              <img src={gpuImg} alt="AMD Radeon AI PRO R9700S" loading="eager" />
            </div>
            <div className="metrics-hero-identity">
              <h2 className="metrics-hero-name">AMD Radeon&#8482; AI PRO R9700S</h2>
            </div>
            <div className="spec-strip">
              {SPECS.map((s) => (
                <div key={s.key} className="spec-pill">
                  <span className="spec-pill__val">{s.val}</span>
                  <span className="spec-pill__key">{s.key}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="gpu-workload-list">
            <div className="metrics-section-heading">GPU Workloads</div>
            <div className="gpu-workload-grid">
              {GPU_WORKLOAD_ROWS.map((row) => (
                <GpuWorkloadRow
                  key={row.gpuId}
                  config={row}
                  isGenerating={isGenerating}
                  metricValue={gpuWorkloads.values[row.gpuId]?.metric_value ?? null}
                />
              ))}
            </div>
          </div>

          <div className="metrics-graphs">
            {allChecked && !anyConnected && (
              <div className="metrics-offline-banner">
                <span className="metrics-offline-banner__title">Prometheus not reachable</span>
                <span className="metrics-offline-banner__sub">expecting metrics at /prometheus</span>
              </div>
            )}

            <div className="metrics-section-heading">GPU</div>
            <MetricGraph label="GPU Compute"     series={gpuCompute.series} timestamps={gpuCompute.timestamps} unit="%" color="#ED1C24" maxVal={100} />
            <MetricGraph label="GPU Memory"      series={gpuMemory.series}  timestamps={gpuMemory.timestamps}  unit="GB" color="#FACC15" maxVal={32} />
            <MetricGraph label="GPU Temperature" series={gpuTemp.series}    timestamps={gpuTemp.timestamps}    unit="°C" color="#22C55E" />
            <MetricGraph label="GPU Power"       series={gpuPower.series}   timestamps={gpuPower.timestamps}   unit="W"  color="#F26522" />

            <div className="metrics-section-heading">System</div>
            <MetricGraph label="CPU Utilization" series={cpuUtil.series} timestamps={cpuUtil.timestamps} unit="%" color="#EC4899" maxVal={100} />
            <MetricGraph label="System Memory"   series={sysMem.series}  timestamps={sysMem.timestamps}  unit="GB" color="#A855F7" />
          </div>

          <div className="metrics-panel__footer">
            <span className={"metrics-live-dot" + (anyConnected ? " metrics-live-dot--on" : "")} />
            <span className={"metrics-live-label" + (anyConnected ? " metrics-live-label--on" : "")}>
              {anyConnected ? "Live" : "Offline"}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
