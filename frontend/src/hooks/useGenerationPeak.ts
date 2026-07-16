// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef, useState } from 'react';

function maxNullable(current: number | null, next: number | null): number | null {
  if (next === null) {
    return current;
  }
  if (current === null) {
    return next;
  }
  return Math.max(current, next);
}

export interface GenerationPeakDisplay {
  displayMetric: number | null;
  showingHeldPeak: boolean;
  trackingLive: boolean;
}

export function useGenerationPeak(
  isGenerating: boolean,
  liveMetric: number | null,
): GenerationPeakDisplay {
  const [heldPeak, setHeldPeak] = useState<number | null>(null);
  const [sessionPeak, setSessionPeak] = useState<number | null>(null);
  const sessionPeakRef = useRef<number | null>(null);
  const wasGeneratingRef = useRef(false);

  useEffect(() => {
    const started = isGenerating && !wasGeneratingRef.current;
    const finished = !isGenerating && wasGeneratingRef.current;

    if (started) {
      sessionPeakRef.current = null;
      setSessionPeak(null);
      setHeldPeak(null);
    }

    if (finished) {
      setHeldPeak(sessionPeakRef.current);
    }

    wasGeneratingRef.current = isGenerating;
  }, [isGenerating]);

  useEffect(() => {
    if (!isGenerating) {
      return;
    }

    const next = maxNullable(sessionPeakRef.current, liveMetric);
    sessionPeakRef.current = next;
    setSessionPeak(next);
  }, [isGenerating, liveMetric]);

  const showingHeldPeak = !isGenerating && heldPeak !== null;
  const trackingLive = isGenerating;

  const displayMetric = isGenerating
    ? sessionPeak ?? liveMetric
    : heldPeak ?? liveMetric;

  return {
    displayMetric,
    showingHeldPeak,
    trackingLive,
  };
}
