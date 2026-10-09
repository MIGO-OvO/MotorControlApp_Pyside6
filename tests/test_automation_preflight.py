import threading
import weakref
import re
import time

import pytest

from src.core.automation_engine import AutomationThread
from src.core.automation_preflight import PreflightFeedback, PreflightError, calibrated_offsets
from src.config.settings import SettingsManager


class Serial:
    is_open = True

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data.decode())

    def flush(self):
        pass


class Parent:
    def log(self, message):
        pass


def job():
    parent, serial = Parent(), Serial()
    thread = AutomationThread(weakref.ref(parent), [], 1, serial, threading.Lock())
    thread._execute_loop = lambda: thread._running.clear()
    return parent, serial, thread


def test_preparation_runs_before_injection():
    parent, serial, thread = job()
    thread.on_startup_prepare = lambda steps: serial.writes.append('prepared') or True
    thread.run()
    assert serial.writes.index('prepared') < next(
        i for i, text in enumerate(serial.writes) if text.startswith('PUMP:SET:'))


def test_stop_before_worker_start_cannot_restart_injection():
    parent, serial, thread = job()
    thread.safe_stop()
    thread.run()
    assert not any(text.startswith('PUMP:SET:') for text in serial.writes)


def test_failed_preparation_never_starts_injection():
    parent, serial, thread = job()
    thread.on_startup_prepare = lambda steps: False
    thread.run()
    assert not any(text.startswith('PUMP:SET:') for text in serial.writes)


class Detector(Serial):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.omit_ack = None
        self.fail_phase = None
        self.block_phase = None
        self.feedback = PreflightFeedback()
        self.feedback.update_angles({'X': 150.0, 'A': 18.0})
        self.feedback.update_health({'timestamp_ms': 1000})
        self.feedback.update_text('ANGLE_AGE_CH_MS:1,1,1,1')

    def write(self, data):
        super().write(data)
        text = data.decode().strip()
        preflight = self.thread.preflight
        phase = preflight.snapshot()['phase']
        reply = self.thread.notify_text
        if text == 'PIDQUERY':
            reply('PIDPARAM:0.14,0.015,0.06,1,8')
        elif text == 'PUMP:OFF':
            reply('PUMP_OK:OFF')
        elif text.startswith('PUMP:SET:'):
            if self.omit_ack != 'injection':
                reply('PUMP_OK:SET=50,ON')
        elif re.match('[XYZA]E[FB]R', text):
            for axis, direction, delta in re.findall(r'([XYZA])E([FB])R([\d.]+)P[\d.]+', text):
                reply('PID_START:%s,delta=%.1f,dir=%s,prec=0.1' % (axis, float(delta), direction))
                if self.block_phase == phase and phase != 'separating':
                    continue
                reply('PID_FAIL:%s=SENSOR_ERR' % axis if self.fail_phase == phase else
                      'PID_DONE:%s,abs=360.0,err=0.01' % axis)
            if self.omit_ack != phase:
                reply('CMD_OK')
        elif text.startswith('AEFV'):
            reply('CMD_OK')
            if self.block_phase != 'separating':
                for _ in range(8):
                    with preflight.lock:
                        preflight.travel['at'] -= 0.75
                        angle = (preflight.travel['angle'] + 90) % 360
                    self.feedback.update_angles({'A': angle})
                    preflight.notify_angles({'A': angle})
        else:
            reply('CMD_OK')


def prepared_job(**options):
    parent, serial = Parent(), Detector()
    thread = AutomationThread(weakref.ref(parent), [{'X': {'enable': 'E'}}],
                              1, serial, threading.Lock())
    serial.thread = thread
    for key, value in options.items():
        setattr(serial, key, value)
    thread.configure_preflight({'X': 123.0},
        {'oil_axis': 'A', 'separation_turns': 2, 'separation_rpm': 20}, serial.feedback)
    thread._execute_loop = lambda: serial.writes.append('engine') or thread._running.clear()
    return parent, serial, thread


