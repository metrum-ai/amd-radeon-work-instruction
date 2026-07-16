# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Live GPU workload metrics for the WIG dashboard."""

import asyncio
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from work_instruction_generator.api import prometheus_client, workload_metrics

router = APIRouter(prefix="/api/v1/wig", tags=["metrics"])


class GpuWorkloadValues(BaseModel):
    """GPU workload values."""
    gpu_id: str
    compute_pct: Optional[float] = None
    metric_value: Optional[float] = None


class GpuWorkloadsResponse(BaseModel):
    """GPU workloads response."""
    rows: List[GpuWorkloadValues]


_COMPUTE_QUERIES: Dict[str, str] = {
    "0": 'avg_over_time(gpu_gfx_activity{gpu_id="0"}[10s])',
    "1": 'avg_over_time(gpu_gfx_activity{gpu_id="1"}[10s])',
    "2": 'avg_over_time(gpu_gfx_activity{gpu_id="2"}[10s])',
    "3": 'avg_over_time(gpu_gfx_activity{gpu_id="3"}[10s])',
}

_PROM_METRIC_QUERIES: Dict[str, str] = {
    "0": 'sum(rate(vllm:generation_tokens_total{job="vllm-qwen-vlm"}[30s]))',
    "1": 'sum(rate(vllm:generation_tokens_total{job="vllm-gemma"}[30s]))',
}


@router.get("/metrics/gpu-workloads", response_model=GpuWorkloadsResponse)
async def get_gpu_workloads() -> GpuWorkloadsResponse:
    """Return live compute and throughput values for all GPU workload rows."""
    gpu_ids = list(_COMPUTE_QUERIES.keys())
    prom_metric_ids = [g for g in gpu_ids if g in _PROM_METRIC_QUERIES]

    # Issue every Prometheus query in a single concurrent wave instead of
    # serially (was up to ~6×3s on a slow backend). Order is preserved by
    # slicing the results back out in the same order they were scheduled.
    results = await asyncio.gather(
        *(prometheus_client.query_scalar(_COMPUTE_QUERIES[g]) for g in gpu_ids),
        *(
            prometheus_client.query_scalar(_PROM_METRIC_QUERIES[g], mode="sum")
            for g in prom_metric_ids
        ),
    )
    compute_results = results[: len(gpu_ids)]
    prom_metric_map = dict(zip(prom_metric_ids, results[len(gpu_ids):]))

    rows: List[GpuWorkloadValues] = []
    for gpu_id, compute_pct in zip(gpu_ids, compute_results):
        metric_value: Optional[float] = None
        if gpu_id in prom_metric_map:
            metric_value = prom_metric_map[gpu_id]
        elif gpu_id == "2":
            metric_value = workload_metrics.images_per_minute("lemonade-1")
        elif gpu_id == "3":
            metric_value = workload_metrics.images_per_minute("lemonade-2")

        rows.append(
            GpuWorkloadValues(
                gpu_id=gpu_id,
                compute_pct=compute_pct,
                metric_value=metric_value,
            ),
        )

    return GpuWorkloadsResponse(rows=rows)
