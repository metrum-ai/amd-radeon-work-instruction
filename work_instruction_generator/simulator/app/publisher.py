# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Sparkplug publisher for the machine simulator."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

from mqtt_spb_wrapper import MqttSpbEntityDevice, MqttSpbEntityEdgeNode

if TYPE_CHECKING:
    from .simulator import MachineSimulator

logger = logging.getLogger(__name__)

_GROUP = "ManufacturingFloor"
_EDGE_NODE = "Simulator"
_PUBLISH_INTERVAL = 2.0


class SparkplugPublisher:
    """Publishes simulator snapshots to an MQTT Sparkplug B broker."""

    def __init__(
        self,
        broker_host: str = "mosquitto",
        broker_port: int = 1883,
        simulator: MachineSimulator | None = None,
    ) -> None:
        """Initialize the Sparkplug publisher."""
        self._host = broker_host
        self._port = broker_port
        self._simulator = simulator
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the Sparkplug publisher."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="sparkplug-publisher"
        )
        self._thread.start()
        logger.info(
            "SparkplugPublisher started (broker=%s:%d)", self._host, self._port
        )

    def stop(self) -> None:
        """Stop the Sparkplug publisher."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("SparkplugPublisher stopped")

    # ------------------------------------------------------------------

    def _make_machine_device(self, machine: dict) -> MqttSpbEntityDevice:
        """Make a machine device."""
        dev = MqttSpbEntityDevice(
            spb_group_name=_GROUP,
            spb_eon_name=_EDGE_NODE,
            spb_eon_device_name=machine["id"],
            retain_birth=True,
            debug=False,
        )
        # Static attributes (published in DBIRTH)
        dev.attributes.set_value("name", machine.get("name", ""))
        dev.attributes.set_value("vendor", machine.get("vendor", ""))
        dev.attributes.set_value("origin", machine.get("origin", ""))
        dev.attributes.set_value("type", machine.get("type", ""))
        dev.attributes.set_value(
            "serial_number", machine.get("serial_number", "")
        )
        dev.attributes.set_value(
            "firmware_version", machine.get("firmware_version", "")
        )
        dev.attributes.set_value(
            "install_date", machine.get("install_date", "")
        )
        for i, g in enumerate(machine.get("gauges", [])):
            dev.attributes.set_value(f"gauge_{i}_key", g.get("key", ""))
            dev.attributes.set_value(f"gauge_{i}_label", g.get("label", ""))
            dev.attributes.set_value(f"gauge_{i}_unit", g.get("unit", ""))
            dev.attributes.set_value(
                f"gauge_{i}_max", float(g.get("max", 100.0))
            )
        # Live data metrics (initial values set here to define their types)
        dev.data.set_value("status", machine.get("status", ""))
        dev.data.set_value(
            "cycles_completed", int(machine.get("cycles_completed", 0))
        )
        dev.data.set_value("hours_run", float(machine.get("hours_run", 0.0)))
        for i, g in enumerate(machine.get("gauges", [])):
            dev.data.set_value(f"gauge_{i}", float(g.get("value", 0.0)))
        for key, val in machine.get("readiness", {}).items():
            dev.data.set_value(f"readiness_{key}", bool(val))
        return dev

    def _make_station_device(self, station: dict) -> MqttSpbEntityDevice:
        """Make a station device."""
        dev = MqttSpbEntityDevice(
            spb_group_name=_GROUP,
            spb_eon_name=_EDGE_NODE,
            spb_eon_device_name="station",
            retain_birth=True,
            debug=False,
        )
        dev.data.set_value("state", station.get("state", ""))
        dev.data.set_value(
            "alarms_json", json.dumps(station.get("active_alarms", []))
        )
        for key, val in station.get("readiness_flags", {}).items():
            dev.data.set_value(f"readiness_{key}", bool(val))
        for key, val in station.get("quality_readings", {}).items():
            dev.data.set_value(f"quality_{key}", float(val))
        dev.data.set_value(
            "last_completed_step", station.get("last_completed_step") or ""
        )
        dev.data.set_value("procedure_id", station.get("procedure_id") or "")
        return dev

    def _update_machine_device(
        self, dev: MqttSpbEntityDevice, machine: dict
    ) -> None:
        """Update a machine device."""
        dev.data.set_value("status", machine.get("status", ""))
        dev.data.set_value(
            "cycles_completed", int(machine.get("cycles_completed", 0))
        )
        dev.data.set_value("hours_run", float(machine.get("hours_run", 0.0)))
        for i, g in enumerate(machine.get("gauges", [])):
            dev.data.set_value(f"gauge_{i}", float(g.get("value", 0.0)))
        for key, val in machine.get("readiness", {}).items():
            dev.data.set_value(f"readiness_{key}", bool(val))

    def _update_station_device(
        self, dev: MqttSpbEntityDevice, station: dict
    ) -> None:
        """Update a station device."""
        dev.data.set_value("state", station.get("state", ""))
        dev.data.set_value(
            "alarms_json", json.dumps(station.get("active_alarms", []))
        )
        for key, val in station.get("readiness_flags", {}).items():
            dev.data.set_value(f"readiness_{key}", bool(val))
        for key, val in station.get("quality_readings", {}).items():
            dev.data.set_value(f"quality_{key}", float(val))
        dev.data.set_value(
            "last_completed_step", station.get("last_completed_step") or ""
        )

    def _run(self) -> None:
        """Run the Sparkplug publisher."""
        while not self._stop_event.is_set():
            try:
                snapshot = self._simulator.snapshot() if self._simulator else {}
            except (OSError, ValueError, TimeoutError, ConnectionError) as exc:
                logger.error("Snapshot error: %s", exc)
                self._stop_event.wait(timeout=5)
                continue

            edge_node = MqttSpbEntityEdgeNode(
                _GROUP, _EDGE_NODE, retain_birth=True, debug=False
            )

            machine_devices: dict[str, MqttSpbEntityDevice] = {}
            for machine in snapshot.get("machines", []):
                machine_devices[machine["id"]] = self._make_machine_device(
                    machine
                )

            station_device: MqttSpbEntityDevice | None = None
            if snapshot.get("station_state"):
                station_device = self._make_station_device(
                    snapshot["station_state"]
                )

            # Connect edge node first (NBIRTH)
            if not edge_node.connect(host=self._host, port=self._port):
                logger.warning("EdgeNode connect failed — retrying in 5s")
                self._stop_event.wait(timeout=5)
                continue

            edge_node.publish_birth()

            # Connect and DBIRTH each device
            all_devices = list(machine_devices.items())
            if station_device:
                all_devices.append(("station", station_device))

            for dev_id, dev in all_devices:
                if dev.connect(host=self._host, port=self._port):
                    dev.publish_birth()
                    logger.info("DBIRTH published for %s", dev_id)
                else:
                    logger.warning("Device %s connect failed", dev_id)

            logger.info(
                "Sparkplug B birth certificates published — starting DDATA loop"
            )

            # Publish DDATA every interval
            while not self._stop_event.is_set():
                try:
                    snap = self._simulator.snapshot() if self._simulator else {}
                except (OSError, ValueError, TimeoutError, ConnectionError) as exc:
                    logger.error("Snapshot error: %s", exc)
                    break

                for machine in snap.get("machines", []):
                    dev = machine_devices.get(machine["id"])
                    if dev:
                        self._update_machine_device(dev, machine)
                        try:
                            dev.publish_data()
                        except (OSError, ValueError, TimeoutError, ConnectionError) as exc:
                            logger.warning(
                                "DDATA publish error (%s): %s",
                                machine["id"],
                                exc,
                            )
                            break

                if station_device and snap.get("station_state"):
                    self._update_station_device(
                        station_device, snap["station_state"]
                    )
                    try:
                        station_device.publish_data()
                    except (OSError, ValueError, TimeoutError, ConnectionError) as exc:
                        logger.warning("DDATA publish error (station): %s", exc)
                        break

                self._stop_event.wait(timeout=_PUBLISH_INTERVAL)

            # Disconnect all on exit or reconnect
            for _, dev in all_devices:
                try:
                    dev.disconnect()
                except (OSError, ConnectionError):
                    pass
            try:
                edge_node.disconnect()
            except (OSError, ConnectionError):
                pass

            if not self._stop_event.is_set():
                logger.warning("Broker connection lost — reconnecting in 5s")
                self._stop_event.wait(timeout=5)
