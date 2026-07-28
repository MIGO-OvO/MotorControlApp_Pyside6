"""分光信号采集 Mixin 模块。

通过串口与下位机通信控制 ADS122C04 采集，实时接收电压数据并计算吸光度。
已移除 NI DAQ 依赖，所有采集由下位机统一完成。
"""
from __future__ import annotations
import os
import time
from datetime import datetime
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)
from src.config.constants import (
    ADS_AIN_OPTIONS, ADS_GAIN_OPTIONS, ADS_SUPPORTED_RATES,
    ADS_VREF_OPTIONS, DEFAULT_ADS_CONFIG,
    DEFAULT_SPECTRO_CHART_POINTS, SPECTRO_CHART_POINTS_RANGE,
    SPECTRO_CHART_POINTS_STEP,
    COLOR_PRIMARY, COLOR_TEXT_SECONDARY,
    BUTTON_SECONDARY, BUTTON_DANGER, BUTTON_SUCCESS,
)
from src.core.spectro_trace import (
    SpectroTraceRecorder,
    compare_spectro_csv,
    format_spectro_comparison,
)
from src.core.spectro_spike_test import (
    DEFAULT_SPIKE_TEST_DURATION_S,
    SPIKE_TEST_DURATION_OPTIONS_S,
    SpectroSpikeTest,
    build_spike_test_summary_csv,
)
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None  # type: ignore