def test_feedback_order_saved_zero_full_turns_oil_then_injection_then_engine():
    parent, serial, thread = prepared_job()
    thread.run()
    commands = [text.strip() for text in serial.writes]
    assert commands.index('PUMP:OFF') < commands.index('XEBR27.000P0.1')
    assert commands.index('XEBR27.000P0.1') < commands.index('XEFR360.000P0.1')
    assert commands.index('AEFR0.000P0.1') < commands.index('AEFV20J720.000')
    assert commands.index('AEFV20J720.000') < commands.index('PUMP:SET:50') < commands.index('engine')
    assert commands.count('PUMP:SET:50') == 1
    assert thread._preflight_zeros == {'X': 123.0}
    assert not any(text.startswith('CAL') for text in commands)
    assert thread.preflight.snapshot()['travel_degrees'] == 720


@pytest.mark.parametrize('phase', ['homing', 'compensating', 'separating'])
def test_pid_failure_never_enters_engine_or_starts_injection(phase):
    parent, serial, thread = prepared_job(fail_phase=phase)
    thread.run()
    assert thread.terminal_error
    assert 'engine' not in serial.writes
    assert not any(text.startswith('PUMP:SET:') for text in serial.writes)
    assert 'STOPALL\r\n' in serial.writes


@pytest.mark.parametrize('phase', ['homing', 'compensating', 'injection'])
def test_ack_is_required_even_if_pid_reports_done(monkeypatch, phase):
    parent, serial, thread = prepared_job(omit_ack=phase)
    monkeypatch.setattr(thread.preflight, 'ACK_TIMEOUT', 0.01)
    thread.run()
    assert 'engine' not in serial.writes
    assert 'ACK timeout' in thread.terminal_error
    assert 'STOPALL\r\n' in serial.writes


@pytest.mark.parametrize('phase', ['homing', 'compensating', 'separating'])
def test_stop_during_preparation_never_dispatches_later_motion(phase):
    parent, serial, thread = prepared_job(block_phase=phase)
    worker = threading.Thread(target=thread.run)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if thread.preflight.snapshot()['phase'] == phase and (
                    thread.preflight.pending or thread.preflight.travel):
                break
            time.sleep(0.005)
        else:
            pytest.fail('Preparation did not reach ' + phase)
        thread.safe_stop()
        stop_index = serial.writes.index('STOPALL\r\n')
        worker.join(1)
        assert not worker.is_alive()
        assert 'engine' not in serial.writes
        assert all(not text.startswith(('PUMP:SET:', 'XE', 'AE'))
                   for text in serial.writes[stop_index + 1:])
    finally:
        thread.safe_stop()
        worker.join(1)


def test_oil_frozen_feedback_fails_closed(monkeypatch):
    parent, serial, thread = prepared_job(block_phase='separating')
    monkeypatch.setattr(thread.preflight, 'PROGRESS_TIMEOUT', 0.01)
    thread.run()
    assert 'forward progress' in thread.terminal_error
    assert 'engine' not in serial.writes
    assert not any(text.startswith('PUMP:SET:') for text in serial.writes)


def test_zero_marker_distinguishes_default_and_explicit_zero(tmp_path):
    settings = SettingsManager(str(tmp_path / 'settings.json'))
    assert calibrated_offsets({'offsets': {'X': 0}}) == {}
    settings.set_angle_offset('X', 0.0)
    assert calibrated_offsets({'offsets': settings.get_angle_offsets(),
        'configured_axes': settings.get('motor.zero_configured_axes')}) == {'X': 0.0}
    settings.reset_angle_offsets()
    assert settings.get('motor.zero_configured_axes') == []


