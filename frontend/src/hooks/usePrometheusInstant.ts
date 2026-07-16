// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useCallback, useEffect, useRef, useState } from 'react';

const PROM_BASE = '/prometheus';
const POLL_INTERVAL = 2000;

export interface InstantQueryResult {
  value: number | null;
  connected: boolean | null;
}

function parseInstantValue(
  result: Array<{ metric: Record<string, string>; value: [number, string] }>,
  mode: 'first' | 'sum',
): number | null {
  if (!result.length) {
    return null;
  }

  const values = result
    .map((row) => parseFloat(row.value[1]))
    .filter((value) => !Number.isNaN(value));

  if (!values.length) {
    return null;
  }

  const raw = mode === 'sum'
    ? values.reduce((total, value) => total + value, 0)
    : values[0];

  return Math.round(raw * 10) / 10;
}

export function usePrometheusInstant(
  query: string,
  mode: 'first' | 'sum' = 'first',
  interval = POLL_INTERVAL,
): InstantQueryResult {
  const [value, setValue] = useState<number | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);

  const queryRef = useRef(query);
  queryRef.current = query;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const connectedRef = useRef(connected);
  connectedRef.current = connected;

  const poll = useCallback(async () => {
    try {
      const url = `${PROM_BASE}/api/v1/query?query=${encodeURIComponent(queryRef.current)}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(response.statusText);
      }

      const json = await response.json();
      if (json.status === 'success' && json.data?.result?.length > 0) {
        setConnected(true);
        setValue(parseInstantValue(json.data.result, modeRef.current));
        return;
      }

      setConnected(true);
      setValue(null);
    } catch {
      if (connectedRef.current === null) {
        setConnected(false);
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    const wrappedPoll = () => {
      if (active) {
        poll();
      }
    };
    wrappedPoll();
    const id = setInterval(wrappedPoll, interval);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [poll, interval]);

  return { value, connected };
}
