import pytest

from src.core.serial_diagnostics import (
    CommandRttTracker,
    parse_ads_health_line,
    parse_detector_debug_line,
)


def test_parse_detector_debug_lines():
    assert parse_detector_debug_line("LOOP_GAP_ACTIVE_MAX_US:87") == (
        "loop_gap_active_max_us",
        87,
    )
    assert parse_detector_debug_line("ANGLE_AGE_MS:12") == ("angle_age_ms", 12)
    assert parse_detector_debug_line("CMD_OK") is None


def test_parse_ads_health_line_uses_same_counter_names_as_jetson():
    assert parse_ads_health_line(
        "ADS_HEALTH:SUCCESS=100,MUTEX_TIMEOUT=2,I2C_ERROR=1,"
        "CRC_ERROR=3,DUPLICATE=4,TRANSIENT_DROP=5"
    ) == {
        "success": 100,
        "mutex_timeout": 2,
        "i2c_error": 1,
        "crc_error": 3,
        "duplicate": 4,
        "transient_drop": 5,
    }
    assert parse_ads_health_line("ADS_HEALTH:SUCCESS=bad") is None
    assert parse_ads_health_line("CMD_OK") is None


def test_command_rtt_tracker_reports_first_response_latency():
    tracker = CommandRttTracker()

    tracker.record("XEFR90P0.5", now_s=10.0)
    result = tracker.finish("CMD_OK", now_s=10.037)

    assert result is not None
    assert result.command == "XEFR90P0.5"
    assert result.response == "CMD_OK"
    assert result.rtt_ms == pytest.approx(37.0)
    assert tracker.finish("PID_DONE:X", now_s=10.5) is None
