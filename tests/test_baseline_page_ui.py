import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QGroupBox, QWidget

from src.ui.mixins.baseline_mixin import BaselineMixin
from src.ui.main_window_complete import MotorControlApp


class _FakeCurve:
    def setData(self, *_args, **_kwargs):
        pass


class _FakePlotWidget(QWidget):
    def setTitle(self, *_args, **_kwargs):
        pass

    def setBackground(self, *_args, **_kwargs):
        pass

    def showGrid(self, *_args, **_kwargs):
        pass

    def setLabel(self, *_args, **_kwargs):
        pass

    def plot(self, *_args, **_kwargs):
        return _FakeCurve()


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


def test_baseline_page_is_independent_from_spectro_page():
    pytest.importorskip("pyqtgraph")
    _app()
    window = MotorControlApp()

    assert hasattr(window, "baseline_btn")
    assert hasattr(window, "baseline_tab")
    assert hasattr(window, "baseline_remaining_value")
    assert hasattr(window, "baseline_export_btn")
    assert hasattr(window, "baseline_result_cards")

    assert window.tab_widget.indexOf(window.spectro_tab) == 4
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
    assert nav_buttons == [
        "手动控制",
        "自动控制",
        "转子监控",
        "运行分析",
        "分光采集",
        "基线稳定测试",
        "健康监控",
    ]

    spectro_group_titles = [group.title() for group in window.spectro_tab.findChildren(QGroupBox)]
    assert "基线稳定测试" not in spectro_group_titles

    window.switch_tab(5)
    assert window.baseline_btn.isChecked()
    assert not window.spectro_btn.isChecked()

    window.deleteLater()


def test_baseline_metric_card_stylesheet_has_balanced_braces():
    _app()
    parent = QWidget()
    layout = QGridLayout(parent)
    mixin = BaselineMixin()
    mixin.baseline_result_cards = {}

    mixin._baseline_add_metric_card(layout, 0, 0, "drift_v", "Drift", "V")

    card = parent.findChild(QFrame)
    assert card is not None
    style = card.styleSheet().strip()
    assert style.count("{") == style.count("}")
    assert not style.endswith("}}")


def test_spectro_page_records_jetson_compatible_transport_diagnostics(monkeypatch):
    import src.ui.mixins.spectro_mixin as spectro_mixin

    monkeypatch.setattr(spectro_mixin, "PYQTGRAPH_AVAILABLE", True)
    monkeypatch.setattr(spectro_mixin, "pg", _FakePg)
    _app()
    window = MotorControlApp()

    assert hasattr(window, "spectro_compare_profile_btn")
    window.spectro_compare_profile_btn.click()
    assert window.spectro_tca_channel_spin.value() == 2
    assert window.spectro_ads_addr_combo.currentText() == "0x40"
    assert window.spectro_vref_combo.currentText() == "AVDD"
    assert window.spectro_gain_combo.currentText() == "1"
    assert window.spectro_rate_combo.currentText() == "90"
    assert window.spectro_publish_spin.value() == 20
    assert hasattr(window, "spectro_timing_value")
    assert hasattr(window, "spectro_integrity_value")
    assert hasattr(window, "spectro_compare_btn")

    window.spectro_trace.start_session("ui-test")
    window.detector_ads_health = {
        "crc_error": 1,
        "duplicate": 2,
        "transient_drop": 3,
    }
    packet = {
        "timestamp_ms": 1000,
        "tca_channel": 2,
        "status": 0x01,
        "raw_code": 123,
        "voltage": 1.035,
    }
    window.handle_spectro_packet(packet)
    packet["timestamp_ms"] = 1050
    window.handle_spectro_packet(packet)

    assert window.spectro_data_log[-1]["source_delta_ms"] == 50
    assert window.spectro_data_log[-1]["transport_path"] == "windows_direct"
    assert window.spectro_data_log[-1]["ads_crc_error"] == 1
    assert "Device Δ 50 ms" in window.spectro_timing_value.text()
    assert window.spectro_integrity_value.text() == "CRC 1 / Dup 2 / Drop 3"

    window.deleteLater()


def test_spectro_spike_test_uses_session_scoped_counter_deltas(monkeypatch):
    import src.ui.mixins.spectro_mixin as spectro_mixin

    monkeypatch.setattr(spectro_mixin, "PYQTGRAPH_AVAILABLE", True)
    monkeypatch.setattr(spectro_mixin, "pg", _FakePg)
    _app()
    window = MotorControlApp()
    window.spectro_is_measuring = True
    window._health_record_ads_counters(
        {"crc_error": 5, "duplicate": 10, "transient_drop": 3}
    )

    window._spectro_start_spike_test()
    assert window.spectro_spike_test.active is True
    assert window.spectro_spike_status_value.text() == "测试中"
    assert window.spectro_trace.session_id == window.spectro_spike_session_id

    packet = {
        "timestamp_ms": 1000,
        "tca_channel": 2,
        "status": 0x01,
        "raw_code": 123,
        "voltage": 1.000,
    }
    window.handle_spectro_packet(packet)
    packet["timestamp_ms"] = 1050
    packet["voltage"] = 0.979
    window.handle_spectro_packet(packet)
    window._health_record_ads_counters(
        {"crc_error": 5, "duplicate": 12, "transient_drop": 4}
    )
    window._spectro_stop_spike_test()

    assert window.spectro_spike_status_value.text() == "已结束"
    assert window.spectro_spike_drop_value.text() == ">5 1 / >10 1 / >20 1"
    assert window.spectro_spike_ads_value.text() == "CRC 0 / Dup 2 / Drop 1"
    assert window.spectro_spike_export_btn.isEnabled()

    window.deleteLater()


def test_startup_does_not_override_qt_dpi_awareness():
    main_py = Path(__file__).resolve().parents[1] / "main.py"
    source = main_py.read_text(encoding="utf-8")

    assert "SetProcessDpiAwareness(" not in source
    assert "SetProcessDpiAwarenessContext(" not in source
