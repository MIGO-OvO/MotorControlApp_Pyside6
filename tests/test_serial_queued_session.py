"""Real Qt queued delivery across production serial close/reconnect paths.

The serial device is fake; Qt, SerialReader, its parser and lifecycle are real.
This is a deterministic offline condition test, not a field reproduction.
"""

import threading
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QThread, QTimer, Qt
from PySide6.QtWidgets import QApplication

from src.ui.mixins import serial_mixin
from src.ui.mixins.serial_mixin import SerialMixin
from src.ui.mixins.spectro_mixin import SpectroMixin


class Label:
    def setText(self, value):
        self.value = value

    def text(self):
        return self.value

    def setEnabled(self, value):
        self.enabled = value


class QueuedPort:
    def __init__(self):
        self.is_open = False
        self.pending = bytearray()
        self.lock = threading.Lock()
        self.writes = []

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def reset_input_buffer(self):
        with self.lock:
            self.pending.clear()

    def reset_output_buffer(self):
        pass

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        pass

    @property
    def in_waiting(self):
        with self.lock:
            return len(self.pending)

    def read(self, size):
        with self.lock:
            result = bytes(self.pending[:size])
            del self.pending[:size]
            return result

    def feed(self, data):
        with self.lock:
            self.pending.extend(data)


class QueuedSessionOwner(QObject, SerialMixin, SpectroMixin):
    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.serial_reader = None
        self.serial_lock = threading.Lock()
        self.automation_thread = None
        self.pid_optimizer = None
        self._closing = False
        self.received = []
        self.callback_threads = []
        self.port_combo = SimpleNamespace(currentText=lambda: "FAKE")
        self.baud_combo = SimpleNamespace(currentText=lambda: "115200")
        self.connect_btn = Label()
        self.status_bar = SimpleNamespace(showMessage=lambda _message: None)
        self.spectro_start_btn = Label()
        self.spectro_status_label = Label()
        self.spectro_ref_btn = Label()
        self._spectro_start_ack_timer = QTimer(self)
        self._spectro_stop_ack_timer = QTimer(self)
        self.spectro_timer = QTimer(self)

    @staticmethod
    def _perform_handshake(_port):
        return True, "DET_ID:USV_DETECTOR;CAP=WATCHDOG1"

    def _sync_i2c_mapping(self):
        pass

    def log(self, _message):
        pass

    def record(self, kind, packet):
        # Match the production handler's teardown guard. It is false again
        # after open_serial(), so it cannot identify a retired reader.
        if self._closing:
            return
        self.received.append((kind, packet))
        self.callback_threads.append(QThread.currentThread())

    def handle_serial_data(self, line):
        self.record("text", line)
        if not self._closing:
            self._spectro_handle_ads_reply(line)

    def handle_pid_packet(self, packet):
        self.record("pid", packet)

    def handle_test_result_packet(self, packet):
        self.record("test", packet)

    def handle_angle_packet(self, packet):
        self.record("angle", packet)

    def handle_spectro_packet(self, packet):
        self.record("spectro", packet)

    def handle_health_packet(self, packet):
        self.record("health", packet)


def all_packet_types():
    result = bytearray(b"ADS_OK:STOP\r\n")
    for kind, size in ((0xAA, 29), (0xBB, 18), (0xCC, 20), (0xDD, 18), (0xEE, 37)):
        frame = bytearray(size)
        frame[0:2] = bytes((0x55, kind))
        frame[-1] = 0x0A
        # PID/test checksums exclude the subtype; other production frames
        # include it. The actual SerialReader validates and parses every frame.
        for value in frame[2 if kind in (0xAA, 0xBB) else 1 : -2]:
            frame[-2] ^= value
        result.extend(frame)
    return bytes(result)


def enqueue_and_wait_for_reader(owner):
    parsed = threading.Event()
    owner.serial_reader.health_packet_received.connect(
        lambda _packet: parsed.set(), Qt.ConnectionType.DirectConnection
    )
    owner.serial_port.feed(all_packet_types())
    assert parsed.wait(2.0), "production SerialReader did not parse the input"


@pytest.fixture
def queued_owner(monkeypatch):
    app = QApplication.instance() or QApplication([])
    dialogs = []
    monkeypatch.setattr(serial_mixin.serial, "Serial", QueuedPort)
    monkeypatch.setattr(
        serial_mixin.QMessageBox, "critical", lambda *args: dialogs.append(args)
    )
    owner = QueuedSessionOwner()
    owner.open_serial()
    assert owner.serial_reader is not None
    assert dialogs == []
    try:
        yield app, owner
    finally:
        owner.close_serial()
        app.processEvents()


def test_old_queued_reader_data_cannot_enter_reconnected_session(queued_owner):
    app, owner = queued_owner
    old_reader = owner.serial_reader
    enqueue_and_wait_for_reader(owner)
    assert owner.received == []  # The UI event loop has not dispatched yet.

    owner.close_serial()  # Production disconnect() and reader.stop()/wait().
    owner.open_serial()
    assert owner.serial_reader is not old_reader
    owner._spectro_stop_pending = True  # A new-session STOP transaction.
    owner._spectro_stop_unknown = True
    owner._spectro_stop_ack_timer.start(2500)
    app.processEvents()

    assert owner.received == [], "retired reader callbacks reached the new session"
    assert owner._spectro_stop_pending
    assert owner._spectro_stop_unknown
    assert owner._spectro_stop_ack_timer.isActive()

    enqueue_and_wait_for_reader(owner)
    app.processEvents()
    assert [kind for kind, _packet in owner.received] == [
        "text", "pid", "test", "angle", "spectro", "health"
    ]
    assert all(thread is owner.thread() for thread in owner.callback_threads)
    assert not owner._spectro_stop_pending
    assert not owner._spectro_stop_unknown


def test_queued_reader_data_is_ignored_while_closed(queued_owner):
    app, owner = queued_owner
    enqueue_and_wait_for_reader(owner)
    owner.close_serial()
    app.processEvents()
    assert owner.received == []
    assert owner._spectro_stop_unknown
