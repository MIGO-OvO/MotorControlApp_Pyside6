"""Health monitor history and export helpers for ESP32 detector diagnostics."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional


CSV_COLUMNS = [
    "host_time",
    "elapsed_s",
    "device_timestamp_ms",
    "uptime_s",
    "temp_c",
    "cpu_freq_mhz",
    "heap_free",
    "heap_min_free",
    "heap_total",
    "heap_free_pct",
    "task_count",
    "loop_stack_hwm",
    "comms_stack_hwm",
    "sensors_stack_hwm",
    "loop_gap_active_max_us",
    "angle_age_ms",
    "ads_success",
    "ads_mutex_timeout",
    "ads_i2c_error",
    "ads_crc_error",
    "ads_duplicate",
    "ads_transient_drop",
    "command_rtt_ms",
]


@dataclass
class HealthSample:
    host_time: datetime
    elapsed_s: float
    device_timestamp_ms: Optional[int]
    uptime_s: Optional[int]
    temp_c: Optional[float]
    cpu_freq_mhz: Optional[int]
    heap_free: Optional[int]
    heap_min_free: Optional[int]
    heap_total: Optional[int]
    heap_free_pct: Optional[float]
    task_count: Optional[int]
    loop_stack_hwm: Optional[int]
    comms_stack_hwm: Optional[int]
    sensors_stack_hwm: Optional[int]
    loop_gap_active_max_us: Optional[int] = None
    angle_age_ms: Optional[int] = None
    ads_success: Optional[int] = None
    ads_mutex_timeout: Optional[int] = None
    ads_i2c_error: Optional[int] = None
    ads_crc_error: Optional[int] = None
    ads_duplicate: Optional[int] = None
    ads_transient_drop: Optional[int] = None
    command_rtt_ms: Optional[float] = None


class HealthHistory:
    """Keeps the current-session ESP32 health samples and CSV export format."""

    def __init__(self, time_provider: Callable[[], float] | None = None) -> None:
        self._time_provider = time.perf_counter if time_provider is None else time_provider
        self._started_at_s: Optional[float] = None
        self.samples: list[HealthSample] = []

    @property
    def latest(self) -> Optional[HealthSample]:
        if not self.samples:
            return None
        return self.samples[-1]

    def append_packet(
        self,
        packet: dict,
        host_time: Optional[datetime] = None,
    ) -> HealthSample:
        now_s = self._time_provider()
        if self._started_at_s is None:
            self._started_at_s = now_s

        sample = HealthSample(
            host_time=datetime.now() if host_time is None else host_time,
            elapsed_s=now_s - self._started_at_s,
            device_timestamp_ms=_optional_int(packet.get("timestamp_ms")),
            uptime_s=_optional_int(packet.get("uptime_s")),
            temp_c=_optional_float(packet.get("temp_c")),
            cpu_freq_mhz=_optional_int(packet.get("cpu_freq_mhz")),
            heap_free=_optional_int(packet.get("heap_free")),
            heap_min_free=_optional_int(packet.get("heap_min_free")),
            heap_total=_optional_int(packet.get("heap_total")),
            heap_free_pct=_optional_float(packet.get("heap_free_pct")),
            task_count=_optional_int(packet.get("task_count")),
            loop_stack_hwm=_optional_int(packet.get("loop_stack_hwm")),
            comms_stack_hwm=_optional_int(packet.get("comms_stack_hwm")),
            sensors_stack_hwm=_optional_int(packet.get("sensors_stack_hwm")),
        )
        self.samples.append(sample)
        return sample

    def update_debug_value(self, key: str, value: int) -> None:
        latest = self.latest
        if latest is None:
            return
        if key == "loop_gap_active_max_us":
            latest.loop_gap_active_max_us = int(value)
        elif key == "angle_age_ms":
            latest.angle_age_ms = int(value)

    def update_command_rtt(self, rtt_ms: float) -> None:
        latest = self.latest
        if latest is not None:
            latest.command_rtt_ms = float(rtt_ms)

    def update_ads_counters(self, counters: dict[str, int]) -> None:
        latest = self.latest
        if latest is None:
            return
        latest.ads_success = _optional_int(counters.get("success"))
        latest.ads_mutex_timeout = _optional_int(counters.get("mutex_timeout"))
        latest.ads_i2c_error = _optional_int(counters.get("i2c_error"))
        latest.ads_crc_error = _optional_int(counters.get("crc_error"))
        latest.ads_duplicate = _optional_int(counters.get("duplicate"))
        latest.ads_transient_drop = _optional_int(counters.get("transient_drop"))

    def clear(self) -> None:
        self.samples.clear()
        self._started_at_s = None

    def build_csv_rows(self) -> list[dict[str, str]]:
        return [_sample_to_csv_row(sample) for sample in self.samples]

    def export_csv(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(self.build_csv_rows())

    def chart_samples(self, limit: int = 600) -> Iterable[HealthSample]:
        if limit <= 0:
            return []
        return self.samples[-limit:]


def _sample_to_csv_row(sample: HealthSample) -> dict[str, str]:
    row = {
        "host_time": sample.host_time.isoformat(timespec="milliseconds"),
        "elapsed_s": sample.elapsed_s,
        "device_timestamp_ms": sample.device_timestamp_ms,
        "uptime_s": sample.uptime_s,
        "temp_c": sample.temp_c,
        "cpu_freq_mhz": sample.cpu_freq_mhz,
        "heap_free": sample.heap_free,
        "heap_min_free": sample.heap_min_free,
        "heap_total": sample.heap_total,
        "heap_free_pct": sample.heap_free_pct,
        "task_count": sample.task_count,
        "loop_stack_hwm": sample.loop_stack_hwm,
        "comms_stack_hwm": sample.comms_stack_hwm,
        "sensors_stack_hwm": sample.sensors_stack_hwm,
        "loop_gap_active_max_us": sample.loop_gap_active_max_us,
        "angle_age_ms": sample.angle_age_ms,
        "ads_success": sample.ads_success,
        "ads_mutex_timeout": sample.ads_mutex_timeout,
        "ads_i2c_error": sample.ads_i2c_error,
        "ads_crc_error": sample.ads_crc_error,
        "ads_duplicate": sample.ads_duplicate,
        "ads_transient_drop": sample.ads_transient_drop,
        "command_rtt_ms": sample.command_rtt_ms,
    }
    return {key: _format_csv_value(row[key]) for key in CSV_COLUMNS}


def _format_csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return text if text else "0"
    return str(value)


def _optional_int(value) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _optional_float(value) -> Optional[float]:
    if value is None:
        return None
    return float(value)
