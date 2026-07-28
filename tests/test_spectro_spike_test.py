import csv
import io

import pytest

from src.core.spectro_spike_test import (
    SpectroSpikeTest,
    build_spike_test_summary_csv,
)


def test_spike_test_counts_session_drops_and_counter_deltas():
    test = SpectroSpikeTest()
    test.start(
        started_at_ms=1000,
        counters={"crc_error": 1, "duplicate": 10, "transient_drop": 2},
    )

    for timestamp_ms, voltage in (
        (1000, 1.000),
        (1050, 0.994),
        (1100, 1.000),
        (1150, 0.989),
        (1200, 1.000),
        (1250, 0.979),
        (1300, 1.000),
    ):
        test.add_sample(timestamp_ms=timestamp_ms, voltage=voltage, valid=True)

    test.stop(
        ended_at_ms=1350,
        counters={"crc_error": 1, "duplicate": 13, "transient_drop": 4},
    )
    summary = test.summary()

    assert summary.active is False
    assert summary.duration_s == pytest.approx(0.35)
    assert summary.sample_count == 7
    assert summary.receive_rate_hz == pytest.approx(20.0)
    assert summary.drop_count_5mv == 3
    assert summary.drop_count_10mv == 2
    assert summary.drop_count_20mv == 1
    assert summary.max_down_mv == pytest.approx(21.0)
    assert summary.ads_crc_error_delta == 0
    assert summary.ads_duplicate_delta == 3
    assert summary.ads_transient_drop_delta == 2
    assert summary.counter_reset_detected is False


def test_spike_test_ignores_invalid_samples_and_marks_counter_reset():
    test = SpectroSpikeTest()
    test.start(
        started_at_ms=2000,
        counters={"crc_error": 3, "duplicate": 20, "transient_drop": 8},
    )
    test.add_sample(timestamp_ms=2000, voltage=1.0, valid=True)
    test.add_sample(timestamp_ms=2050, voltage=0.0, valid=False)
    test.add_sample(timestamp_ms=2100, voltage=float("nan"), valid=True)
    test.add_sample(timestamp_ms=2150, voltage=0.995, valid=True)
    test.update_counters({"crc_error": 0, "duplicate": 2, "transient_drop": 1})

    summary = test.summary(now_ms=2200)

    assert summary.sample_count == 2
    assert summary.drop_count_5mv == 0
    assert summary.ads_crc_error_delta is None
    assert summary.ads_duplicate_delta is None
    assert summary.ads_transient_drop_delta is None
    assert summary.counter_reset_detected is True


def test_spike_test_summary_csv_uses_cross_platform_columns():
    test = SpectroSpikeTest()
    test.start(
        started_at_ms=1000,
        target_duration_s=30,
        counters={"crc_error": 0},
    )
    test.add_sample(timestamp_ms=1000, voltage=1.0)
    test.stop(ended_at_ms=1100, counters={"crc_error": 0})

    csv_text = build_spike_test_summary_csv(
        test.summary(),
        session_id="windows-test",
        transport_path="windows_direct",
    )
    rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))

    assert rows[0]["session_id"] == "windows-test"
    assert rows[0]["transport_path"] == "windows_direct"
    assert rows[0]["sample_count"] == "1"
    assert rows[0]["target_duration_s"] == "30"
    assert "ads_transient_drop_delta" in rows[0]


def test_spike_test_uses_a_fixed_deadline_and_ignores_late_samples():
    test = SpectroSpikeTest()
    test.start(
        started_at_ms=1000,
        target_duration_s=30,
        counters={"crc_error": 0},
    )
    test.add_sample(timestamp_ms=1000, voltage=1.000)

    assert test.deadline_ms == 31000
    assert test.should_auto_stop(30999) is False
    assert test.should_auto_stop(31000) is True

    running = test.summary(now_ms=16000)
    assert running.target_duration_s == 30
    assert running.remaining_s == pytest.approx(15.0)
    assert running.sample_count == 1

    test.add_sample(timestamp_ms=30999, voltage=0.990)
    test.add_sample(timestamp_ms=31001, voltage=0.900)

    test.stop(ended_at_ms=32000, counters={"crc_error": 0})
    completed = test.summary()
    assert completed.ended_at_ms == 31000
    assert completed.duration_s == pytest.approx(30.0)
    assert completed.remaining_s == 0.0
    assert completed.sample_count == 2
