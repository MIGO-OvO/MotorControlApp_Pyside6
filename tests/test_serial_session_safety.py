import types
import threading

import pytest
import serial
from PySide6.QtCore import QCoreApplication

from src.core.pid_optimizer import PatternSearchOptimizer
from src.ui.mixins.serial_mixin import QMessageBox, SerialMixin


def test_closing_session_cancels_automation_and_optimizer_without_thread_termination():
    stopped = []
    owner = types.SimpleNamespace(
        automation_thread=types.SimpleNamespace(stop=lambda: stopped.append('automation')),
        pid_optimizer=types.SimpleNamespace(stop=lambda: stopped.append('optimizer')),
        _single_test_active=True,
    )
    SerialMixin._stop_control_jobs(owner)
    assert stopped == ['automation', 'optimizer']
    assert not owner._single_test_active


class FakeSerial:
    def __init__(self, fail_writes=False):
        self.is_open = True
        self.fail_writes = fail_writes
        self.writes = []
        self.close_count = 0

    def write(self, data):
        self.writes.append(data)
        if self.fail_writes:
            raise serial.SerialException('fake unplugged device')

    def flush(self):
        pass

    def close(self):
        self.is_open = False
        self.close_count += 1


class TooManyCloseCalls(BaseException):
    """Bound a recursion regression without waiting for Python's stack limit."""


class SessionOwner(SerialMixin):
    def __init__(self, port):
        self.serial_port = port
        self.serial_lock = threading.Lock()
        self.serial_reader = None
        self.automation_thread = None
        self.pid_optimizer = PatternSearchOptimizer()
        self.pid_optimizer.set_send_callback(self.send_command)
        self.close_calls = 0
        self.logs = []
        self.connect_btn = types.SimpleNamespace(setText=lambda _value: None)
        self.status_bar = types.SimpleNamespace(showMessage=lambda _value: None)

    def close_serial(self):
        self.close_calls += 1
        if self.close_calls > 4:
            raise TooManyCloseCalls()
        return super().close_serial()

    def log(self, message):
        self.logs.append(message)


@pytest.fixture
def qt_core_app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_write_failure_closes_once_without_optimizer_callback_recursion(monkeypatch, qt_core_app):
    dialogs = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: dialogs.append(args))
    port = FakeSerial(fail_writes=True)
    owner = SessionOwner(port)

    try:
        result = owner.send_command('PUMP:ON')
    except TooManyCloseCalls:
        pytest.fail('close_serial recursively re-entered through optimizer.stop')

    assert result is False
    assert owner.close_calls == 1
    assert owner.pid_optimizer._stop_requested
    assert port.writes == [b'PUMP:ON\r\n', b'STOPALL\r\n']
    assert port.close_count == 1
    assert owner.serial_port is None
    assert len(dialogs) == 1


def test_disconnected_close_is_idempotent_and_never_prompts_to_connect(monkeypatch, qt_core_app):
    dialogs = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: dialogs.append(args))
    port = FakeSerial()
    owner = SessionOwner(port)
    owner.close_serial()
    owner.close_serial()

    assert dialogs == []
    assert owner.pid_optimizer._stop_requested
    assert port.close_count == 1
    assert port.writes == [b'STOPALL\r\n', b'ANGLESTREAM_STOP\r\n']


def test_job_stop_failure_does_not_skip_stopall_or_port_cleanup(qt_core_app):
    port = FakeSerial()
    owner = SessionOwner(port)

    def fail_stop():
        raise RuntimeError('fake job cleanup failure')

    owner.automation_thread = types.SimpleNamespace(stop=fail_stop)
    owner.close_serial()

    assert owner.pid_optimizer._stop_requested
    assert port.writes[0] == b'STOPALL\r\n'
    assert port.close_count == 1
    assert owner.serial_port is None


def test_window_close_flag_still_allows_explicit_sensor_stop_before_teardown(qt_core_app):
    port = FakeSerial()
    owner = SessionOwner(port)
    # closeEvent sets this data-delivery flag before _spectro_stop_measurement.
    owner._closing = True

    assert owner.send_command('ADSSTOP') is True
    assert port.writes == [b'ADSSTOP\r\n']
