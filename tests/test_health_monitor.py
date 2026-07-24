from datetime import datetime

import pytest

from src.core.health_monitor import CSV_COLUMNS, HealthHistory


def _health_packet():
    return {
        "timestamp_ms": 987654,
        "uptime_s": 321,
        "temp_c": 42.3,
        "cpu_freq_mhz": 160,
        "heap_free": 123456,
        "heap_min_free": 100000,
        "heap_total": 200000,
        "heap_free_pct": 61.728,
        "task_count": 9,
        "loop_stack_hwm": 4096,
        "comms_stack_hwm": 6144,
        "sensors_stack_hwm": 3072,
    }


def test_health_history_records_packet_fields_and_csv_row():
    ticks = iter([100.0])
    history = HealthHistory(time_provider=lambda: next(ticks))

    sample = history.append_packet(
        _health_packet(),
        host_time=datetime(2026, 6, 3, 12, 0, 1, 234000),
    )

    assert sample.device_timestamp_ms == 987654
    assert sample.uptime_s == 321
    assert sample.temp_c == pytest.approx(42.3)
    assert sample.cpu_freq_mhz == 160
    assert sample.heap_free == 123456
    assert sample.heap_min_free == 100000
    assert sample.heap_total == 200000
    assert sample.heap_free_pct == pytest.approx(61.728)
    assert sample.task_count == 9
    assert sample.loop_stack_hwm == 4096
    assert sample.comms_stack_hwm == 6144
    assert sample.sensors_stack_hwm == 3072

    rows = history.build_csv_rows()
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert rows[0]["host_time"] == "2026-06-03T12:00:01.234"
    assert rows[0]["device_timestamp_ms"] == "987654"
    assert rows[0]["cpu_freq_mhz"] == "160"
    assert rows[0]["heap_free_pct"] == "61.728"
    assert rows[0]["loop_gap_active_max_us"] == ""


def test_health_history_updates_latest_sample_with_debug_and_rtt():
    ticks = iter([10.0, 10.5])
    history = HealthHistory(time_provider=lambda: next(ticks))

    history.append_packet(_health_packet(), host_time=datetime(2026, 6, 3, 12, 0, 0))
    history.update_debug_value("loop_gap_active_max_us", 87)
    history.update_debug_value("angle_age_ms", 12)
    history.update_ads_counters(
        {
            "success": 100,
            "mutex_timeout": 2,
            "i2c_error": 1,
            "crc_error": 3,
            "duplicate": 4,
            "transient_drop": 5,
        }
    )
    history.update_command_rtt(37.4)

    latest = history.latest
    assert latest is not None
    assert latest.loop_gap_active_max_us == 87
    assert latest.angle_age_ms == 12
    assert latest.ads_success == 100
    assert latest.ads_mutex_timeout == 2
    assert latest.ads_i2c_error == 1
    assert latest.ads_crc_error == 3
    assert latest.ads_duplicate == 4
    assert latest.ads_transient_drop == 5
    assert latest.command_rtt_ms == pytest.approx(37.4)

    history.append_packet(_health_packet(), host_time=datetime(2026, 6, 3, 12, 0, 1))
    assert history.latest is not None
    assert history.latest.loop_gap_active_max_us is None
    assert history.latest.ads_crc_error is None
    assert history.latest.command_rtt_ms is None


def test_health_history_can_export_csv(tmp_path):
    history = HealthHistory(time_provider=lambda: 1.0)
    history.append_packet(_health_packet(), host_time=datetime(2026, 6, 3, 12, 0, 0))
    path = tmp_path / "health.csv"

    history.export_csv(path)

    text = path.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert "2026-06-03T12:00:00.000" in text
    assert ",160," in text
    assert "ads_crc_error" in text.splitlines()[0]
    assert "ads_transient_drop" in text.splitlines()[0]
