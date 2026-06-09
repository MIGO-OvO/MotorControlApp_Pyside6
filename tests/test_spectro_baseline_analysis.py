import pytest

from src.core.spectro_baseline import (
    BaselineExportRecord,
    BaselineSample,
    analyze_baseline,
    build_baseline_export_tables,
)


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


def test_build_baseline_export_tables_contains_summary_and_samples():
    records = [
        BaselineExportRecord(
            elapsed_s=0.0,
            voltage_v=1.0,
            raw_code=100,
            status=0x01,
            tca_channel=2,
            valid=True,
        ),
        BaselineExportRecord(
            elapsed_s=1.0,
            voltage_v=1.1,
            raw_code=110,
            status=0x01,
            tca_channel=2,
            valid=True,
        ),
        BaselineExportRecord(
            elapsed_s=2.0,
            voltage_v=1.2,
            raw_code=120,
            status=0x08,
            tca_channel=2,
            valid=False,
        ),
    ]
    metrics = analyze_baseline(
        [BaselineSample(timestamp_s=r.elapsed_s, voltage=r.voltage_v) for r in records if r.valid],
        warmup_s=0.0,
    )

    tables = build_baseline_export_tables(
        records=records,
        metrics=metrics,
        duration_min=30,
        warmup_s=0,
        started_at="2026-05-14 16:00:00",
        finished_at="2026-05-14 16:01:00",
    )

    assert tables.summary[0] == ("field", "value")
    assert ("sample_count", 2) in tables.summary
    assert ("drift_v", pytest.approx(0.1)) in tables.summary
    assert tables.samples[0] == (
        "sample_index",
        "elapsed_s",
        "voltage_v",
        "raw_code",
        "status",
        "tca_channel",
        "valid",
    )
    assert tables.samples[1] == (1, pytest.approx(0.0), pytest.approx(1.0), 100, 0x01, 2, True)
    assert tables.samples[3] == (3, pytest.approx(2.0), pytest.approx(1.2), 120, 0x08, 2, False)
