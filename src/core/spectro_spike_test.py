"""Session-scoped spectrometer spike diagnostics shared by the Windows UI."""

from __future__ import annotations

import csv
import io
import math
import time
from dataclasses import dataclass
from typing import Mapping, Optional


DROP_THRESHOLDS_V = (0.005, 0.010, 0.020)
COUNTER_KEYS = ("crc_error", "duplicate", "transient_drop")
_VOLTAGE_EPSILON_V = 1e-12

SPIKE_TEST_SUMMARY_COLUMNS = [
    "session_id",
    "transport_path",
    "started_at_ms",
    "ended_at_ms",
    "duration_s",
    "sample_count",
    "receive_rate_hz",
    "drop_count_5mv",
    "drop_count_10mv",
    "drop_count_20mv",
    "max_down_mv",
    "ads_crc_error_delta",
    "ads_duplicate_delta",
    "ads_transient_drop_delta",
    "counter_reset_detected",
]


@dataclass(frozen=True)
class SpikeTestSummary:
    active: bool
    started_at_ms: Optional[int]
    ended_at_ms: Optional[int]
    duration_s: float
    sample_count: int
    receive_rate_hz: Optional[float]
    drop_count_5mv: int
    drop_count_10mv: int
    drop_count_20mv: int
    max_down_mv: float
    ads_crc_error_delta: Optional[int]
    ads_duplicate_delta: Optional[int]
    ads_transient_drop_delta: Optional[int]
    counter_reset_detected: bool


