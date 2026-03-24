"""分光信号采集 Mixin 模块。

通过串口与下位机通信控制 ADS122C04 采集，实时接收电压数据并计算吸光度。
已移除 NI DAQ 依赖，所有采集由下位机统一完成。
"""
from __future__ import annotations
import csv, os, time
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
        self.spectro_max_data_points: int = 500
        self.spectro_data_log: list[dict] = []
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
        left = QFrame(); ll = QVBoxLayout(left); ll.setContentsMargins(5,5,5,5); ll.setSpacing(10)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([300, 700])
        self._spectro_create_ads_config_group(ll)
        self._spectro_create_measurement_group(ll)
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
        self.spectro_publish_spin.setValue(DEFAULT_ADS_CONFIG.get("publish_rate", 50))
        layout.addRow("TCA 通道:", self.spectro_tca_channel_spin)
        layout.addRow("ADS 地址:", self.spectro_ads_addr_combo)
        layout.addRow("参考源:", self.spectro_vref_combo)
        layout.addRow("增益:", self.spectro_gain_combo)
        layout.addRow("ADC 数据率:", self.spectro_rate_combo)
        layout.addRow("上传频率 (Hz):", self.spectro_publish_spin)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_measurement_group(self, parent_layout):
        group = QGroupBox("实时测量"); layout = QFormLayout(); layout.setSpacing(8)
        self.spectro_voltage_value = QLabel("0.0000 V")
        self.spectro_voltage_value.setStyleSheet("font-size: 20px; color: #007AFF; font-weight: bold;")
        self.spectro_absorbance_value = QLabel("0.0000")
        self.spectro_absorbance_value.setStyleSheet("font-size: 20px; color: #FF2D55; font-weight: bold;")
        self.spectro_ref_value = QLabel("未设置")
        self.spectro_ref_value.setStyleSheet("font-size: 16px; color: #5856D6;")
        self.spectro_status_label = QLabel("就绪")
        self.spectro_status_label.setStyleSheet("font-size: 14px; color: #8e8e93;")
        layout.addRow("电压:", self.spectro_voltage_value)
        layout.addRow("吸光度:", self.spectro_absorbance_value)
        layout.addRow("参考电压:", self.spectro_ref_value)
        layout.addRow("状态:", self.spectro_status_label)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_control_buttons(self, parent_layout):
        group = QGroupBox("操作控制"); layout = QVBoxLayout(); layout.setSpacing(8)
        self.spectro_start_btn = QPushButton("开始采集")
        self.spectro_start_btn.clicked.connect(self._spectro_toggle_measurement)
        self.spectro_ref_btn = QPushButton("设置参考")
        self.spectro_ref_btn.clicked.connect(self._spectro_set_reference)
        self.spectro_ref_btn.setEnabled(False)
        self.spectro_clear_btn = QPushButton("清除数据")
        self.spectro_clear_btn.clicked.connect(self._spectro_clear_data)
        self.spectro_save_btn = QPushButton("保存数据")
        self.spectro_save_btn.clicked.connect(self._spectro_save_data)
        for btn in [self.spectro_start_btn, self.spectro_ref_btn, self.spectro_clear_btn, self.spectro_save_btn]:
            layout.addWidget(btn)
        group.setLayout(layout); parent_layout.addWidget(group)

    def _spectro_create_charts_group(self, parent_layout):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget(); cl = QVBoxLayout(container); cl.setSpacing(15)
        vg = QGroupBox("电压 (V)"); vl = QVBoxLayout(vg)
        self.spectro_voltage_plot = pg.PlotWidget(); self.spectro_voltage_plot.setBackground("w")
        self.spectro_voltage_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_voltage_curve = self.spectro_voltage_plot.plot(pen=pg.mkPen(color="#007AFF", width=2))
        self.spectro_voltage_plot.setMinimumHeight(200); vl.addWidget(self.spectro_voltage_plot)
        cl.addWidget(vg)
        ag = QGroupBox("吸光度 (Abs)"); al = QVBoxLayout(ag)
        self.spectro_absorbance_plot = pg.PlotWidget(); self.spectro_absorbance_plot.setBackground("w")
        self.spectro_absorbance_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_absorbance_curve = self.spectro_absorbance_plot.plot(pen=pg.mkPen(color="#FF2D55", width=2))
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

    def _spectro_toggle_measurement(self):
        if not self.spectro_is_measuring:
            if not self.serial_port or not self.serial_port.is_open:
                QMessageBox.warning(self, "错误", "请先打开串口连接")
                return
            cfg_cmd = self._spectro_build_adscfg_command()
            self.send_command(cfg_cmd)
            import time as _t; _t.sleep(0.1)
            self.send_command("ADSSTART\r\n")
            self.spectro_is_measuring = True
            self.spectro_start_btn.setText("停止采集")
            self.spectro_ref_btn.setEnabled(True)
            self.spectro_status_label.setText("采集中...")
            self.spectro_start_time = time.time()
            self.spectro_timer.start(100)
            self.log("分光信号开始采集")
        else:
            self._spectro_stop_measurement()

    def _spectro_stop_measurement(self):
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
        self.log("分光信号停止采集")

    def handle_spectro_packet(self, packet: dict):
        """处理分光二进制数据包 (0xDD)。"""
        if getattr(self, "_closing", False):
            return
        voltage = packet.get("voltage", 0.0)
        raw_code = packet.get("raw_code", 0)
        status = packet.get("status", 0)

        self.spectro_voltage_data.append(voltage)
        if len(self.spectro_voltage_data) > self.spectro_max_data_points:
            self.spectro_voltage_data.pop(0)
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
        if len(self.spectro_absorbance_data) > self.spectro_max_data_points:
            self.spectro_absorbance_data.pop(0)

        ts = time.time() - self.spectro_start_time if self.spectro_start_time else 0
        self.spectro_data_log.append({
            "timestamp": ts, "raw_code": raw_code, "voltage": voltage,
            "absorbance": absorbance, "spectro_channel": packet.get("tca_channel", 0),
        })

    def _spectro_set_reference(self):
        if self.spectro_is_measuring and self.spectro_voltage_data:
            avg = float(np.mean(self.spectro_voltage_data[-10:]))
            self.spectro_reference_voltage = avg
            self.spectro_ref_value.setText(f"{avg:.4f} V")
            self.log(f"参考电压设置为 {avg:.4f} V")

    def _spectro_clear_data(self):
        self.spectro_voltage_data.clear()
        self.spectro_absorbance_data.clear()
        self.spectro_data_log.clear()
        self._spectro_update_charts()
        self.log("分光数据已清除")

    def _spectro_update_charts(self):
        if hasattr(self, "spectro_voltage_curve"):
            self.spectro_voltage_curve.setData(self.spectro_voltage_data)
        if hasattr(self, "spectro_absorbance_curve"):
            self.spectro_absorbance_curve.setData(self.spectro_absorbance_data)

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
            fields = ["timestamp", "raw_code", "voltage", "absorbance", "spectro_channel"]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.spectro_data_log)
            self.log(f"分光数据已保存至 {os.path.basename(path)}")
        except Exception as e:
            self.log(f"保存数据失败: {e}")
            QMessageBox.critical(self, "保存错误", f"文件保存失败: {e}")

