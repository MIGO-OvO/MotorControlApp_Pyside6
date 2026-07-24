"""Comparable spectrometer trace recording for Windows-direct and Jetson paths."""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence


JETSON_COMPATIBLE_COLUMNS = [
    "frame_index",
    "received_at_ms",
    "source_timestamp_ms",
    "voltage",
    "absorbance",
    "raw_code",
    "valid",
    "status",
]

SPECTRO_CSV_COLUMNS = JETSON_COMPATIBLE_COLUMNS + [
    "seq",
    "elapsed_s",
    "host_interarrival_ms",
    "source_delta_ms",
    "tca_channel",
    "status_bits",
    "i2c_error",
    "not_configured",
    "saturated",
    "transport_path",
    "session_id",
    "ads_success",
    "ads_mutex_timeout",
    "ads_i2c_error",
    "ads_crc_error",
    "ads_duplicate",
    "ads_transient_drop",
]


class SpectroTraceRecorder:
    """Collects direct serial frames in a Jetson-compatible CSV schema."""

    def __init__(self, transport_path: str = "windows_direct") -> None:
        self.transport_path = transport_path
        self.records: list[dict] = []
        self.session_id = ""
        self._last_received_at_ms: Optional[int] = None
        self._last_source_timestamp_ms: Optional[int] = None

    def start_session(self, session_id: Optional[str] = None) -> None:
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        self._last_received_at_ms = None
        self._last_source_timestamp_ms = None

    def append_packet(
        self,
        packet: dict,
        *,
        received_at_ms: int,
        elapsed_s: float,
        absorbance: float,
        ads_counters: Optional[dict[str, int]] = None,
    ) -> dict:
        if not self.session_id:
            self.start_session()

        status_bits = int(packet.get("status", 0))
        source_timestamp_ms = int(packet.get("timestamp_ms", 0))
        counters = ads_counters or {}
        valid = bool(status_bits & 0x01)
        i2c_error = bool(status_bits & 0x02)
        not_configured = bool(status_bits & 0x04)
        saturated = bool(status_bits & 0x08)

        if valid:
            status = "acquiring"
        elif i2c_error:
            status = "i2c_error"
        elif not_configured:
            status = "not_configured"
        elif saturated:
            status = "saturated"
        else:
            status = "idle"

        frame_index = len(self.records)
        record = {
            "frame_index": frame_index,
            "received_at_ms": int(received_at_ms),
            "source_timestamp_ms": source_timestamp_ms,
            "voltage": float(packet.get("voltage", 0.0)),
            "absorbance": float(absorbance),
            "raw_code": int(packet.get("raw_code", 0)),
            "valid": valid,
            "status": status,
            "seq": frame_index + 1,
            "elapsed_s": float(elapsed_s),
            "host_interarrival_ms": _positive_delta(
                int(received_at_ms), self._last_received_at_ms
            ),
            "source_delta_ms": _u32_delta(
                source_timestamp_ms, self._last_source_timestamp_ms
            ),
            "tca_channel": int(packet.get("tca_channel", -1)),
            "status_bits": status_bits,
            "i2c_error": i2c_error,
            "not_configured": not_configured,
            "saturated": saturated,
            "transport_path": self.transport_path,
            "session_id": self.session_id,
            "ads_success": counters.get("success"),
            "ads_mutex_timeout": counters.get("mutex_timeout"),
            "ads_i2c_error": counters.get("i2c_error"),
            "ads_crc_error": counters.get("crc_error"),
            "ads_duplicate": counters.get("duplicate"),
            "ads_transient_drop": counters.get("transient_drop"),
        }
        self.records.append(record)
        self._last_received_at_ms = int(received_at_ms)
        self._last_source_timestamp_ms = source_timestamp_ms
        return record

    def clear(self) -> None:
        self.records.clear()
        self.session_id = ""
        self._last_received_at_ms = None
        self._last_source_timestamp_ms = None

    def export_csv(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=SPECTRO_CSV_COLUMNS,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(self.records)


@dataclass(frozen=True)
class SpectroTraceSummary:
    sample_count: int
    duration_ms: Optional[float]
    receive_rate_hz: Optional[float]
    voltage_mean_v: Optional[float]
    voltage_std_v: Optional[float]
    voltage_min_v: Optional[float]
    voltage_max_v: Optional[float]
    host_interval_median_ms: Optional[float]
    host_interval_p95_ms: Optional[float]
    source_interval_median_ms: Optional[float]
    source_interval_p95_ms: Optional[float]
    isolated_spike_count_20mv: int


@dataclass(frozen=True)
class SpectroTraceComparison:
    windows: SpectroTraceSummary
    jetson: SpectroTraceSummary
    voltage_mean_delta_v: Optional[float]
    voltage_std_delta_v: Optional[float]
    receive_rate_delta_hz: Optional[float]
    host_interval_p95_delta_ms: Optional[float]
    source_interval_p95_delta_ms: Optional[float]
    isolated_spike_count_delta: int


def summarize_spectro_csv(path: str | Path) -> SpectroTraceSummary:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or ())
        missing = [
            column for column in JETSON_COMPATIBLE_COLUMNS if column not in fieldnames
        ]
        if missing:
            raise ValueError("CSV 缺少 Jetson 兼容字段: " + ", ".join(missing))
        rows = list(reader)

    received_times = _column_floats(rows, "received_at_ms")
    source_times = _column_ints(rows, "source_timestamp_ms")
    voltages = _column_floats(rows, "voltage")
    host_intervals = _positive_intervals(received_times)
    source_intervals = [
        delta
        for previous, current in zip(source_times, source_times[1:])
        if (delta := _u32_delta(current, previous)) is not None
    ]

    duration_ms = None
    receive_rate_hz = None
    if len(received_times) >= 2:
        duration_ms = received_times[-1] - received_times[0]
        if duration_ms > 0:
            receive_rate_hz = (len(received_times) - 1) * 1000.0 / duration_ms

    return SpectroTraceSummary(
        sample_count=len(rows),
        duration_ms=duration_ms,
        receive_rate_hz=receive_rate_hz,
        voltage_mean_v=statistics.fmean(voltages) if voltages else None,
        voltage_std_v=(
            statistics.pstdev(voltages)
            if len(voltages) >= 2
            else 0.0 if voltages else None
        ),
        voltage_min_v=min(voltages) if voltages else None,
        voltage_max_v=max(voltages) if voltages else None,
        host_interval_median_ms=(
            statistics.median(host_intervals) if host_intervals else None
        ),
        host_interval_p95_ms=_percentile_nearest_rank(host_intervals, 0.95),
        source_interval_median_ms=(
            statistics.median(source_intervals) if source_intervals else None
        ),
        source_interval_p95_ms=_percentile_nearest_rank(source_intervals, 0.95),
        isolated_spike_count_20mv=_count_isolated_downward_spikes(voltages, 0.020),
    )


