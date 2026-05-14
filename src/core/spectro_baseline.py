"""Baseline stability analysis for spectrometer voltage samples."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class BaselineSample:
    """One voltage sample used for baseline stability analysis."""

    timestamp_s: float
    voltage: float


@dataclass(frozen=True)
class BaselineMetrics:
    """Computed metrics for a baseline stability run."""

    sample_count: int
    duration_s: float
    warmup_s: float
    start_voltage_v: float
    end_voltage_v: float
    mean_voltage_v: float
    drift_v: float
    drift_percent: float
    peak_to_peak_v: float
    std_dev_v: float
    detrended_rms_v: float
    slope_v_per_s: float
    slope_v_per_min: float
    min_voltage_v: float
    max_voltage_v: float


def analyze_baseline(
    samples: Sequence[BaselineSample],
    warmup_s: float = 0.0,
) -> BaselineMetrics:
    """Analyze voltage drift after dropping the initial warmup window.

    Args:
        samples: Voltage samples with monotonic or unordered timestamps.
        warmup_s: Seconds to drop from the start of the run.

    Raises:
        ValueError: If fewer than two finite samples remain after warmup.
    """

    if not samples:
        raise ValueError("baseline analysis requires at least two samples after warmup")

    ordered = sorted(samples, key=lambda sample: sample.timestamp_s)
    start_time = ordered[0].timestamp_s
    warmup_cutoff = start_time + max(0.0, warmup_s)
    filtered = [
        sample
        for sample in ordered
        if sample.timestamp_s >= warmup_cutoff
        and isfinite(sample.timestamp_s)
        and isfinite(sample.voltage)
    ]

    if len(filtered) < 2:
        raise ValueError("baseline analysis requires at least two samples after warmup")

    timestamps = np.array([sample.timestamp_s for sample in filtered], dtype=float)
    voltages = np.array([sample.voltage for sample in filtered], dtype=float)
    relative_t = timestamps - timestamps[0]

    duration_s = float(timestamps[-1] - timestamps[0])
    if duration_s <= 0:
        raise ValueError("baseline analysis requires samples spanning a positive duration")

    slope_v_per_s, intercept = np.polyfit(relative_t, voltages, deg=1)
    trend = slope_v_per_s * relative_t + intercept
    residuals = voltages - trend

    window_size = max(1, min(10, len(voltages) // 10))
    start_voltage_v = float(np.mean(voltages[:window_size]))
    end_voltage_v = float(np.mean(voltages[-window_size:]))
    drift_v = end_voltage_v - start_voltage_v
    drift_percent = (drift_v / abs(start_voltage_v) * 100.0) if abs(start_voltage_v) > 1e-12 else 0.0

    return BaselineMetrics(
        sample_count=len(filtered),
        duration_s=duration_s,
        warmup_s=max(0.0, warmup_s),
        start_voltage_v=start_voltage_v,
        end_voltage_v=end_voltage_v,
        mean_voltage_v=float(np.mean(voltages)),
        drift_v=float(drift_v),
        drift_percent=float(drift_percent),
        peak_to_peak_v=float(np.max(voltages) - np.min(voltages)),
        std_dev_v=float(np.std(voltages, ddof=0)),
        detrended_rms_v=float(np.sqrt(np.mean(np.square(residuals)))),
        slope_v_per_s=float(slope_v_per_s),
        slope_v_per_min=float(slope_v_per_s * 60.0),
        min_voltage_v=float(np.min(voltages)),
        max_voltage_v=float(np.max(voltages)),
    )
