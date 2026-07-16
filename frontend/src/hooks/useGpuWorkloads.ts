// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useCallback, useEffect, useRef, useState } from 'react';

const POLL_INTERVAL = 2000;

export interface GpuWorkloadValues {
  gpu_id: string;
  compute_pct: number | null;
  metric_value: number | null;
}

export interface GpuWorkloadsState {
  values: Record<string, GpuWorkloadValues>;
  connected: boolean | null;
}

const EMPTY_VALUES: Record<string, GpuWorkloadValues> = {};

export function useGpuWorkloads(enabled = true): GpuWorkloadsState {
  const [values, setValues] = useState<Record<string, GpuWorkloadValues>>(
    EMPTY_VALUES,
  );
  const [connected, setConnected] = useState<boolean | null>(null);
  const connectedRef = useRef(connected);
  connectedRef.current = connected;

  const poll = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/wig/metrics/gpu-workloads');
      if (!response.ok) {
        throw new Error(response.statusText);
      }

      const json = await response.json() as {
        rows: GpuWorkloadValues[];
      };

      const next: Record<string, GpuWorkloadValues> = {};
      for (const row of json.rows) {
        next[row.gpu_id] = row;
      }

      setConnected(true);
      setValues(next);
    } catch {
      if (connectedRef.current === null) {
        setConnected(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const wrappedPoll = () => {
      if (active) {
        poll();
      }
    };
    wrappedPoll();
    const id = window.setInterval(wrappedPoll, POLL_INTERVAL);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [poll, enabled]);

  return { values, connected };
}