class SpectroSpikeTest:
    """Tracks downward voltage steps and ADS counter deltas for one test."""

    def __init__(self) -> None:
        self.reset()

    @property
    def active(self) -> bool:
        return self._active

    def reset(self) -> None:
        self._active = False
        self._started_at_ms: Optional[int] = None
        self._ended_at_ms: Optional[int] = None
        self._sample_count = 0
        self._first_sample_at_ms: Optional[int] = None
        self._last_sample_at_ms: Optional[int] = None
        self._previous_voltage: Optional[float] = None
        self._drop_counts = [0, 0, 0]
        self._max_down_v = 0.0
        self._counter_baseline: dict[str, int] = {}
        self._counter_current: dict[str, int] = {}

    def start(
        self,
        *,
        started_at_ms: Optional[int] = None,
        counters: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.reset()
        self._active = True
        self._started_at_ms = int(
            started_at_ms if started_at_ms is not None else time.time() * 1000
        )
        self._counter_baseline = _normalize_counters(counters)
        self._counter_current = dict(self._counter_baseline)

    def add_sample(
        self,
        *,
        timestamp_ms: int,
        voltage: float,
        valid: bool = True,
    ) -> None:
        if not self._active or not valid:
            return
        try:
            numeric_voltage = float(voltage)
            numeric_timestamp = int(timestamp_ms)
        except (TypeError, ValueError):
            return
        if not math.isfinite(numeric_voltage):
            return

        if self._previous_voltage is not None:
            down_v = self._previous_voltage - numeric_voltage
            if down_v > self._max_down_v:
                self._max_down_v = down_v
            for index, threshold_v in enumerate(DROP_THRESHOLDS_V):
                if down_v - threshold_v > _VOLTAGE_EPSILON_V:
                    self._drop_counts[index] += 1

        self._previous_voltage = numeric_voltage
        self._sample_count += 1
        if self._first_sample_at_ms is None:
            self._first_sample_at_ms = numeric_timestamp
        self._last_sample_at_ms = numeric_timestamp

    def update_counters(
        self,
        counters: Optional[Mapping[str, int]],
    ) -> None:
        if self._active:
            self._counter_current = _normalize_counters(counters)

    def stop(
        self,
        *,
        ended_at_ms: Optional[int] = None,
        counters: Optional[Mapping[str, int]] = None,
    ) -> None:
        if not self._active:
            return
        if counters is not None:
            self._counter_current = _normalize_counters(counters)
        self._ended_at_ms = int(
            ended_at_ms if ended_at_ms is not None else time.time() * 1000
        )
        self._active = False

    def summary(self, now_ms: Optional[int] = None) -> SpikeTestSummary:
        effective_end_ms = self._ended_at_ms
        if self._active:
            effective_end_ms = int(
                now_ms if now_ms is not None else time.time() * 1000
            )
        duration_s = 0.0
        if self._started_at_ms is not None and effective_end_ms is not None:
            duration_s = max(0.0, (effective_end_ms - self._started_at_ms) / 1000.0)

        receive_rate_hz = None
        if (
            self._sample_count >= 2
            and self._first_sample_at_ms is not None
            and self._last_sample_at_ms is not None
            and self._last_sample_at_ms > self._first_sample_at_ms
        ):
            receive_rate_hz = (
                (self._sample_count - 1)
                * 1000.0
                / (self._last_sample_at_ms - self._first_sample_at_ms)
            )

        crc_delta, crc_reset = _counter_delta(
            self._counter_baseline.get("crc_error"),
            self._counter_current.get("crc_error"),
        )
        duplicate_delta, duplicate_reset = _counter_delta(
            self._counter_baseline.get("duplicate"),
            self._counter_current.get("duplicate"),
        )
        transient_delta, transient_reset = _counter_delta(
            self._counter_baseline.get("transient_drop"),
            self._counter_current.get("transient_drop"),
        )

        return SpikeTestSummary(
            active=self._active,
            started_at_ms=self._started_at_ms,
            ended_at_ms=self._ended_at_ms,
            duration_s=duration_s,
            sample_count=self._sample_count,
            receive_rate_hz=receive_rate_hz,
            drop_count_5mv=self._drop_counts[0],
            drop_count_10mv=self._drop_counts[1],
            drop_count_20mv=self._drop_counts[2],
            max_down_mv=self._max_down_v * 1000.0,
            ads_crc_error_delta=crc_delta,
            ads_duplicate_delta=duplicate_delta,
            ads_transient_drop_delta=transient_delta,
            counter_reset_detected=crc_reset or duplicate_reset or transient_reset,
        )


def build_spike_test_summary_csv(
    summary: SpikeTestSummary,
    *,
    session_id: str,
    transport_path: str,
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=SPIKE_TEST_SUMMARY_COLUMNS)
    writer.writeheader()
    writer.writerow(
        {
            "session_id": session_id,
            "transport_path": transport_path,
            "started_at_ms": summary.started_at_ms,
            "ended_at_ms": summary.ended_at_ms,
            "duration_s": _csv_number(summary.duration_s),
            "sample_count": summary.sample_count,
            "receive_rate_hz": _csv_number(summary.receive_rate_hz),
            "drop_count_5mv": summary.drop_count_5mv,
            "drop_count_10mv": summary.drop_count_10mv,
            "drop_count_20mv": summary.drop_count_20mv,
            "max_down_mv": _csv_number(summary.max_down_mv),
            "ads_crc_error_delta": summary.ads_crc_error_delta,
            "ads_duplicate_delta": summary.ads_duplicate_delta,
            "ads_transient_drop_delta": summary.ads_transient_drop_delta,
            "counter_reset_detected": str(summary.counter_reset_detected).lower(),
        }
    )
    return "\ufeff" + output.getvalue()


def _normalize_counters(
    counters: Optional[Mapping[str, int]],
) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for key in COUNTER_KEYS:
        if not counters or counters.get(key) is None:
            continue
        try:
            normalized[key] = int(counters[key])
        except (TypeError, ValueError):
            continue
    return normalized


def _counter_delta(
    baseline: Optional[int],
    current: Optional[int],
) -> tuple[Optional[int], bool]:
    if baseline is None or current is None:
        return None, False
    if current < baseline:
        return None, True
    return current - baseline, False


def _csv_number(value: Optional[float]) -> str:
    if value is None:
        return ""
    return format(float(value), ".12g")
