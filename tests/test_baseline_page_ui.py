import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QGroupBox, QWidget

from src.ui.mixins.baseline_mixin import BaselineMixin
from src.ui.main_window_complete import MotorControlApp


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


def test_startup_does_not_override_qt_dpi_awareness():
    main_py = Path(__file__).resolve().parents[1] / "main.py"
    source = main_py.read_text(encoding="utf-8")

    assert "SetProcessDpiAwareness(" not in source
    assert "SetProcessDpiAwarenessContext(" not in source
