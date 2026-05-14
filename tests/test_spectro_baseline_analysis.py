import pytest

from src.core.spectro_baseline import BaselineSample, analyze_baseline


def test_constant_voltage_has_zero_drift_and_slope():
    samples = [BaselineSample(timestamp_s=float(i), voltage=1.25) for i in range(20)]

    metrics = analyze_baseline(samples, warmup_s=0.0)

    assert metrics.sample_count == 20
    assert metrics.duration_s == pytest.approx(19.0)
    assert metrics.mean_voltage_v == pytest.approx(1.25)
    assert metrics.drift_v == pytest.approx(0.0, abs=1e-12)
    assert metrics.drift_percent == pytest.approx(0.0, abs=1e-12)
    assert metrics.peak_to_peak_v == pytest.approx(0.0, abs=1e-12)
    assert metrics.std_dev_v == pytest.approx(0.0, abs=1e-12)
    assert metrics.detrended_rms_v == pytest.approx(0.0, abs=1e-12)
    assert metrics.slope_v_per_s == pytest.approx(0.0, abs=1e-12)


def test_linear_voltage_rise_reports_positive_drift_and_slope():
    samples = [
        BaselineSample(timestamp_s=float(i), voltage=1.0 + 0.002 * i)
        for i in range(11)
    ]

    metrics = analyze_baseline(samples, warmup_s=0.0)

    assert metrics.sample_count == 11
    assert metrics.duration_s == pytest.approx(10.0)
    assert metrics.start_voltage_v == pytest.approx(1.0)
    assert metrics.end_voltage_v == pytest.approx(1.02)
    assert metrics.drift_v == pytest.approx(0.02)
    assert metrics.drift_percent == pytest.approx(2.0)
    assert metrics.peak_to_peak_v == pytest.approx(0.02)
    assert metrics.slope_v_per_s == pytest.approx(0.002)
    assert metrics.slope_v_per_min == pytest.approx(0.12)
    assert metrics.detrended_rms_v == pytest.approx(0.0, abs=1e-12)


def test_warmup_discards_samples_before_warmup_window():
    samples = [
        BaselineSample(timestamp_s=0.0, voltage=2.0),
        BaselineSample(timestamp_s=1.0, voltage=2.5),
        BaselineSample(timestamp_s=2.0, voltage=1.0),
        BaselineSample(timestamp_s=3.0, voltage=1.1),
        BaselineSample(timestamp_s=4.0, voltage=1.2),
    ]

    metrics = analyze_baseline(samples, warmup_s=2.0)

    assert metrics.sample_count == 3
    assert metrics.duration_s == pytest.approx(2.0)
    assert metrics.start_voltage_v == pytest.approx(1.0)
    assert metrics.end_voltage_v == pytest.approx(1.2)
    assert metrics.drift_v == pytest.approx(0.2)


def test_analyze_baseline_requires_two_samples_after_warmup():
    samples = [
        BaselineSample(timestamp_s=0.0, voltage=1.0),
        BaselineSample(timestamp_s=1.0, voltage=1.1),
    ]

    with pytest.raises(ValueError, match="at least two samples after warmup"):
        analyze_baseline(samples, warmup_s=1.0)
