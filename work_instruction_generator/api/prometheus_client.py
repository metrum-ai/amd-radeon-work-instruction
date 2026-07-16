# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Thin async client for Prometheus instant queries."""

import logging
import os
from typing import Literal, Optional

import httpx

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    "http://wig_prometheus:9090",
)


async def query_scalar(
    promql: str,
    mode: Literal["first", "sum"] = "first",
) -> Optional[float]:
    """Run an instant query and return a single numeric value.

    Args:
        promql: Prometheus expression.
        mode: Use the first series value or sum all series.

    Returns:
        Rounded scalar, or None when Prometheus is unreachable or empty.
    """
    url = f"{PROMETHEUS_URL}/api/v1/query"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url, params={"query": promql})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.debug("Prometheus query failed (%s): %s", promql, exc)
        return None

    if payload.get("status") != "success":
        return None

    result = payload.get("data", {}).get("result", [])
    if not result:
        return None

    values = []
    for row in result:
        try:
            values.append(float(row["value"][1]))
        except (KeyError, TypeError, ValueError):
            continue

    if not values:
        return None

    raw = sum(values) if mode == "sum" else values[0]
    return round(raw * 10) / 10