def test_health_timestamp_does_not_accept_duplicates_and_wraps(monkeypatch):
    import src.core.automation_preflight as module
    now = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    feedback = PreflightFeedback()
    feedback.update_health({'timestamp_ms': 2**32 - 1})
    now[0] = 11
    feedback.update_health({'timestamp_ms': 1})
    feedback.update_angles({'A': 0})
    assert feedback.read(['A'], require_health=True)['A'] == 0
    now[0] = 14
    feedback.update_health({'timestamp_ms': 1})
    feedback.update_angles({'A': 0})
    with pytest.raises(PreflightError, match='健康时钟'):
        feedback.read(['A'], require_health=True)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 361, True])
def test_invalid_angle_is_rejected(value):
    feedback = PreflightFeedback()
    feedback.update_angles({'X': value})
    with pytest.raises(PreflightError):
        feedback.read(['X'])


def test_pid_ack_and_same_wrapped_angle_are_not_completion():
    parent, serial, thread = prepared_job(block_phase='compensating')
    worker = threading.Thread(target=thread.run)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and thread.preflight.snapshot()['phase'] != 'compensating':
            time.sleep(0.005)
        assert thread.preflight.snapshot()['phase'] == 'compensating'
        thread.preflight.notify_angles({'X': 123})
        assert 'engine' not in serial.writes
        assert not any(text.startswith('PUMP:SET:') for text in serial.writes)
        thread.notify_text('PID_DONE:X,abs=360,err=0')
        worker.join(1)
        assert not worker.is_alive()
        assert 'engine' in serial.writes
    finally:
        thread.safe_stop()
        worker.join(1)


def test_pending_send_waiting_on_serial_lock_cannot_survive_stop():
    parent, serial, thread = prepared_job()
    worker = threading.Thread(target=thread.run)
    # Force the worker to wait for the port; stop owns cancellation before release.
    with thread.lock:
        worker.start()
        thread._running.clear()
        thread.preflight.cancel()
    thread.safe_stop()
    worker.join(1)
    assert not worker.is_alive()
    assert all(not text.startswith(('XE', 'AE', 'PUMP:SET:')) for text in serial.writes)


def test_missing_zero_is_rejected_before_any_write():
    parent, serial, thread = job()
    thread.steps = [{'X': {'enable': 'E'}}]
    with pytest.raises(ValueError):
        thread.configure_preflight({}, {}, PreflightFeedback())
    assert serial.writes == []


def test_channel_age_rejects_fresh_but_invalid_cached_angle():
    feedback = PreflightFeedback()
    feedback.update_angles({'A': 18.0})
    feedback.update_text('ANGLE_AGE_CH_MS:1,1,1,2000')
    with pytest.raises(PreflightError):
        feedback.read(['A'])


def test_ui_packet_hooks_feed_preparation_and_zero_is_explicit(monkeypatch, tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from src.ui.main_window_complete import MotorControlApp
    monkeypatch.chdir(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MotorControlApp()
    try:
        assert window.auto_separation_turns.value() == 0
        assert window.auto_oil_axis.currentData() is None
        window.handle_angle_packet({'X': 0.0, 'Y': 30.0, 'Z': 0.0, 'A': 18.0})
        window.handle_health_packet({'timestamp_ms': 1000})
        window.handle_serial_data('ANGLE_AGE_CH_MS:1,1,1,1')
        assert window._automation_feedback.read(['X'], require_health=True)['X'] == 0
        window.set_current_as_zero('X')
        assert window.settings_manager.get('motor.zero_configured_axes') == ['X']
        window._set_automation_running_state(True)
        assert not window.auto_separation_turns.isEnabled()
        window._set_automation_running_state(False)
        assert window.auto_separation_turns.isEnabled()
    finally:
        window.close()
        app.processEvents()


def test_old_ui_cleanup_does_not_cancel_new_thread():
    from types import SimpleNamespace
    from src.ui.mixins.automation_mixin import AutomationMixin
    replacement = object()
    owner = SimpleNamespace(automation_thread=replacement)
    AutomationMixin._cleanup_automation_thread(owner, object())
    assert owner.automation_thread is replacement
    AutomationMixin._handle_automation_error_delayed(owner, 'old error', object())
    assert owner.automation_thread is replacement
