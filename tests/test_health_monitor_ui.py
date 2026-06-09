import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.ui.main_window_complete import MotorControlApp


class _FakeCurve:
    def __init__(self):
        self.last_data = None

    def setData(self, x, y):
        self.last_data = (list(x), list(y))


class _FakePlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.curves = []

    def setTitle(self, *_args, **_kwargs):
        pass

    def setBackground(self, *_args, **_kwargs):
        pass

    def showGrid(self, *_args, **_kwargs):
        pass

    def setLabel(self, *_args, **_kwargs):
        pass

    def plot(self, *_args, **_kwargs):
        curve = _FakeCurve()
        self.curves.append(curve)
        return curve


class _FakePg:
    PlotWidget = _FakePlotWidget

    @staticmethod
    def mkPen(*_args, **_kwargs):
        return object()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _force_chart_backend(monkeypatch):
    import src.ui.mixins.health_monitor_mixin as health_mixin

    try:
        import pyqtgraph  # noqa: F401
    except ImportError:
        monkeypatch.setattr(health_mixin, "PYQTGRAPH_AVAILABLE", True)
        monkeypatch.setattr(health_mixin, "pg", _FakePg)


def test_health_monitor_page_is_available_after_baseline(monkeypatch):
    _force_chart_backend(monkeypatch)
    _app()
    window = MotorControlApp()

    assert hasattr(window, "health_btn")
    assert hasattr(window, "health_tab")
    assert hasattr(window, "health_history")
    assert hasattr(window, "health_temp_value")
    assert hasattr(window, "health_heap_value")
    assert hasattr(window, "health_clear_btn")
    assert hasattr(window, "health_export_csv_btn")
    assert hasattr(window, "health_save_png_btn")
    assert hasattr(window, "health_monitor_duration_spin")
    assert hasattr(window, "health_monitor_start_btn")
    assert hasattr(window, "health_monitor_stop_btn")
    assert hasattr(window, "health_recording_status_label")
    assert window.health_recording_active is False
    assert not hasattr(window, "health_table")
    assert hasattr(window, "health_stress_mode_combo")
    assert window.health_stress_mode_combo.currentText() == "FULL"
    assert hasattr(window, "health_temp_plot")
    assert hasattr(window, "health_heap_plot")
    assert hasattr(window, "health_loop_gap_plot")
    assert hasattr(window, "health_latency_plot")
    assert hasattr(window, "system_monitor_group")
    assert hasattr(window, "serial_group")

    assert not hasattr(window, "detector_health_label")
    assert not hasattr(window, "detector_stack_label")
    assert not hasattr(window, "detector_diag_label")
    assert not hasattr(window, "command_rtt_label")
    assert window.nav_layout.indexOf(window.system_monitor_group) < window.nav_layout.indexOf(
        window.serial_group
    )

    serial_buttons = [button.text() for button in window.serial_group.findChildren(QWidget) if hasattr(button, "text")]
    assert "健康监控" not in serial_buttons

    assert window.tab_widget.indexOf(window.baseline_tab) == 5
    assert window.tab_widget.indexOf(window.health_tab) == 6

    nav_buttons = [
        window.manual_btn.text(),
        window.auto_btn.text(),
        window.position_btn.text(),
        window.analysis_btn.text(),
        window.spectro_btn.text(),
        window.baseline_btn.text(),
        window.health_btn.text(),
    ]
    assert nav_buttons == ["手动控制", "自动控制", "转子监控", "运行分析", "分光采集", "基线稳定测试", "健康监控"]

    window.switch_tab(6)
    assert window.health_btn.isChecked()
    assert not window.baseline_btn.isChecked()

    window.deleteLater()


