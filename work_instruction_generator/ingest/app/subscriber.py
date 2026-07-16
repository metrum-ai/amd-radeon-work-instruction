# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Subscriber for ingest application."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from mqtt_spb_wrapper.spb_base import SpbPayloadParser

logger = logging.getLogger(__name__)

_TOPIC = "spBv1.0/ManufacturingFloor/#"
_MACHINE_DEVICE_IDS = {"zyro-welder", "veltrix-dispenser", "nexora-scanner"}
_STATION_DEVICE_ID = "station"


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float, returning default on non-numeric/missing input.

    Guards the snapshot build so one malformed MQTT metric can't raise inside
    the locked snapshot and take down /snapshot and the SSE stream.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_topic(topic_str: str) -> tuple[str, str]:
    """Return (msg_type, device_id) from a Sparkplug B topic string."""
    parts = topic_str.split("/")
    msg_type = parts[2] if len(parts) > 2 else ""
    device_id = (
        parts[4] if len(parts) > 4 else parts[3] if len(parts) > 3 else ""
    )
    return msg_type, device_id


class SparkplugSubscriber:
    """Subscribe to Sparkplug B messages via paho-mqtt and maintain in-memory snapshot."""

    def __init__(
        self, mqtt_host: str = "mosquitto", mqtt_port: int = 1883
    ) -> None:
        """Initialize the Sparkplug subscriber."""
        self._host = mqtt_host
        self._port = mqtt_port
        self._lock = threading.Lock()
        self._parser = SpbPayloadParser()

        self._machine_attrs: dict[str, dict[str, Any]] = {}
        self._machine_data: dict[str, dict[str, Any]] = {}
        self._station_data: dict[str, Any] = {}

        self._client = mqtt.Client(
            client_id="backend-subscriber", protocol=mqtt.MQTTv311
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def connect(self) -> None:
        """Connect to the Sparkplug subscriber."""
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        logger.info(
            "SparkplugSubscriber connecting to %s:%s", self._host, self._port
        )

    def disconnect(self) -> None:
        """Disconnect from the Sparkplug subscriber."""
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as exc:
            logger.debug("SparkplugSubscriber disconnect error ignored: %s", exc)
        logger.info("SparkplugSubscriber disconnected")

    def _on_connect(
        self, client: mqtt.Client, userdata: Any, flags: Any, rc: int
    ) -> None:
        """On connect callback."""
        if rc == 0:
            client.subscribe(_TOPIC, qos=0)
            logger.info("SparkplugSubscriber subscribed to %s", _TOPIC)
        else:
            logger.warning("SparkplugSubscriber connect failed rc=%d", rc)

    def _on_message(
        self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        """On message callback."""
        msg_type, device_id = _parse_topic(msg.topic)
        if not device_id:
            return

        parsed = self._parser.parse_payload(msg.payload)
        if not parsed or "metrics" not in parsed:
            return

        # mqtt-spb-wrapper prefixes metric names with "ATTR/" or "DATA/" — strip them.
        attrs: dict[str, Any] = {}
        data: dict[str, Any] = {}
        for m in parsed["metrics"]:
            name: str = m.get("name", "")
            value = m.get("value")
            if value is None:
                continue
            if name.startswith("ATTR/"):
                attrs[name[5:]] = value
            elif name.startswith("DATA/"):
                data[name[5:]] = value
            else:
                data[name] = value  # unqualified metric → treat as data

        with self._lock:
            if device_id in _MACHINE_DEVICE_IDS:
                if msg_type == "DBIRTH":
                    self._machine_attrs.setdefault(device_id, {}).update(attrs)
                    self._machine_data.setdefault(device_id, {}).update(data)
                elif msg_type == "DDATA":
                    self._machine_data.setdefault(device_id, {}).update(data)
                elif msg_type == "DDEATH":
                    self._machine_data.setdefault(device_id, {})[
                        "status"
                    ] = "offline"

            elif device_id == _STATION_DEVICE_ID:
                if msg_type == "DBIRTH":
                    self._station_data.update(attrs)
                    self._station_data.update(data)
                elif msg_type == "DDATA":
                    self._station_data.update(data)

    def get_snapshot(self) -> dict[str, Any]:
        """Get the snapshot."""
        with self._lock:
            machines = [
                self._build_floor_machine(did) for did in _MACHINE_DEVICE_IDS
            ]
            station_state = self._build_machine_state()

        return {
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "machines": machines,
            "station_state": station_state,
        }

    def _build_floor_machine(self, device_id: str) -> dict[str, Any]:
        """Build a floor machine."""
        attrs = self._machine_attrs.get(device_id, {})
        data = self._machine_data.get(device_id, {})

        gauges: list[dict[str, Any]] = []
        i = 0
        while True:
            key = attrs.get(f"gauge_{i}_key")
            if key is None:
                break
            gauges.append(
                {
                    "key": key,
                    "label": attrs.get(f"gauge_{i}_label", key),
                    "value": _safe_float(data.get(f"gauge_{i}"), 0.0),
                    "unit": attrs.get(f"gauge_{i}_unit", ""),
                    "max": _safe_float(attrs.get(f"gauge_{i}_max"), 100.0),
                }
            )
            i += 1

        readiness: dict[str, bool] = {
            k[len("readiness_") :]: bool(v)
            for k, v in data.items()
            if k.startswith("readiness_")
        }

        return {
            "id": device_id,
            "name": attrs.get("name", device_id),
            "vendor": attrs.get("vendor", ""),
            "origin": attrs.get("origin", ""),
            "type": attrs.get("type", ""),
            "status": str(data.get("status", "unknown")),
            "gauges": gauges,
            "readiness": readiness,
            "docs": [],
        }

    def _build_machine_state(self) -> dict[str, Any]:
        """Build a machine state."""
        data = self._station_data

        alarms_raw = data.get("alarms_json", "[]")
        try:
            active_alarms = (
                json.loads(alarms_raw) if isinstance(alarms_raw, str) else []
            )
        except (json.JSONDecodeError, TypeError):
            active_alarms = []

        readiness_flags: dict[str, bool] = {
            k[len("readiness_") :]: bool(v)
            for k, v in data.items()
            if k.startswith("readiness_")
        }

        quality_readings: dict[str, float] = {
            k[len("quality_") :]: _safe_float(v)
            for k, v in data.items()
            if k.startswith("quality_")
        }

        return {
            "state_id": None,
            "station_id": data.get("station_id", "station"),
            "procedure_id": data.get("procedure_id"),
            "source": "sparkplug_b",
            "state": str(data.get("state", "unknown")),
            "active_alarms": active_alarms,
            "readiness_flags": readiness_flags,
            "quality_readings": quality_readings,
            "last_completed_step": data.get("last_completed_step"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
