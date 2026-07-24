import csv

import pytest

from src.config.constants import DEFAULT_ADS_CONFIG
from src.core.spectro_trace import (
    JETSON_COMPATIBLE_COLUMNS,
    SpectroTraceRecorder,
    compare_spectro_csv,
    summarize_spectro_csv,
)


def test_windows_default_publish_rate_matches_jetson_for_path_comparison():
    assert DEFAULT_ADS_CONFIG["adc_rate"] == 90
    assert DEFAULT_ADS_CONFIG["publish_rate"] == 20


def test_trace_export_starts_with_jetson_raw_csv_columns(tmp_path):
    recorder = SpectroTraceRecorder(transport_path="windows_direct")
    recorder.start_session("windows-test")
    recorder.append_packet(
        {
            "timestamp_ms": 1000,
            "tca_channel": 2,
            "status": 0x01,
            "raw_code": 123,
            "voltage": 1.035,
        },
        received_at_ms=10_000,
        elapsed_s=0.0,
        absorbance=0.0,
        ads_counters={"crc_error": 1, "transient_drop": 2},
    )
    recorder.append_packet(
        {
            "timestamp_ms": 1050,
            "tca_channel": 2,
            "status": 0x01,
            "raw_code": 124,
            "voltage": 1.034,
        },
        received_at_ms=10_052,
        elapsed_s=0.052,
        absorbance=0.001,
        ads_counters={"crc_error": 1, "transient_drop": 2},
    )

    output = tmp_path / "windows.csv"
    recorder.export_csv(output)

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        assert handle.closed is False

    assert list(rows[0])[: len(JETSON_COMPATIBLE_COLUMNS)] == JETSON_COMPATIBLE_COLUMNS
    assert rows[0]["transport_path"] == "windows_direct"
    assert rows[0]["source_timestamp_ms"] == "1000"
    assert rows[0]["valid"] == "True"
    assert rows[1]["host_interarrival_ms"] == "52"
    assert rows[1]["source_delta_ms"] == "50"
    assert rows[1]["ads_crc_error"] == "1"
    assert rows[1]["ads_transient_drop"] == "2"


def test_trace_comparison_reports_transport_and_signal_differences(tmp_path):
    windows_path = tmp_path / "windows.csv"
    jetson_path = tmp_path / "jetson.csv"
    columns = JETSON_COMPATIBLE_COLUMNS

    with windows_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(
            [
                _row(0, 1000, 0, 1.035, 100),
                _row(1, 1050, 50, 1.034, 101),
                _row(2, 1100, 100, 1.036, 102),
            ]
        )

    with jetson_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(
            [
                _row(0, 2000, 0, 1.035, 100),
                _row(1, 2055, 50, 1.034, 101),
                _row(2, 2115, 100, 1.036, 102),
            ]
        )

    windows = summarize_spectro_csv(windows_path)
    jetson = summarize_spectro_csv(jetson_path)
    comparison = compare_spectro_csv(windows_path, jetson_path)

    assert windows.sample_count == 3
    assert windows.receive_rate_hz == pytest.approx(20.0)
    assert windows.host_interval_p95_ms == pytest.approx(50.0)
    assert jetson.host_interval_p95_ms == pytest.approx(60.0)
    assert comparison.voltage_mean_delta_v == pytest.approx(0.0)
    assert comparison.host_interval_p95_delta_ms == pytest.approx(10.0)


def test_trace_comparison_rejects_non_spectro_csv(tmp_path):
    output = tmp_path / "wrong.csv"
    output.write_text("time,value\n1,2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Jetson 兼容字段"):
        summarize_spectro_csv(output)


def _row(index, received_at_ms, source_timestamp_ms, voltage, raw_code):
    return {
        "frame_index": index,
        "received_at_ms": received_at_ms,
        "source_timestamp_ms": source_timestamp_ms,
        "voltage": voltage,
        "absorbance": 0.0,
        "raw_code": raw_code,
        "valid": True,
        "status": "acquiring",
    }
