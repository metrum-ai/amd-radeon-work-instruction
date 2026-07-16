# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""In-process illustration throughput tracking for Flux/Lemonade workloads.

Concurrency model: the module-level counters below (``_instances``,
``_lb_in_flight``) are deliberately plain globals. They are only mutated from
the API's single asyncio event loop, and every mutation is synchronous with no
``await`` in between, so it is atomic with respect to other coroutines. This is
NOT thread-safe — do not call these from a thread pool without adding a lock.
"""

import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

_WINDOW_SEC = 60.0
_DNS_TTL_SEC = 30.0

# Cache of hostname → (resolved IP or None, expiry). Bounds the blocking
# gethostbyname() call to at most once per host per TTL instead of once per
# illustration, keeping it off the hot path of the event loop.
_dns_cache: dict[str, tuple[Optional[str], float]] = {}


def _resolve_cached(name: str) -> Optional[str]:
    """Resolve a hostname to an IP with a short TTL cache; None if unresolvable."""
    now = time.time()
    cached = _dns_cache.get(name)
    if cached is not None and cached[1] > now:
        return cached[0]
    try:
        ip: Optional[str] = socket.gethostbyname(name)
    except OSError:
        ip = None
    _dns_cache[name] = (ip, now + _DNS_TTL_SEC)
    return ip


@dataclass
class _InstanceState:
    completions: deque[float] = field(default_factory=lambda: deque(maxlen=200))


_instances = {
    "lemonade-1": _InstanceState(),
    "lemonade-2": _InstanceState(),
}
_lb_in_flight = 0


def instance_from_base_url(base_url: str) -> Optional[str]:
    """Map a Lemonade base URL to a tracked instance id."""
    host = (urlparse(base_url).hostname or "").lower()
    if host == "lemonade-1":
        return "lemonade-1"
    if host == "lemonade-2":
        return "lemonade-2"
    return None


def instance_from_upstream_addr(upstream_addr: Optional[str]) -> Optional[str]:
    """Resolve nginx's $upstream_addr (e.g. "172.18.1.14:13305") to a tracked instance id.

    This is ground truth — it comes straight from the X-Upstream-Addr response header
    the Lemonade LB sets on every request (config/nginx.conf) — rather than guessing
    which backend handled a request after the fact from an unrelated metric.
    """
    if not upstream_addr:
        return None
    ip = upstream_addr.split(":", 1)[0].strip()
    for name in ("lemonade-1", "lemonade-2"):
        if _resolve_cached(name) == ip:
            return name
    return None


def record_illustration_start(base_url: str) -> None:
    """Mark an in-flight illustration routed through the Lemonade LB."""
    global _lb_in_flight
    if instance_from_base_url(base_url) is None:
        _lb_in_flight += 1


def record_illustration_complete(
    base_url: str,
    attributed_instance: Optional[str] = None,
) -> None:
    """Record a finished illustration for throughput calculations."""
    global _lb_in_flight
    via_lb = instance_from_base_url(base_url) is None
    instance = attributed_instance or instance_from_base_url(base_url)
    if not instance or instance not in _instances:
        return

    if via_lb:
        _lb_in_flight = max(0, _lb_in_flight - 1)
    state = _instances[instance]
    state.completions.append(time.time())


def record_illustration_failed(base_url: str) -> None:
    """Drop in-flight count when generation fails."""
    global _lb_in_flight
    if instance_from_base_url(base_url) is None:
        _lb_in_flight = max(0, _lb_in_flight - 1)


def lb_in_flight() -> int:
    """Return in-flight illustration count routed through the Lemonade LB."""
    return _lb_in_flight


def images_per_minute(instance: str) -> Optional[float]:
    """Return a rolling img/min rate from completed illustrations only."""
    if instance not in _instances:
        return None

    now = time.time()
    state = _instances[instance]
    recent = [ts for ts in state.completions if now - ts <= _WINDOW_SEC]
    if not recent:
        return None

    return round(len(recent) * (60.0 / _WINDOW_SEC), 1)
