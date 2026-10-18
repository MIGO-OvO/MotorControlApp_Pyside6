from types import SimpleNamespace

import pytest
from src.ui.mixins.spectro_mixin import SpectroMixin


class Label:
    def setText(self, text):
        self.value = text

    def text(self):
        return self.value


def owner():
    obj = SimpleNamespace(
        _spectro_stop_pending=True, _spectro_stop_unknown=True,
        _spectro_start_pending=False,
        _spectro_stop_ack_timer=SimpleNamespace(stop=lambda: None),
        spectro_start_btn=Label(), spectro_status_label=Label(), log=lambda text: None,
    )
    return obj


@pytest.mark.parametrize('reply', ['ADS_ERR:STOP_I2C', 'ADS_ERR:STOP_MUTEX_TIMEOUT'])
def test_failed_stop_never_displays_confirmed_or_allows_start(reply):
    obj = owner()
    SpectroMixin._spectro_handle_ads_reply(obj, reply)
    assert obj._spectro_stop_unknown
    assert not obj._spectro_stop_pending
    assert '未确认' in obj.spectro_status_label.text()
    assert SpectroMixin._spectro_start_measurement(obj) is False


def test_timeout_and_late_start_ack_cannot_confirm_stop():
    obj = owner()
    SpectroMixin._spectro_handle_ads_reply(obj, 'ADS_OK:START')
    assert obj._spectro_stop_pending
    SpectroMixin._spectro_stop_ack_timeout(obj)
    assert obj._spectro_stop_unknown
    assert '未确认' in obj.spectro_status_label.text()


def test_matching_stop_ack_unblocks_explicit_new_start():
    obj = owner()
    SpectroMixin._spectro_handle_ads_reply(obj, 'ADS_OK:STOP')
    assert not obj._spectro_stop_pending
    assert not obj._spectro_stop_unknown
    assert obj.spectro_status_label.text() == '已确认停止'


def test_real_timer_expires_and_disconnect_requires_new_stop():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    app = QApplication.instance() or QApplication([])
    obj = owner()
    obj._spectro_stop_ack_timer = QTimer()
    obj._spectro_stop_ack_timer.setSingleShot(True)
    obj._spectro_stop_ack_timer.timeout.connect(lambda: SpectroMixin._spectro_stop_ack_timeout(obj))
    obj._spectro_stop_ack_timer.start(10)
    QTest.qWait(50)
    assert obj._spectro_stop_unknown and not obj._spectro_stop_pending
    obj._spectro_start_ack_timer = QTimer()
    obj.spectro_timer = QTimer()
    obj.spectro_ref_btn = SimpleNamespace(setEnabled=lambda value: setattr(obj, 'ref_enabled', value))
    obj._spectro_stop_pending = True
    obj._spectro_stop_ack_timer.start(2500)
    SpectroMixin._spectro_connection_lost(obj)
    assert not obj._spectro_stop_ack_timer.isActive()
    assert not obj.ref_enabled and not obj.spectro_is_measuring
    SpectroMixin._spectro_handle_ads_reply(obj, 'ADS_OK:STOP')
    assert obj._spectro_stop_unknown  # A reply outside an outstanding request is ignored.
    assert SpectroMixin._spectro_start_measurement(obj) is False
    obj._spectro_stop_pending = True
    SpectroMixin._spectro_handle_ads_reply(obj, 'ADS_OK:STOP')
    assert not obj._spectro_stop_unknown