def compare_spectro_csv(
    windows_path: str | Path,
    jetson_path: str | Path,
) -> SpectroTraceComparison:
    windows = summarize_spectro_csv(windows_path)
    jetson = summarize_spectro_csv(jetson_path)
    return SpectroTraceComparison(
        windows=windows,
        jetson=jetson,
        voltage_mean_delta_v=_subtract(jetson.voltage_mean_v, windows.voltage_mean_v),
        voltage_std_delta_v=_subtract(jetson.voltage_std_v, windows.voltage_std_v),
        receive_rate_delta_hz=_subtract(
            jetson.receive_rate_hz, windows.receive_rate_hz
        ),
        host_interval_p95_delta_ms=_subtract(
            jetson.host_interval_p95_ms, windows.host_interval_p95_ms
        ),
        source_interval_p95_delta_ms=_subtract(
            jetson.source_interval_p95_ms, windows.source_interval_p95_ms
        ),
        isolated_spike_count_delta=(
            jetson.isolated_spike_count_20mv - windows.isolated_spike_count_20mv
        ),
    )


def format_spectro_comparison(comparison: SpectroTraceComparison) -> str:
    windows = comparison.windows
    jetson = comparison.jetson
    return "\n".join(
        [
            "Windows 直连 / Jetson 对比",
            f"样本数: {windows.sample_count} / {jetson.sample_count}",
            f"接收频率: {_fmt(windows.receive_rate_hz, 'Hz')} / {_fmt(jetson.receive_rate_hz, 'Hz')}",
            f"主机间隔 P95: {_fmt(windows.host_interval_p95_ms, 'ms')} / {_fmt(jetson.host_interval_p95_ms, 'ms')}",
            f"设备间隔 P95: {_fmt(windows.source_interval_p95_ms, 'ms')} / {_fmt(jetson.source_interval_p95_ms, 'ms')}",
            f"电压均值: {_fmt(windows.voltage_mean_v, 'V', 6)} / {_fmt(jetson.voltage_mean_v, 'V', 6)}",
            f"电压标准差: {_fmt(windows.voltage_std_v, 'V', 6)} / {_fmt(jetson.voltage_std_v, 'V', 6)}",
            f"孤立下冲(>20mV): {windows.isolated_spike_count_20mv} / {jetson.isolated_spike_count_20mv}",
            "",
            f"Jetson-Windows 主机间隔 P95: {_fmt(comparison.host_interval_p95_delta_ms, 'ms')}",
            f"Jetson-Windows 电压均值: {_fmt(comparison.voltage_mean_delta_v, 'V', 6)}",
        ]
    )


def _column_floats(rows: Iterable[dict], key: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row.get(key, ""))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def _column_ints(rows: Iterable[dict], key: str) -> list[int]:
    values = []
    for row in rows:
        try:
            values.append(int(float(row.get(key, ""))))
        except (TypeError, ValueError):
            continue
    return values


def _positive_intervals(values: list[float]) -> list[float]:
    return [
        current - previous
        for previous, current in zip(values, values[1:])
        if current > previous
    ]


def _positive_delta(current: int, previous: Optional[int]) -> Optional[int]:
    if previous is None or current < previous:
        return None
    return current - previous


def _u32_delta(current: int, previous: Optional[int]) -> Optional[int]:
    if previous is None:
        return None
    return (current - previous) & 0xFFFFFFFF


def _percentile_nearest_rank(
    values: Sequence[float], percentile: float
) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def _count_isolated_downward_spikes(voltages: list[float], threshold_v: float) -> int:
    return sum(
        1
        for previous, current, following in zip(voltages, voltages[1:], voltages[2:])
        if current + threshold_v < min(previous, following)
    )


def _subtract(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None or right is None:
        return None
    return left - right


def _fmt(value: Optional[float], unit: str, digits: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:.{digits}f} {unit}"
