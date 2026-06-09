import struct

import pytest

from src.hardware.serial_reader import SerialReader


class DummySerial:
    is_open = False


def _build_spectro_packet(
    timestamp_ms: int,
    tca_channel: int,
    status: int,
    raw_code: int,
    voltage: float,
) -> bytes:
    payload = struct.pack(
        "<BIBBif",
        SerialReader.HEADER2_SPECTRO,
        timestamp_ms,
        tca_channel,
        status,
        raw_code,
        voltage,
    )

    checksum = 0
    for value in payload:
        checksum ^= value

    return bytes([SerialReader.HEADER1]) + payload + bytes([checksum, SerialReader.TAIL])


def _build_health_packet() -> bytes:
    payload = struct.pack(
        "<BBBIIhHIIIBHHH",
        SerialReader.HEADER2_HEALTH,
        1,
        0x03,
        987654,
        321,
        423,
        160,
        123456,
        100000,
        200000,
        9,
        4096,
        6144,
        3072,
    )

    checksum = 0
    for value in payload:
        checksum ^= value

    return bytes([SerialReader.HEADER1]) + payload + bytes([checksum, SerialReader.TAIL])


def test_serial_reader_parses_mixed_spectro_packet_and_text():
    reader = SerialReader(DummySerial())
    received_packets = []
    received_text = []

    reader.spectro_packet_received.connect(received_packets.append)
    reader.data_received.connect(received_text.append)

    packet = _build_spectro_packet(
        timestamp_ms=123456,
        tca_channel=2,
        status=0x01,
        raw_code=-654321,
        voltage=1.2345,
    )

    assert len(packet) == SerialReader.PACKET_SIZE_SPECTRO == 18
    assert reader._validate_packet(
        packet,
        SerialReader.HEADER2_SPECTRO,
        SerialReader.PACKET_SIZE_SPECTRO,
    )

    reader._process_data(packet[:7])
    assert received_packets == []
    assert received_text == []

    reader._process_data(packet[7:] + b"ADS_OK:STOP\n")

    assert received_text == ["ADS_OK:STOP"]
    assert len(received_packets) == 1

    parsed = received_packets[0]
    assert parsed["timestamp_ms"] == 123456
    assert parsed["tca_channel"] == 2
    assert parsed["status"] == 0x01
    assert parsed["raw_code"] == -654321
    assert parsed["voltage"] == pytest.approx(1.2345, abs=1e-6)


def test_serial_reader_parses_health_packet():
    reader = SerialReader(DummySerial())
    received_packets = []

    reader.health_packet_received.connect(received_packets.append)

    packet = _build_health_packet()

    assert len(packet) == SerialReader.PACKET_SIZE_HEALTH == 37
    assert reader._validate_packet(
        packet,
        SerialReader.HEADER2_HEALTH,
        SerialReader.PACKET_SIZE_HEALTH,
    )

    reader._process_data(packet[:11])
    assert received_packets == []

    reader._process_data(packet[11:])

    assert len(received_packets) == 1
    parsed = received_packets[0]
    assert parsed["version"] == 1
    assert parsed["flags"] == 0x03
    assert parsed["timestamp_ms"] == 987654
    assert parsed["uptime_s"] == 321
    assert parsed["temp_c"] == pytest.approx(42.3)
    assert parsed["cpu_freq_mhz"] == 160
    assert parsed["heap_free"] == 123456
    assert parsed["heap_min_free"] == 100000
    assert parsed["heap_total"] == 200000
    assert parsed["heap_free_pct"] == pytest.approx(61.728)
    assert parsed["task_count"] == 9
    assert parsed["loop_stack_hwm"] == 4096
    assert parsed["comms_stack_hwm"] == 6144
    assert parsed["sensors_stack_hwm"] == 3072
