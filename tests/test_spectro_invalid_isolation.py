import math
from types import SimpleNamespace

import pytest

from src.core.spectro_trace import SpectroTraceRecorder, summarize_spectro_csv
from src.ui.mixins.baseline_mixin import BaselineMixin
from src.ui.mixins.spectro_mixin import QMessageBox, SpectroMixin


class FakeLabel:
    def setText(self, text):
        self.text = text


class SpectroOwner(SpectroMixin):
    def __init__(self):
        self.spectro_voltage_data = []
        self.spectro_absorbance_data = []
        self.spectro_reference_voltage = None
        self.spectro_is_measuring = True
        self.spectro_start_time = 0
        self.spectro_max_data_points = 100
        self.spectro_trace = SpectroTraceRecorder()
        self.spike_samples = []
        self.spectro_spike_test = SimpleNamespace(
            add_sample=lambda **sample: self.spike_samples.append(sample)
        )
        for name in ('spectro_voltage_value', 'spectro_status_label',
                     'spectro_absorbance_value', 'spectro_timing_value', 'spectro_ref_value'):
            setattr(self, name, FakeLabel())

    def _spectro_refresh_integrity_label(self):
        pass

    def log(self, _message):
        pass


@pytest.mark.parametrize('status', [0, 0x02, 0x03, 0x05, 0x09, 0x10, 0x11])
def test_invalid_frames_cannot_establish_reference_and_remain_diagnostic(status, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    owner = SpectroOwner()
    owner.handle_spectro_packet({'timestamp_ms': 100, 'status': status, 'voltage': 2.0})
    owner._spectro_set_reference()

    assert owner.spectro_reference_voltage is None
    assert owner.spectro_voltage_data == []
    assert owner.spectro_absorbance_data == []
    assert not owner.spike_samples[0]['valid']
    assert not BaselineMixin._baseline_is_valid_packet(owner, status)
    record = owner.spectro_trace.records[0]
    assert record['voltage'] == 2.0
    assert record['valid'] is False
    assert math.isnan(record['absorbance'])
    if status & 0x10:
        assert record['status'] == 'test_data'


def test_invalid_voltage_does_not_pollute_reference_or_valid_absorbance():
    owner = SpectroOwner()
    for status, voltage in [(0x01, 1.0), (0x10, 2.0), (0x03, 3.0)]:
        owner.handle_spectro_packet({'timestamp_ms': 100, 'status': status, 'voltage': voltage})
    owner._spectro_set_reference()
    owner.handle_spectro_packet({'timestamp_ms': 200, 'status': 0x01, 'voltage': 0.5})

    assert owner.spectro_reference_voltage == 1.0
    assert owner.spectro_voltage_data == [1.0, 0.5]
    assert owner.spectro_trace.records[-1]['absorbance'] == pytest.approx(math.log10(2))


def test_csv_signal_statistics_exclude_invalid_but_keep_raw_transport_frames(tmp_path):
    recorder = SpectroTraceRecorder()
    for index, (status, voltage) in enumerate([(0x01, 1.0), (0x10, 20.0), (0x03, 30.0), (0x01, 3.0)]):
        recorder.append_packet(
            {'timestamp_ms': index * 50, 'status': status, 'voltage': voltage},
            received_at_ms=1000 + index * 50, elapsed_s=index * 0.05, absorbance=0.0,
        )
    output = tmp_path / 'diagnostic.csv'
    recorder.export_csv(output)
    summary = summarize_spectro_csv(output)

    assert summary.sample_count == 4
    assert summary.receive_rate_hz == pytest.approx(20.0)
    assert summary.voltage_mean_v == pytest.approx(2.0)
    assert summary.voltage_std_v == pytest.approx(1.0)
    assert summary.voltage_min_v == pytest.approx(1.0)
    assert summary.voltage_max_v == pytest.approx(3.0)


def test_csv_all_invalid_has_no_measured_signal_statistics(tmp_path):
    recorder = SpectroTraceRecorder()
    recorder.append_packet(
        {'timestamp_ms': 0, 'status': 0x10, 'voltage': 20.0},
        received_at_ms=1000, elapsed_s=0, absorbance=0.0,
    )
    output = tmp_path / 'only-test-data.csv'
    recorder.export_csv(output)
    summary = summarize_spectro_csv(output)
    assert summary.sample_count == 1
    assert summary.voltage_mean_v is None
    assert summary.voltage_std_v is None
    assert summary.voltage_min_v is None
    assert summary.voltage_max_v is None
