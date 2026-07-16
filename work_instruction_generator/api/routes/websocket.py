# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""WebSocket channels for WIG.

Implements the 4 channels from plan Section 11.3:
  - /ws/wig/{doc_id}/generation  — generation progress
  - /ws/wig/{doc_id}/chat        — refinement chat
  - /ws/wig/{doc_id}/preview     — live preview updates
  - /ws/wig/stations/{station_id}/state — live simulator/telemetry state

The API is a thin broadcast layer: clients connect and listen, server
publishes events from store mutations (e.g. a step or export being
added). This MVP does not push from external agents; integration with
NATS/RabbitMQ is a follow-up.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from work_instruction_generator.api.store import store

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionHub:
    """Per-channel pub/sub for WebSocket clients."""

    def __init__(self) -> None:
        """Initialize the connection hub."""
        self._lock = asyncio.Lock()
        self._channels: dict[str, set[WebSocket]] = {}

    async def connect(self, channel: str, ws: WebSocket) -> None:
        """Connect a client to a channel."""
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        """Disconnect a client from a channel."""
        async with self._lock:
            subs = self._channels.get(channel)
            if subs and ws in subs:
                subs.discard(ws)
            if subs is not None and not subs:
                self._channels.pop(channel, None)

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Publish a message to a channel."""
        async with self._lock:
            subs = list(self._channels.get(channel, ()))
        if not subs:
            return
        msg = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception as exc:
                logger.warning("WS publish failed for %s: %s", channel, exc)
                dead.append(ws)
        if dead:
            async with self._lock:
                ch = self._channels.get(channel)
                if ch is not None:
                    for ws in dead:
                        ch.discard(ws)


hub = ConnectionHub()


def _channel_name(prefix: str, key: str) -> str:
    """Generate a channel name."""
    return f"{prefix}:{key}"


@router.websocket("/ws/wig/{document_id}/generation")
async def ws_generation(ws: WebSocket, document_id: str) -> None:
    """WebSocket generation channel."""
    channel = _channel_name("generation", document_id)
    await hub.connect(channel, ws)
    try:
        # On connect, replay current job status
        job = await store.find_job_for_document(document_id)
        if job:
            await ws.send_text(
                json.dumps({"event": "status", **job}, default=str)
            )
        # Listen (drain inbound pings)
        while True:
            data = await ws.receive_text()
            if data.strip() == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(channel, ws)


@router.websocket("/ws/wig/{document_id}/chat")
async def ws_chat(ws: WebSocket, document_id: str) -> None:
    """WebSocket chat channel."""
    channel = _channel_name("chat", document_id)
    await hub.connect(channel, ws)
    try:
        # Replay recent messages
        for msg in (await store.list_chat(document_id))[-20:]:
            await ws.send_text(
                json.dumps({"event": "message", **msg}, default=str)
            )
        while True:
            await ws.receive_text()  # keep-alive; echo only
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(channel, ws)


@router.websocket("/ws/wig/{document_id}/preview")
async def ws_preview(ws: WebSocket, document_id: str) -> None:
    """WebSocket preview channel."""
    channel = _channel_name("preview", document_id)
    await hub.connect(channel, ws)
    try:
        # Initial preview snapshot
        for step in await store.list_steps(document_id):
            ill = await store.get_illustration_by_step(step["step_id"])
            await ws.send_text(
                json.dumps(
                    {
                        "event": "step_update",
                        "step_number": step["step_number"],
                        "content": step.get("instruction_text"),
                        "illustration_url": (
                            ill.get("artifact_ref") if ill else None
                        ),
                    },
                    default=str,
                )
            )
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(channel, ws)


@router.websocket("/ws/wig/stations/{station_id}/state")
async def ws_station_state(ws: WebSocket, station_id: str) -> None:
    """WebSocket station state channel."""
    channel = _channel_name("station", station_id)
    await hub.connect(channel, ws)
    try:
        ms = await store.get_machine_state(station_id)
        if ms:
            await ws.send_text(
                json.dumps({"event": "state_change", **ms}, default=str)
            )
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(channel, ws)
