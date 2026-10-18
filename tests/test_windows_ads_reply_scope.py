"""Firmware-scoped ADS replies must not let a late START consume STOP."""

from types import SimpleNamespace

import pytest

from src.hardware.serial_reader import SerialReader
from src.ui.mixins.spectro_mixin import SpectroMixin


class Label:
    def __init__(self):
        self.value = "停止中，等待下位机确认..."

    def setText(self, text):
        self.value = text

    def text(self):
        return self.value


@pytest.mark.parametrize(
    "late_reply",
    [
        "ADS_OK:START",
        "ADS_ERR:I2C",
        "ADS_ERR:CONFIG",
        "ADS_ERR:MUTEX_TIMEOUT",
        "ADS_ERR:STOP_I2C_EXTRA",
    ],
)
def test_late_start_or_config_reply_cannot_consume_pending_stop(late_reply):
    timer_stops = []
    owner = SimpleNamespace(
        _spectro_stop_pending=True,
        _spectro_stop_unknown=True,
        _spectro_start_pending=False,
        _spectro_stop_ack_timer=SimpleNamespace(stop=lambda: timer_stops.append(True)),
        spectro_start_btn=Label(),
        spectro_status_label=Label(),
        log=lambda _message: None,
    )
    reader = SerialReader(SimpleNamespace(is_open=False))
    reader.data_received.connect(
        lambda line: SpectroMixin._spectro_handle_ads_reply(owner, line)
    )

    # Use the production line parser, including a fragmented old START reply.
    encoded = (late_reply + "\r\n").encode()
    reader._process_data(encoded[:7])
    reader._process_data(encoded[7:])
    assert owner._spectro_stop_pending, late_reply
    assert owner._spectro_stop_unknown
    assert timer_stops == []

    reader._process_data(b"ADS_OK:STOP\r\n")
    assert not owner._spectro_stop_pending
    assert not owner._spectro_stop_unknown
    assert owner.spectro_status_label.text() == "已确认停止"
    assert timer_stops == [True]
