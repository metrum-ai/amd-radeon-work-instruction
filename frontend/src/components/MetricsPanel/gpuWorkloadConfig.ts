// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

export type GpuMetricKind = 'throughput' | 'images_generated' | 'images_analyzed';

export interface GpuWorkloadRowConfig {
  gpuId: string;
  title: string;
  model: string;
  subtitle: string;
  metricKind: GpuMetricKind;
  metricLabel: string;
  metricUnit: string;
}

export const GPU_WORKLOAD_ROWS: GpuWorkloadRowConfig[] = [
  {
    gpuId: '0',
    title: 'GPU 0',
    model: 'Qwen3.5-9B',
    subtitle: 'VLM / Translation',
    metricKind: 'throughput',
    metricLabel: 'Throughput',
    metricUnit: 'tok/s',
  },
  {
    gpuId: '1',
    title: 'GPU 1',
    model: 'Gemma-4-E2B-it (x2)',
    subtitle: 'Instruction LLM x 2',
    metricKind: 'throughput',
    metricLabel: 'Throughput',
    metricUnit: 'tok/s',
  },
  {
    gpuId: '2',
    title: 'GPU 2',
    model: 'Flux-2-Klein-4B',
    subtitle: 'Lemonade instance 1',
    metricKind: 'images_generated',
    metricLabel: 'Images generated',
    metricUnit: 'img/m',
  },
  {
    gpuId: '3',
    title: 'GPU 3',
    model: 'Flux-2-Klein-4B',
    subtitle: 'Lemonade instance 2',
    metricKind: 'images_generated',
    metricLabel: 'Images generated',
    metricUnit: 'img/m',
  },
];