class SpectroMixin:
    """分光信号采集功能 Mixin。"""

    def _spectro_init_vars(self) -> None:
        self.spectro_reference_voltage: Optional[float] = None
        self.spectro_is_measuring: bool = False
        self.spectro_voltage_data: list[float] = []
        self.spectro_absorbance_data: list[float] = []
        self.spectro_max_data_points: int = DEFAULT_SPECTRO_CHART_POINTS
        self.spectro_trace = SpectroTraceRecorder(transport_path="windows_direct")
        self.spectro_data_log = self.spectro_trace.records
        self.spectro_latest_record: Optional[dict] = None
        self.spectro_last_export_path = ""
        self.spectro_spike_test = SpectroSpikeTest()
        self.spectro_spike_session_id = ""
        self.spectro_spike_auto_completed = False
        self.spectro_start_time: float = 0.0
        self.spectro_timer = QTimer(self)  # type: ignore[arg-type]
        self.spectro_timer.setTimerType(Qt.PreciseTimer)
        self.spectro_timer.timeout.connect(self._spectro_update_charts)

    def init_spectro_tab(self):
        if not PYQTGRAPH_AVAILABLE:
            layout = QVBoxLayout(self.spectro_tab)
            lbl = QLabel("分光信号功能不可用，缺少 pyqtgraph 库。")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Microsoft YaHei", 14))
            layout.addWidget(lbl)
            return
        main_layout = QHBoxLayout(self.spectro_tab)
        main_layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        left_scroll = QScrollArea(); left_scroll.setWidgetResizable(True); left_scroll.setFrameShape(QFrame.NoFrame)
        left = QFrame(); ll = QVBoxLayout(left); ll.setContentsMargins(5,5,5,5); ll.setSpacing(10)
        left_scroll.setWidget(left)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0)
        splitter.addWidget(left_scroll); splitter.addWidget(right); splitter.setSizes([360, 700])
        self._spectro_create_ads_config_group(ll)
        self._spectro_create_display_group(ll)
        self._spectro_create_measurement_group(ll)
        self._spectro_create_spike_test_group(ll)
        self._spectro_create_control_buttons(ll)
        ll.addStretch(1)
        self._spectro_create_charts_group(rl)

    # --- UI 创建方法 ---

    def _spectro_create_ads_config_group(self, parent_layout):
        group = QGroupBox("ADS122C04 配置")
        layout = QFormLayout(); layout.setSpacing(8)
        self.spectro_tca_channel_spin = QSpinBox(); self.spectro_tca_channel_spin.setRange(0, 7)
        self.spectro_tca_channel_spin.setValue(DEFAULT_ADS_CONFIG.get("tca_channel", 2))
        self.spectro_ads_addr_combo = QComboBox()
        self.spectro_ads_addr_combo.addItems(["0x40", "0x41", "0x44", "0x45"])
        self.spectro_vref_combo = QComboBox(); self.spectro_vref_combo.addItems(ADS_VREF_OPTIONS)
        self.spectro_gain_combo = QComboBox()
        self.spectro_gain_combo.addItems([str(g) for g in ADS_GAIN_OPTIONS])
        self.spectro_rate_combo = QComboBox()
        self.spectro_rate_combo.addItems([str(r) for r in ADS_SUPPORTED_RATES])
        self.spectro_rate_combo.setCurrentText(str(DEFAULT_ADS_CONFIG.get("adc_rate", 90)))
        self.spectro_publish_spin = QSpinBox(); self.spectro_publish_spin.setRange(1, 200)
        self.spectro_publish_spin.setValue(DEFAULT_ADS_CONFIG.get("publish_rate", 20))
        layout.addRow("参考源:", self.spectro_vref_combo)
        layout.addRow("增益:", self.spectro_gain_combo)
        layout.addRow("ADC 数据率:", self.spectro_rate_combo)
        layout.addRow("上传频率 (Hz):", self.spectro_publish_spin)
        self.spectro_compare_profile_btn = QPushButton("应用 Jetson 对比参数")
        self.spectro_compare_profile_btn.setToolTip(
            "载入 Jetson 默认分光配置：通道 2、地址 0x40、AVDD、增益 1、"
            "ADC 90 SPS、发布 20 Hz"
        )
        self.spectro_compare_profile_btn.clicked.connect(
            self._spectro_apply_jetson_compare_profile
        )
        layout.addRow(self.spectro_compare_profile_btn)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_display_group(self, parent_layout):
        group = QGroupBox("显示设置")
        layout = QFormLayout(); layout.setSpacing(8)
        min_points, max_points = SPECTRO_CHART_POINTS_RANGE
        self.spectro_chart_points_spin = QSpinBox()
        self.spectro_chart_points_spin.setRange(min_points, max_points)
        self.spectro_chart_points_spin.setSingleStep(SPECTRO_CHART_POINTS_STEP)
        self.spectro_chart_points_spin.setValue(self.spectro_max_data_points)
        self.spectro_chart_points_spin.setSuffix(" 点")
        self.spectro_chart_points_spin.setToolTip("仅控制图表显示窗口，不影响CSV保存和基线分析。")
        self.spectro_chart_points_spin.valueChanged.connect(self._spectro_set_chart_points)
        layout.addRow("图表点数:", self.spectro_chart_points_spin)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_measurement_group(self, parent_layout):
        group = QGroupBox("实时测量"); layout = QFormLayout(); layout.setSpacing(8)
        self.spectro_voltage_value = QLabel("0.0000 V")
        self.spectro_voltage_value.setStyleSheet(f"font-size: 20px; color: {COLOR_PRIMARY}; font-weight: bold;")
        self.spectro_absorbance_value = QLabel("0.0000")
        self.spectro_absorbance_value.setStyleSheet("font-size: 20px; color: #CC1155; font-weight: bold;")
        self.spectro_ref_value = QLabel("未设置")
        self.spectro_ref_value.setStyleSheet("font-size: 16px; color: #4745B5;")
        self.spectro_status_label = QLabel("就绪")
        self.spectro_status_label.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_SECONDARY};")
        self.spectro_timing_value = QLabel("Host Δ -- / Device Δ --")
        self.spectro_timing_value.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_SECONDARY};")
        self.spectro_integrity_value = QLabel("CRC -- / Dup -- / Drop --")
        self.spectro_integrity_value.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_SECONDARY};")
        layout.addRow("电压:", self.spectro_voltage_value)
        layout.addRow("吸光度:", self.spectro_absorbance_value)
        layout.addRow("参考电压:", self.spectro_ref_value)
        layout.addRow("状态:", self.spectro_status_label)
        layout.addRow("接收间隔:", self.spectro_timing_value)
        layout.addRow("固件完整性:", self.spectro_integrity_value)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_spike_test_group(self, parent_layout):
        group = QGroupBox("毛刺测试")
        layout = QFormLayout()
        layout.setSpacing(8)
        self.spectro_spike_status_value = QLabel("未开始")
        self.spectro_spike_time_value = QLabel("0.0 s / 0 点 / -- Hz")
        self.spectro_spike_drop_value = QLabel(">5 0 / >10 0 / >20 0")
        self.spectro_spike_max_value = QLabel("0.0 mV")
        self.spectro_spike_ads_value = QLabel("CRC -- / Dup -- / Drop --")
        for label in (
            self.spectro_spike_status_value,
            self.spectro_spike_time_value,
            self.spectro_spike_drop_value,
            self.spectro_spike_max_value,
            self.spectro_spike_ads_value,
        ):
            label.setStyleSheet(
                f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};"
            )

        self.spectro_spike_duration_combo = QComboBox()
        for duration_s in SPIKE_TEST_DURATION_OPTIONS_S:
            self.spectro_spike_duration_combo.addItem(
                _format_duration_option(duration_s),
                duration_s,
            )
        default_index = self.spectro_spike_duration_combo.findData(
            DEFAULT_SPIKE_TEST_DURATION_S
        )
        self.spectro_spike_duration_combo.setCurrentIndex(max(0, default_index))
        self.spectro_spike_duration_combo.setToolTip(
            "Windows 与 ROS 网页使用相同测试时长；开始后锁定，到时自动结束。"
        )
        self.spectro_spike_duration_combo.currentIndexChanged.connect(
            lambda _index: self._spectro_refresh_spike_test()
        )

        layout.addRow("状态:", self.spectro_spike_status_value)
        layout.addRow("测试时长:", self.spectro_spike_duration_combo)
        layout.addRow("进度/样本:", self.spectro_spike_time_value)
        layout.addRow("相邻下冲 (mV):", self.spectro_spike_drop_value)
        layout.addRow("最大下冲:", self.spectro_spike_max_value)
        layout.addRow("ADS 会话增量:", self.spectro_spike_ads_value)

        buttons = QHBoxLayout()
        self.spectro_spike_start_btn = QPushButton("开始测试")
        self.spectro_spike_start_btn.setToolTip(
            "清空当前分光图表，并以当前 ADS 累计计数作为本次测试基线。"
        )
        self.spectro_spike_start_btn.setStyleSheet(BUTTON_SUCCESS)
        self.spectro_spike_start_btn.clicked.connect(self._spectro_start_spike_test)
        self.spectro_spike_start_btn.setEnabled(False)

        self.spectro_spike_stop_btn = QPushButton("结束测试")
        self.spectro_spike_stop_btn.setStyleSheet(BUTTON_DANGER)
        self.spectro_spike_stop_btn.clicked.connect(self._spectro_stop_spike_test)
        self.spectro_spike_stop_btn.setEnabled(False)

        self.spectro_spike_export_btn = QPushButton("导出结果")
        self.spectro_spike_export_btn.setToolTip(
            "导出与 ROS 网页一致的一行毛刺测试汇总 CSV；原始样本请使用“保存数据”。"
        )
        self.spectro_spike_export_btn.setStyleSheet(BUTTON_SECONDARY)
        self.spectro_spike_export_btn.clicked.connect(
            self._spectro_export_spike_test
        )
        self.spectro_spike_export_btn.setEnabled(False)
        for button in (
            self.spectro_spike_start_btn,
            self.spectro_spike_stop_btn,
            self.spectro_spike_export_btn,
        ):
            buttons.addWidget(button)
        layout.addRow(buttons)
        group.setLayout(layout)
        parent_layout.addWidget(group)

    def _spectro_create_control_buttons(self, parent_layout):
        group = QGroupBox("操作控制"); layout = QVBoxLayout(); layout.setSpacing(8)
        self.spectro_start_btn = QPushButton("开始采集")
        self.spectro_start_btn.setToolTip("开始/停止ADS122C04连续采集")
        self.spectro_start_btn.clicked.connect(self._spectro_toggle_measurement)
        self.spectro_ref_btn = QPushButton("设置参考")
        self.spectro_ref_btn.setToolTip("将当前电压均值设为吸光度计算的参考值")
        self.spectro_ref_btn.clicked.connect(self._spectro_set_reference)
        self.spectro_ref_btn.setEnabled(False)
        self.spectro_clear_btn = QPushButton("清除数据")
        self.spectro_clear_btn.setToolTip("清除所有已采集的电压和吸光度数据")
        self.spectro_clear_btn.clicked.connect(self._spectro_clear_data)
        self.spectro_save_btn = QPushButton("保存数据")
        self.spectro_save_btn.setToolTip("导出与 Jetson raw.csv 前八列一致的对比 CSV")
        self.spectro_save_btn.clicked.connect(self._spectro_save_data)
        self.spectro_compare_btn = QPushButton("对比 Jetson CSV")
        self.spectro_compare_btn.setToolTip(
            "依次选择 Windows 直连 CSV 和 Jetson 采样窗口 raw.csv，比较频率、抖动和毛刺。"
        )
        self.spectro_compare_btn.clicked.connect(self._spectro_compare_jetson_csv)
        for btn in [
            self.spectro_start_btn,
            self.spectro_ref_btn,
            self.spectro_clear_btn,
            self.spectro_save_btn,
            self.spectro_compare_btn,
        ]:
            layout.addWidget(btn)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_charts_group(self, parent_layout):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget(); cl = QVBoxLayout(container); cl.setSpacing(15)
        vg = QGroupBox("电压 (V)"); vl = QVBoxLayout(vg)
        self.spectro_voltage_plot = pg.PlotWidget(); self.spectro_voltage_plot.setBackground("w")
        self.spectro_voltage_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_voltage_curve = self.spectro_voltage_plot.plot(pen=pg.mkPen(color=COLOR_PRIMARY, width=2))
        self.spectro_voltage_plot.setMinimumHeight(200); vl.addWidget(self.spectro_voltage_plot)
        cl.addWidget(vg)
        ag = QGroupBox("吸光度 (Abs)"); al = QVBoxLayout(ag)
        self.spectro_absorbance_plot = pg.PlotWidget(); self.spectro_absorbance_plot.setBackground("w")
        self.spectro_absorbance_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_absorbance_curve = self.spectro_absorbance_plot.plot(pen=pg.mkPen(color="#CC1155", width=2))
        self.spectro_absorbance_plot.setMinimumHeight(200); al.addWidget(self.spectro_absorbance_plot)
        cl.addWidget(ag)
        scroll.setWidget(container); parent_layout.addWidget(scroll)

    # --- 逻辑方法 ---

    def _spectro_build_adscfg_command(self) -> str:
        """根据UI控件构建 ADSCFG 串口命令。"""
        ch = self.spectro_tca_channel_spin.value()
        addr = self.spectro_ads_addr_combo.currentText()
        vref = "AVDD" if self.spectro_vref_combo.currentText() == "AVDD" else "INT"
        gain = self.spectro_gain_combo.currentText()
        dr = self.spectro_rate_combo.currentText()
        pr = self.spectro_publish_spin.value()
        return f"ADSCFG:CH={ch},ADDR={addr},AIN=AIN0,REF={vref},GAIN={gain},DR={dr},MODE=CONT,PR={pr}\r\n"

    def _spectro_apply_jetson_compare_profile(self) -> None:
        """Apply matching ADS settings for Windows/Jetson comparison."""
        self.spectro_tca_channel_spin.setValue(2)
        self.spectro_ads_addr_combo.setCurrentText("0x40")
        self.spectro_vref_combo.setCurrentText("AVDD")
        self.spectro_gain_combo.setCurrentText("1")
        self.spectro_rate_combo.setCurrentText("90")
        self.spectro_publish_spin.setValue(20)
        self.log(
            "已载入 Jetson 对比参数: CH2, 0x40, AVDD, GAIN 1, "
            "ADC 90 SPS, 发布 20 Hz"
        )

    def _spectro_toggle_measurement(self):
        if not self.spectro_is_measuring:
            self._spectro_start_measurement()
        else:
            self._spectro_stop_measurement()

    def _spectro_start_measurement(self) -> bool:
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "错误", "请先打开串口连接")
            return False
        cfg_cmd = self._spectro_build_adscfg_command()
        self.send_command(cfg_cmd)
        time.sleep(0.1)
        self.send_command("ADSSTART\r\n")
        self.spectro_is_measuring = True
        self.spectro_start_btn.setText("停止采集")
        self.spectro_ref_btn.setEnabled(True)
        self.spectro_status_label.setText("采集中...")
        self.spectro_start_time = time.time()
        self.spectro_trace.start_session()
        self.spectro_latest_record = None
        self.spectro_timer.start(100)
        self._spectro_refresh_spike_test()
        self.log("分光信号开始采集")
        return True

    def _spectro_stop_measurement(self):
        if getattr(self, "baseline_is_running", False):
            self._baseline_finish_test(manual_stop=True, stop_owned_measurement=False)
        if self.spectro_spike_test.active:
            self._spectro_stop_spike_test()
        if self.spectro_timer.isActive():
            self.spectro_timer.stop()
        if self.serial_port and self.serial_port.is_open:
            try:
                self.send_command("ADSSTOP\r\n")
            except Exception:
                pass
        self.spectro_is_measuring = False
        self.spectro_start_btn.setText("开始采集")
        self.spectro_ref_btn.setEnabled(False)
        self.spectro_status_label.setText("已停止")
        self._spectro_refresh_spike_test()
        self.log("分光信号停止采集")

    def _spectro_set_chart_points(self, value: int) -> None:
        self.spectro_max_data_points = value
        if hasattr(self, "baseline_chart_points_spin") and self.baseline_chart_points_spin.value() != value:
            self.baseline_chart_points_spin.blockSignals(True)
            self.baseline_chart_points_spin.setValue(value)
            self.baseline_chart_points_spin.blockSignals(False)
            self._baseline_set_chart_points(value, sync_spectro=False)
        self._spectro_trim_chart_data()
        self._spectro_update_charts()

    def _spectro_trim_chart_data(self) -> None:
        if len(self.spectro_voltage_data) > self.spectro_max_data_points:
            del self.spectro_voltage_data[:-self.spectro_max_data_points]
        if len(self.spectro_absorbance_data) > self.spectro_max_data_points:
            del self.spectro_absorbance_data[:-self.spectro_max_data_points]

    def handle_spectro_packet(self, packet: dict):
        """处理分光二进制数据包 (0xDD)。"""
        if getattr(self, "_closing", False):
            return
        received_at_s = time.time()
        received_at_ms = int(received_at_s * 1000)
        voltage = float(packet.get("voltage", 0.0))
        raw_code = packet.get("raw_code", 0)
        status = int(packet.get("status", 0))

        self.spectro_voltage_data.append(voltage)
        self.spectro_voltage_value.setText(f"{voltage:.4f} V")

        if status & 0x02:
            self.spectro_status_label.setText("I2C 错误")
        elif status & 0x08:
            self.spectro_status_label.setText("数据饱和")
        elif self.spectro_is_measuring:
            self.spectro_status_label.setText("采集中...")

        absorbance = 0.0
        if self.spectro_reference_voltage and self.spectro_reference_voltage > 1e-9:
            transmittance = voltage / self.spectro_reference_voltage
            absorbance = -np.log10(transmittance) if transmittance > 0 else 0.0
            self.spectro_absorbance_value.setText(f"{absorbance:.4f}")
        else:
            self.spectro_absorbance_value.setText("N/A")

        self.spectro_absorbance_data.append(absorbance)
        self._spectro_trim_chart_data()

        elapsed_s = received_at_s - self.spectro_start_time if self.spectro_start_time else 0
        self.spectro_latest_record = self.spectro_trace.append_packet(
            packet,
            received_at_ms=received_at_ms,
            elapsed_s=elapsed_s,
            absorbance=absorbance,
            ads_counters=getattr(self, "detector_ads_health", {}),
        )
        host_delta = self.spectro_latest_record.get("host_interarrival_ms")
        source_delta = self.spectro_latest_record.get("source_delta_ms")
        self.spectro_timing_value.setText(
            f"Host Δ {_format_interval(host_delta)} / Device Δ {_format_interval(source_delta)}"
        )
        self.spectro_spike_test.add_sample(
            timestamp_ms=received_at_ms,
            voltage=voltage,
            valid=bool(status & 0x01),
        )
        self._spectro_refresh_integrity_label()

        if hasattr(self, "handle_baseline_packet"):
            self.handle_baseline_packet(packet, voltage, status)

    def _spectro_set_reference(self):
        if self.spectro_is_measuring and self.spectro_voltage_data:
            avg = float(np.mean(self.spectro_voltage_data[-10:]))
            self.spectro_reference_voltage = avg
            self.spectro_ref_value.setText(f"{avg:.4f} V")
            self.spectro_status_label.setText("参考电压已设置")
            self.log(f"参考电压设置为 {avg:.4f} V")
        else:
            # M1: 明确反馈无法设置的原因
            if not self.spectro_is_measuring:
                self.spectro_status_label.setText("请先开始采集")
                QMessageBox.information(self, "提示", "请先开始采集数据后再设置参考电压。")
            elif not self.spectro_voltage_data:
                self.spectro_status_label.setText("等待数据...")
                QMessageBox.information(self, "提示", "尚无采集数据，请等待数据到达后再设置。")

    def _spectro_clear_data(self):
        self.spectro_voltage_data.clear()
        self.spectro_absorbance_data.clear()
        self.spectro_trace.clear()
        self.spectro_latest_record = None
        self.spectro_spike_test.reset()
        self.spectro_spike_session_id = ""
        self.spectro_spike_auto_completed = False
        self.spectro_timing_value.setText("Host Δ -- / Device Δ --")
        self._spectro_refresh_integrity_label()
        self._spectro_refresh_spike_test()
        self._spectro_update_charts()
        self.log("分光数据已清除")

    def _spectro_update_charts(self):
        if hasattr(self, "spectro_voltage_curve"):
            self.spectro_voltage_curve.setData(self.spectro_voltage_data)
        if hasattr(self, "spectro_absorbance_curve"):
            self.spectro_absorbance_curve.setData(self.spectro_absorbance_data)
        if self.spectro_spike_test.active:
            self._spectro_refresh_spike_test()

    def _spectro_save_data(self):
        if not self.spectro_data_log:
            QMessageBox.warning(self, "保存错误", "没有数据可以保存")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"spectro_data_{ts}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "保存数据", filename, "CSV Files (*.csv)")
        if not path:
            return
        try:
            self.spectro_trace.export_csv(path)
            self.spectro_last_export_path = path
            self.log(f"分光数据已保存至 {os.path.basename(path)}")
        except Exception as e:
            self.log(f"保存数据失败: {e}")
            QMessageBox.critical(self, "保存错误", f"文件保存失败: {e}")

    def _spectro_compare_jetson_csv(self):
        windows_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Windows 直连 CSV",
            self.spectro_last_export_path,
            "CSV Files (*.csv)",
        )
        if not windows_path:
            return
        jetson_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Jetson 采样窗口 raw.csv",
            "",
            "CSV Files (*.csv)",
        )
        if not jetson_path:
            return
        try:
            comparison = compare_spectro_csv(windows_path, jetson_path)
            QMessageBox.information(
                self,
                "Windows / Jetson 分光链路对比",
                format_spectro_comparison(comparison),
            )
        except Exception as exc:
            QMessageBox.critical(self, "对比失败", f"无法比较 CSV: {exc}")

    def _spectro_refresh_integrity_label(self) -> None:
        if not hasattr(self, "spectro_integrity_value"):
            return
        counters = getattr(self, "detector_ads_health", {})
        self.spectro_spike_test.update_counters(counters)
        self.spectro_integrity_value.setText(
            f"CRC {_format_counter(counters.get('crc_error'))} / "
            f"Dup {_format_counter(counters.get('duplicate'))} / "
            f"Drop {_format_counter(counters.get('transient_drop'))}"
        )
        self._spectro_refresh_spike_test()

    def _spectro_start_spike_test(self) -> None:
        if not self.spectro_is_measuring:
            QMessageBox.information(
                self,
                "毛刺测试",
                "请先开始分光采集，再开始毛刺测试。",
            )
            return
        self._spectro_clear_data()
        started_at_ms = int(time.time() * 1000)
        target_duration_s = int(self.spectro_spike_duration_combo.currentData())
        self.spectro_spike_session_id = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )[:-3]
        self.spectro_start_time = started_at_ms / 1000.0
        self.spectro_trace.start_session(self.spectro_spike_session_id)
        self.spectro_spike_test.start(
            started_at_ms=started_at_ms,
            target_duration_s=target_duration_s,
            counters=getattr(self, "detector_ads_health", {}),
        )
        self._spectro_refresh_spike_test(now_ms=started_at_ms)
        self.log(
            f"[毛刺测试] 已开始，目标 {_format_duration_option(target_duration_s)}，"
            "会话计数已归零"
        )

    def _spectro_stop_spike_test(self) -> None:
        self._spectro_finish_spike_test()

    def _spectro_finish_spike_test(
        self,
        *,
        ended_at_ms: Optional[int] = None,
        auto_completed: bool = False,
    ) -> None:
        if not self.spectro_spike_test.active:
            return
        self.spectro_spike_test.stop(
            ended_at_ms=(
                ended_at_ms
                if ended_at_ms is not None
                else int(time.time() * 1000)
            ),
            counters=getattr(self, "detector_ads_health", {}),
        )
        self.spectro_spike_auto_completed = auto_completed
        self._spectro_refresh_spike_test()
        self.log(
            "[毛刺测试] 已按设定时长自动结束"
            if auto_completed
            else "[毛刺测试] 已手动结束"
        )

    def _spectro_export_spike_test(self) -> None:
        summary = self.spectro_spike_test.summary()
        if summary.active:
            QMessageBox.information(self, "毛刺测试", "请先结束测试再导出结果。")
            return
        if summary.sample_count <= 0 or not self.spectro_spike_session_id:
            QMessageBox.warning(self, "毛刺测试", "没有可导出的毛刺测试结果。")
            return
        filename = f"spectro_spike_test_{self.spectro_spike_session_id}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出毛刺测试结果",
            filename,
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            csv_text = build_spike_test_summary_csv(
                summary,
                session_id=self.spectro_spike_session_id,
                transport_path="windows_direct",
            )
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(csv_text)
            self.log(f"[毛刺测试] 结果已保存至 {os.path.basename(path)}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"无法导出毛刺测试结果: {exc}")

    def _spectro_refresh_spike_test(self, now_ms: Optional[int] = None) -> None:
        if not hasattr(self, "spectro_spike_status_value"):
            return
        current_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        if self.spectro_spike_test.should_auto_stop(current_ms):
            self._spectro_finish_spike_test(
                ended_at_ms=self.spectro_spike_test.deadline_ms,
                auto_completed=True,
            )
            return
        summary = self.spectro_spike_test.summary(now_ms=now_ms)
        if summary.active:
            status = "测试中"
        elif summary.started_at_ms is not None:
            status = (
                "已完成（到时自动结束）"
                if self.spectro_spike_auto_completed
                else "已结束"
            )
        else:
            status = "未开始"
        if summary.counter_reset_detected:
            status += "（ADS 计数器已重置）"
        self.spectro_spike_status_value.setText(status)
        selected_duration_s = int(self.spectro_spike_duration_combo.currentData())
        target_duration_s = (
            summary.target_duration_s
            if summary.started_at_ms is not None
            else selected_duration_s
        )
        remaining_s = (
            summary.remaining_s
            if summary.started_at_ms is not None
            else float(selected_duration_s)
        )
        self.spectro_spike_time_value.setText(
            f"{summary.duration_s:.1f}/{target_duration_s} s · "
            f"剩余 {remaining_s:.1f} s · {summary.sample_count} 点 / "
            f"{_format_rate(summary.receive_rate_hz)}"
        )
        self.spectro_spike_drop_value.setText(
            f">5 {summary.drop_count_5mv} / "
            f">10 {summary.drop_count_10mv} / "
            f">20 {summary.drop_count_20mv}"
        )
        self.spectro_spike_max_value.setText(f"{summary.max_down_mv:.2f} mV")
        self.spectro_spike_ads_value.setText(
            f"CRC {_format_counter(summary.ads_crc_error_delta)} / "
            f"Dup {_format_counter(summary.ads_duplicate_delta)} / "
            f"Drop {_format_counter(summary.ads_transient_drop_delta)}"
        )
        self.spectro_spike_start_btn.setEnabled(
            self.spectro_is_measuring and not summary.active
        )
        self.spectro_spike_stop_btn.setEnabled(summary.active)
        self.spectro_spike_export_btn.setEnabled(
            not summary.active and summary.sample_count > 0
        )
        self.spectro_spike_duration_combo.setEnabled(not summary.active)


def _format_interval(value) -> str:
    return "--" if value is None else f"{int(value)} ms"


def _format_counter(value) -> str:
    return "--" if value is None else str(int(value))


def _format_rate(value) -> str:
    return "-- Hz" if value is None else f"{value:.1f} Hz"


def _format_duration_option(duration_s: int) -> str:
    if duration_s % 60 == 0:
        return f"{duration_s // 60} 分钟"
    return f"{duration_s} 秒"
