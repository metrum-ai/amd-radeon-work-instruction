# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Machine simulator for the work instruction generator."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a value between a lower and upper bound."""
    return max(lower, min(upper, value))


def iso_timestamp(epoch_seconds: float) -> str:
    """Convert an epoch seconds to an ISO timestamp."""
    return (
        datetime.fromtimestamp(epoch_seconds, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def round_for_display(value: float) -> float:
    """Round a value for display."""
    return round(value, 1 if abs(value) < 100 else 0)


# PackML state → gauge factor category (ISA-88 / IEC 62264)
_PACKML_FACTOR: dict[str, str] = {
    "Execute": "active",
    "Starting": "ready",
    "Completing": "ready",
    "Complete": "ready",
    "Idle": "ready",
    "Held": "idle",
    "Aborted": "fault",
}

# PackML states that require a pulsing status indicator
PACKML_ACTIVE_STATES = {"Execute", "Starting", "Completing"}


@dataclass(frozen=True)
class MachineDoc:
    """Machine document model."""

    doc_id: str
    file_name: str
    file_type: str
    language: str
    pages: int
    display_name: str


@dataclass(frozen=True)
class GaugeProfile:
    """Gauge profile model."""

    key: str
    label: str
    unit: str
    max_value: float
    baseline: float
    amplitude: float
    drift: float
    phase: float
    active_factor: float
    ready_factor: float
    idle_factor: float
    fault_factor: float


@dataclass(frozen=True)
class MachineProfile:
    """Machine profile model."""

    id: str
    name: str
    vendor: str
    origin: str
    type: str
    serial_number: str
    firmware_version: str
    install_date: str  # ISO-8601 date
    phase_offset: float
    gauges: tuple[GaugeProfile, ...]
    readiness_keys: tuple[str, ...]
    docs: tuple[MachineDoc, ...]
    fault_prone: bool = False


class MachineSimulator:
    """Machine simulator."""

    def __init__(self) -> None:
        """Initialize the machine simulator."""
        self.started_monotonic = time.monotonic()
        self.started_epoch = time.time()
        self.station_id = "hv_integration_bench"
        self.procedure_id = "hv_harness_routing"
        self._machine_profiles = self._build_machine_profiles()
        # Runtime fault-prone overrides: None = use profile default
        self._fault_prone_overrides: dict[str, bool] = {}
        self._step_names = (
            "hv_loto_verification",
            "routing_channel_inspection",
            "hv_cable_routing",
            "negative_cable_routing",
            "main_contactor_connection",
            "protection_sleeve_install",
            "insulation_resistance_test",
            "final_inspection_signoff",
        )

    def _build_machine_profiles(self) -> dict[str, MachineProfile]:
        """Build the machine profiles."""
        return {
            "zyro-welder": MachineProfile(
                id="zyro-welder",
                name="ZYRO Welder",
                vendor="ZYRO",
                origin="DE",
                type="Fiber Laser Welder",
                serial_number="KW-2024-0847",
                firmware_version="3.2.1",
                install_date="2024-03-15",
                phase_offset=0.0,
                readiness_keys=(
                    "fixture_clamped",
                    "laser_aligned",
                    "shield_gas_ok",
                    "lens_clean",
                ),
                docs=(
                    MachineDoc(
                        doc_id="doc-zyro-1",
                        file_name="ZYRO_Assembly_Guide_Rev_C.pdf",
                        file_type="pdf",
                        language="DE",
                        pages=32,
                        display_name="ZYRO_Montageanleitung_Rev_C",
                    ),
                ),
                gauges=(
                    GaugeProfile(
                        "laser_power",
                        "Laser",
                        "W",
                        4000,
                        2400,
                        320,
                        110,
                        0.1,
                        1.0,
                        0.74,
                        0.22,
                        0.15,
                    ),
                    GaugeProfile(
                        "weld_current",
                        "Current",
                        "A",
                        300,
                        185,
                        18,
                        8,
                        1.4,
                        1.0,
                        0.78,
                        0.30,
                        0.18,
                    ),
                    GaugeProfile(
                        "gas_flow",
                        "Gas",
                        "L/m",
                        25,
                        14.2,
                        1.6,
                        0.8,
                        2.0,
                        1.0,
                        0.82,
                        0.38,
                        0.20,
                    ),
                ),
            ),
            "veltrix-dispenser": MachineProfile(
                id="veltrix-dispenser",
                name="Veltrix Dispenser",
                vendor="Veltrix",
                origin="US",
                type="Gantry Adhesive System",
                serial_number="ND-2023-1204",
                firmware_version="2.8.0",
                install_date="2023-11-08",
                phase_offset=70.0,
                readiness_keys=(
                    "purge_complete",
                    "head_homed",
                    "bead_sensor_cal",
                ),
                docs=(
                    MachineDoc(
                        doc_id="doc-veltrix-1",
                        file_name="Veltrix_Routing_Specification.pdf",
                        file_type="pdf",
                        language="EN",
                        pages=24,
                        display_name="Veltrix_Routing_Specification",
                    ),
                ),
                gauges=(
                    GaugeProfile(
                        "nozzle_temp",
                        "Nozzle",
                        "°C",
                        80,
                        47.3,
                        6.4,
                        1.6,
                        0.9,
                        1.0,
                        0.93,
                        0.68,
                        0.52,
                    ),
                    GaugeProfile(
                        "reservoir_level",
                        "Reservoir",
                        "%",
                        100,
                        72,
                        7.5,
                        -5.2,
                        2.3,
                        0.96,
                        0.90,
                        0.84,
                        0.80,
                    ),
                    GaugeProfile(
                        "humidity",
                        "Humidity",
                        "%",
                        100,
                        54,
                        4.2,
                        2.2,
                        1.7,
                        1.0,
                        0.98,
                        0.92,
                        0.95,
                    ),
                ),
            ),
            "nexora-scanner": MachineProfile(
                id="nexora-scanner",
                name="Nexora Scanner",
                vendor="Nexora",
                origin="JP",
                type="KS-200 Optical Inspector",
                serial_number="KS-2024-0316",
                firmware_version="1.9.4",
                install_date="2024-06-22",
                phase_offset=145.0,
                readiness_keys=("calibrated", "lens_clean", "focus_locked"),
                docs=(
                    MachineDoc(
                        doc_id="doc-nexora-1",
                        file_name="Nexora_KS200_Inspection_Standard.pdf",
                        file_type="pdf",
                        language="JA",
                        pages=16,
                        display_name="ネクソラ_KS200検査基準書",
                    ),
                ),
                gauges=(
                    GaugeProfile(
                        "pass_rate",
                        "Pass %",
                        "%",
                        100,
                        98.4,
                        1.2,
                        -0.6,
                        0.4,
                        1.0,
                        0.995,
                        0.985,
                        0.94,
                    ),
                    GaugeProfile(
                        "light_intensity",
                        "Light",
                        "%",
                        100,
                        82,
                        5.0,
                        2.5,
                        1.2,
                        1.0,
                        0.97,
                        0.88,
                        0.80,
                    ),
                    GaugeProfile(
                        "scan_speed",
                        "Speed",
                        "mm/s",
                        200,
                        120,
                        18,
                        12,
                        2.8,
                        1.0,
                        0.80,
                        0.46,
                        0.35,
                    ),
                ),
            ),
        }

    def _elapsed(self, sample_monotonic: float | None = None) -> float:
        current = (
            sample_monotonic
            if sample_monotonic is not None
            else time.monotonic()
        )
        return current - self.started_monotonic

    # ------------------------------------------------------------------
    # 1. PackML state machine (ISA-88 / IEC 62264)
    # ------------------------------------------------------------------
    def _packml_state(
        self, elapsed: float, phase_offset: float, forced_abort: bool = False
    ) -> str:
        """Return the current ISA-88 PackML state for the machine.

        forced_abort is the on-demand override (toggle_fault_prone) — it forces
        Aborted immediately regardless of where the automatic cycle currently sits.
        """
        if forced_abort:
            return "Aborted"
        # Independent per-machine cycle, staggered via phase_offset: 1 min Aborted,
        # then 3 min Execute, repeating. Offsets (0/70/145) keep machines from
        # aborting simultaneously.
        cycle = (elapsed + phase_offset) % 240.0
        if cycle < 60.0:
            return "Aborted"
        return "Execute"

    def _factor_for_state(self, profile: GaugeProfile, state: str) -> float:
        """Get the factor for a state."""
        category = _PACKML_FACTOR.get(state, "fault")
        if category == "active":
            return profile.active_factor
        if category == "ready":
            return profile.ready_factor
        if category == "idle":
            return profile.idle_factor
        return profile.fault_factor

    def _readiness_for_state(
        self, state: str, elapsed: float, index: int
    ) -> bool:
        """Get the readiness for a state."""
        category = _PACKML_FACTOR.get(state, "fault")
        if category == "active":
            return True
        if category == "ready":
            return math.sin((elapsed / 31.0) + index) > -0.92
        if category == "idle":
            return index != 2
        return index == 0 and math.sin((elapsed / 9.0) + index) > 0.15

    # ------------------------------------------------------------------
    # 2. Sensor noise — small Gaussian jitter on every reading
    # ------------------------------------------------------------------
    @staticmethod
    def _noise(sigma: float) -> float:
        """Get the noise for a sigma."""
        return random.gauss(0.0, sigma)

    # ------------------------------------------------------------------
    # Base signal (deterministic multi-wave)
    # ------------------------------------------------------------------
    def _signal(self, elapsed: float, profile: GaugeProfile) -> float:
        """Get the signal for a elapsed time and profile."""
        fast_wave = math.sin((elapsed / 12.0) + profile.phase)
        slow_wave = math.sin((elapsed / 55.0) + (profile.phase * 0.5))
        fine_detail = math.sin((elapsed / 3.7) + (profile.phase * 1.7)) * 0.18
        return (
            profile.baseline
            + (profile.amplitude * fast_wave)
            + (profile.drift * slow_wave)
            + (profile.amplitude * fine_detail)
        )

    # ------------------------------------------------------------------
    # 3. Dispenser reservoir — monotonically drains, refills at low mark
    # ------------------------------------------------------------------
    def _reservoir_level(self, elapsed: float, state: str) -> float:
        """Get the reservoir level for a elapsed time and state."""
        REFILL_CYCLE = 1200.0  # 20-minute full drain → refill cycle
        FULL = 95.0
        LOW = 28.0
        cycle_pos = elapsed % REFILL_CYCLE
        # Linear drain across the cycle; Execute drains faster
        base_level = FULL - (cycle_pos / REFILL_CYCLE) * (FULL - LOW)
        if state == "Execute":
            base_level -= 4.0  # faster consumption during production
        elif state in ("Held", "Aborted"):
            base_level += 6.0  # machine paused → minimal consumption
        return clamp(base_level + self._noise(0.4), LOW, FULL)

    # ------------------------------------------------------------------
    # Asset counters (derived from uptime)
    # ------------------------------------------------------------------
    @staticmethod
    def _cycles_completed(elapsed: float) -> int:
        """Each 240-second machine cycle = one production cycle."""
        return int(elapsed / 240.0)

    @staticmethod
    def _hours_run(elapsed: float) -> float:
        return round(elapsed / 3600.0, 2)

    # ------------------------------------------------------------------
    # Build machine snapshot
    # ------------------------------------------------------------------
    def _build_machine(
        self, profile: MachineProfile, sample_monotonic: float | None = None
    ) -> dict:
        elapsed = self._elapsed(sample_monotonic)
        fault_prone = self._fault_prone_overrides.get(
            profile.id, profile.fault_prone
        )
        state = self._packml_state(elapsed, profile.phase_offset, fault_prone)
        gauges = []

        for gauge_profile in profile.gauges:
            # 3. Reservoir special-case — physics-driven drain/refill
            if (
                profile.id == "veltrix-dispenser"
                and gauge_profile.key == "reservoir_level"
            ):
                value = self._reservoir_level(elapsed, state)
            else:
                raw = self._signal(
                    elapsed, gauge_profile
                ) * self._factor_for_state(gauge_profile, state)
                # 2. Add sensor noise (1.5% of amplitude as 1-sigma)
                raw += self._noise(gauge_profile.amplitude * 0.015)
                value = clamp(raw, 0, gauge_profile.max_value)

            gauges.append(
                {
                    "key": gauge_profile.key,
                    "label": gauge_profile.label,
                    "value": round_for_display(value),
                    "unit": gauge_profile.unit,
                    "max": gauge_profile.max_value,
                }
            )

        # 4. Welder weld_current correlates physically with laser_power
        if profile.id == "zyro-welder":
            laser_power = next(
                g["value"] for g in gauges if g["key"] == "laser_power"
            )
            for g in gauges:
                if g["key"] == "weld_current":
                    # I ≈ P × 0.047 (nominal: 185 A at 3950 W peak)
                    correlated = laser_power * 0.047 + self._noise(2.5)
                    g["value"] = round_for_display(clamp(correlated, 0, 300))

        readiness = {
            key: self._readiness_for_state(state, elapsed, index)
            for index, key in enumerate(profile.readiness_keys)
        }

        return {
            "id": profile.id,
            "name": profile.name,
            "vendor": profile.vendor,
            "origin": profile.origin,
            "type": profile.type,
            # 5. Asset identity
            "serial_number": profile.serial_number,
            "firmware_version": profile.firmware_version,
            "install_date": profile.install_date,
            "cycles_completed": self._cycles_completed(elapsed),
            "hours_run": self._hours_run(elapsed),
            "status": state,
            "gauges": gauges,
            "readiness": readiness,
            "fault_prone": fault_prone,
            "docs": [
                {
                    "doc_id": doc.doc_id,
                    "file_name": doc.file_name,
                    "file_type": doc.file_type,
                    "language": doc.language,
                    "pages": doc.pages,
                    "display_name": doc.display_name,
                }
                for doc in profile.docs
            ],
        }

    def _station_state(self, sample_monotonic: float | None = None) -> dict:
        elapsed = self._elapsed(sample_monotonic)
        station_cycle = elapsed % 420.0

        if station_cycle < 215.0:
            state = "Idle"
        elif station_cycle < 325.0:
            state = "Execute"
        elif station_cycle < 382.0:
            state = "Held"
        else:
            state = "Aborted"

        insulation = clamp(
            12.2
            + math.sin(elapsed / 48.0) * 1.4
            + math.sin(elapsed / 11.0) * 0.35
            + self._noise(0.05),
            0.8,
            18.0,
        )
        torque = clamp(
            42.4
            + math.sin(elapsed / 27.0) * 1.1
            + math.sin(elapsed / 8.5) * 0.25
            + self._noise(0.08),
            39.0,
            45.5,
        )
        harness_temp = clamp(
            28.5 + math.sin(elapsed / 19.0) * 2.8 + self._noise(0.1),
            22.0,
            38.0,
        )
        contact_resistance = clamp(
            0.82
            + math.sin(elapsed / 34.0) * 0.09
            + math.sin(elapsed / 7.0) * 0.02
            + self._noise(0.003),
            0.55,
            1.25,
        )

        readiness_flags = {
            "loto_verified": state != "Aborted",
            "ppe_class_0_confirmed": True,
            "hv_de_energized": state in {"Idle", "Held"},
            "msd_state_safe": state != "Aborted",
            "torque_tool_calibrated": state != "Held",
        }

        active_alarms: list[dict] = []
        if state == "Held":
            active_alarms.append(
                {
                    "code": "WARN-IR-LOW",
                    "severity": "medium",
                    "message": "Insulation resistance is trending toward the lower control band.",
                }
            )
            readiness_flags["torque_tool_calibrated"] = False

        if state == "Aborted":
            active_alarms.extend(
                [
                    {
                        "code": "FLT-HV-INTERLOCK",
                        "severity": "critical",
                        "message": "HV interlock chain opened during harness validation.",
                    },
                    {
                        "code": "FLT-MSD-SAFE",
                        "severity": "high",
                        "message": "Manual service disconnect verification is missing.",
                    },
                ]
            )
            readiness_flags["loto_verified"] = False
            readiness_flags["hv_de_energized"] = False
            readiness_flags["msd_state_safe"] = False

        step_index = int((elapsed // 38.0) % len(self._step_names))

        return {
            "state_id": f"ms-{int(elapsed):06d}",
            "station_id": self.station_id,
            "procedure_id": self.procedure_id,
            "source": "python_machine_simulator",
            "state": state,
            "active_alarms": active_alarms,
            "readiness_flags": readiness_flags,
            "quality_readings": {
                "insulation_resistance_mohm": round(insulation, 2),
                "torque_verification_nm": round(torque, 2),
                "harness_temperature_c": round(harness_temp, 1),
                "contact_resistance_mohm": round(contact_resistance, 3),
            },
            "last_completed_step": self._step_names[step_index],
            "created_at": iso_timestamp(self.started_epoch + elapsed),
        }

    def snapshot(self) -> dict:
        """Get the snapshot of the simulator."""
        now_monotonic = time.monotonic()
        elapsed = self._elapsed(now_monotonic)
        return {
            "sampled_at": iso_timestamp(self.started_epoch + elapsed),
            "simulator_uptime_seconds": round(elapsed, 2),
            "machines": [
                self._build_machine(profile, now_monotonic)
                for profile in self._machine_profiles.values()
            ],
            "station_state": self._station_state(now_monotonic),
        }

    def list_machines(self) -> list[dict]:
        """Get the list of machines of the simulator."""
        now_monotonic = time.monotonic()
        return [
            self._build_machine(profile, now_monotonic)
            for profile in self._machine_profiles.values()
        ]

    def get_machine(self, machine_id: str) -> dict | None:
        """Get the machine of the simulator."""
        profile = self._machine_profiles.get(machine_id)
        if profile is None:
            return None
        return self._build_machine(profile)

    def machine_history(
        self, machine_id: str, samples: int, interval_seconds: float
    ) -> dict | None:
        """Get the machine history of the simulator."""
        profile = self._machine_profiles.get(machine_id)
        if profile is None:
            return None

        current_monotonic = time.monotonic()
        start_offset = (samples - 1) * interval_seconds
        history = []

        for index in range(samples):
            sample_monotonic = (
                current_monotonic - start_offset + (index * interval_seconds)
            )
            elapsed = self._elapsed(sample_monotonic)
            machine = self._build_machine(profile, sample_monotonic)
            history.append(
                {
                    "timestamp": iso_timestamp(self.started_epoch + elapsed),
                    "status": machine["status"],
                    "gauges": machine["gauges"],
                    "readiness": machine["readiness"],
                }
            )

        return {
            "machine_id": machine_id,
            "interval_seconds": interval_seconds,
            "samples": samples,
            "history": history,
        }

    # Maps WIG station IDs to machine profile IDs for readiness flag merging
    _STATION_MACHINE_MAP: dict[str, str] = {
        "welder": "zyro-welder",
        "dispenser": "veltrix-dispenser",
        "tim_dispenser": "veltrix-dispenser",
        "sealing_dispenser": "veltrix-dispenser",
        "cell_tester": "nexora-scanner",
    }

    def get_station_state(self, station_id: str) -> dict:
        """Get the station state of the simulator."""
        result = self._station_state()
        result["station_id"] = station_id

        machine_id = self._STATION_MACHINE_MAP.get(station_id)
        if machine_id:
            machine = self._build_machine(self._machine_profiles[machine_id])
            machine_readiness = machine.get("readiness", {})
            # Replace readiness_flags entirely with machine-specific flags.
            # The base _station_state() flags (hv_de_energized etc.) are only
            # meaningful for the HV bench — other stations get their own machine flags,
            # plus the universal safety flags that apply everywhere.
            universal = {
                k: result["readiness_flags"][k]
                for k in ("loto_verified", "ppe_class_0_confirmed")
                if k in result["readiness_flags"]
            }
            result["readiness_flags"] = {**universal, **machine_readiness}
        return result

    def toggle_fault_prone(self, machine_id: str) -> bool:
        """Toggle the on-demand forced-abort override for a machine.

        Returns the new state.

        When on, the machine reports Aborted immediately, overriding its automatic cycle.
        """
        if machine_id not in self._machine_profiles:
            raise KeyError(machine_id)
        current = self._fault_prone_overrides.get(
            machine_id, self._machine_profiles[machine_id].fault_prone
        )
        new_value = not current
        self._fault_prone_overrides[machine_id] = new_value
        return new_value