def test_health_monitor_records_only_during_monitor_session_and_auto_saves(monkeypatch, tmp_path):
    _force_chart_backend(monkeypatch)
    _app()
    window = MotorControlApp()
    window.health_log_dir = tmp_path

    packet = {
        "timestamp_ms": 1000,
        "uptime_s": 1,
        "temp_c": 38.5,
        "cpu_freq_mhz": 160,
        "heap_free": 120000,
        "heap_min_free": 110000,
        "heap_total": 200000,
        "heap_free_pct": 60.0,
        "task_count": 8,
        "loop_stack_hwm": 4096,
        "comms_stack_hwm": 6144,
        "sensors_stack_hwm": 3072,
    }

    window.handle_health_packet(packet)
    assert window.health_history.latest is None
    assert "38.5" in window.health_temp_value.text()
    assert "60.0" in window.health_heap_value.text()
    assert window.health_temp_curve.last_data[0] == []

    window.health_monitor_duration_spin.setValue(1)
    window.health_monitor_start_btn.click()
    assert window.health_recording_active is True
    assert window.health_monitor_start_btn.isEnabled() is False
    assert window.health_monitor_stop_btn.isEnabled() is True

    window.handle_health_packet(packet)
    window.handle_serial_data("LOOP_GAP_ACTIVE_MAX_US:87")
    window.handle_serial_data("ANGLE_AGE_MS:12")
    window.command_rtt_tracker.record("DET?", now_s=10.0)
    window._finish_command_rtt("DET_ID:USV_DETECTOR", now_s=10.037)

    assert window.health_history.latest is not None
    assert window.health_history.latest.loop_gap_active_max_us == 87
    assert window.health_history.latest.angle_age_ms == 12
    assert window.health_history.latest.command_rtt_ms == pytest.approx(37.0)
    assert not hasattr(window, "health_table")
    assert window.health_temp_curve.last_data[0] == [0.0]

    window._health_finish_monitoring(auto=True)
    assert window.health_recording_active is False
    assert window.health_monitor_start_btn.isEnabled() is True
    assert window.health_monitor_stop_btn.isEnabled() is False
    saved_files = list(tmp_path.glob("health_monitor_*.csv"))
    assert len(saved_files) == 1
    csv_text = saved_files[0].read_text(encoding="utf-8-sig")
    assert "38.5" in csv_text
    assert "loop_gap_active_max_us" in csv_text
    assert window.health_last_auto_csv_path == saved_files[0]

    window.deleteLater()


def test_health_monitor_sends_stress_test_commands(monkeypatch):
    _force_chart_backend(monkeypatch)
    _app()
    window = MotorControlApp()
    sent = []
    window.send_command = sent.append

    window.health_stress_duration_spin.setValue(60)
    window.health_stress_start_btn.click()
    window.health_stress_mode_combo.setCurrentText("CPU")
    window.health_stress_start_btn.click()
    window.health_stress_status_btn.click()
    window.health_stress_stop_btn.click()

    assert sent == [
        "STRESS:START:60,FULL\r\n",
        "STRESS:START:60\r\n",
        "STRESS:STATUS?\r\n",
        "STRESS:STOP\r\n",
    ]

    window.deleteLater()


def test_health_monitor_updates_stress_status_from_serial_text(monkeypatch):
    _force_chart_backend(monkeypatch)
    _app()
    window = MotorControlApp()

    window.handle_serial_data("STRESS_OK:START,mode=FULL,duration_s=60")
    assert "RUNNING" in window.health_stress_status_label.text()
    assert "FULL" in window.health_stress_status_label.text()
    assert "60" in window.health_stress_status_label.text()

    window.handle_serial_data("STRESS_STATUS:RUNNING,mode=FULL,duration_s=60,elapsed_s=10,remaining_s=50")
    assert "FULL" in window.health_stress_status_label.text()
    assert "remaining 50s" in window.health_stress_status_label.text()

    window.handle_serial_data("STRESS_DONE:mode=FULL,duration_s=60")
    assert "DONE" in window.health_stress_status_label.text()
    assert "FULL" in window.health_stress_status_label.text()

    window.handle_serial_data("STRESS_ERR:BUSY_MOTION")
    assert "ERR" in window.health_stress_status_label.text()
    assert "BUSY_MOTION" in window.health_stress_status_label.text()

    window.deleteLater()


def test_health_monitor_page_shows_dependency_hint_without_pyqtgraph(monkeypatch):
    import src.ui.mixins.health_monitor_mixin as health_mixin

    monkeypatch.setattr(health_mixin, "PYQTGRAPH_AVAILABLE", False)
    monkeypatch.setattr(health_mixin, "pg", None)
    _app()
    window = MotorControlApp()

    assert hasattr(window, "health_btn")
    assert hasattr(window, "health_tab")
    assert hasattr(window, "system_monitor_group")
    labels = [label.text() for label in window.health_tab.findChildren(QLabel)]
    assert any("pyqtgraph" in text for text in labels)
    assert window.tab_widget.indexOf(window.health_tab) == 6

    window.deleteLater()
