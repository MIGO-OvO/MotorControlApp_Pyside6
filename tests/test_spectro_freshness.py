from types import SimpleNamespace

from tests.test_spectro_invalid_isolation import SpectroOwner, FakeLabel
from src.ui.mixins import spectro_mixin


def owner_at_start():
    owner = SpectroOwner()
    owner._spectro_start_pending = True
    owner._spectro_start_ack_timer = SimpleNamespace(stop=lambda: None)
    owner._spectro_last_valid_at = None
    owner._spectro_wait_started_at = 10.0
    owner.spectro_ref_btn = SimpleNamespace(setEnabled=lambda value: setattr(owner, 'ref_enabled', value))
    owner.spectro_ref_value = FakeLabel()
    return owner


def test_ack_without_samples_is_not_acquiring_and_eventually_times_out(monkeypatch):
    owner = owner_at_start()
    owner._spectro_handle_ads_reply('ADS_OK:START')
    assert owner.spectro_status_label.text == '已启动，等待有效数据...'
    monkeypatch.setattr(spectro_mixin.time, 'monotonic', lambda: 14.0)
    owner._spectro_check_freshness()
    assert '无有效数据' in owner.spectro_status_label.text
    assert not owner.ref_enabled


def test_valid_sample_recovers_but_invalid_frames_do_not_refresh_deadline(monkeypatch):
    owner = owner_at_start()
    owner._spectro_handle_ads_reply('ADS_OK:START')
    monkeypatch.setattr(spectro_mixin.time, 'monotonic', lambda: 11.0)
    owner.handle_spectro_packet({'status': 1, 'voltage': 1.2})
    assert owner.ref_enabled
    assert owner.spectro_status_label.text == '采集中...'
    monkeypatch.setattr(spectro_mixin.time, 'monotonic', lambda: 15.0)
    owner.handle_spectro_packet({'status': 0x10, 'voltage': 2.0})
    owner._spectro_check_freshness()
    assert not owner.ref_enabled
    assert '无有效数据' in owner.spectro_status_label.text
    owner._spectro_set_reference()
    assert owner.spectro_reference_voltage is None
    owner.handle_spectro_packet({'status': 1, 'voltage': 0.7})
    assert owner.ref_enabled
    assert owner.spectro_voltage_data == [0.7]
