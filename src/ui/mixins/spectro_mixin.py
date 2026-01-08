"""光谱仪控制 Mixin 模块。

该模块提供光谱仪相关的UI初始化和数据处理功能，包括：
- NI DAQ 设备管理和通道选择
- 实时电压和吸光度测量
- 数据可视化（使用 pyqtgraph）
- 数据保存为 CSV 格式

依赖:
    - nidaqmx: NI 数据采集硬件驱动
    - pyqtgraph: 高性能图表库
"""

from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.hardware.daq_thread import DAQThread

# 可选依赖
try:
    import nidaqmx
    import pyqtgraph as pg

    NIDAQMX_AVAILABLE = True
except ImportError:
    NIDAQMX_AVAILABLE = False
    nidaqmx = None  # type: ignore
    pg = None  # type: ignore


class SpectroMixin:
    """光谱仪控制功能 Mixin。

    提供 NI DAQ 数据采集、实时电压/吸光度测量和数据可视化功能。

    Attributes:
        spectro_reference_voltage: 参考电压值（用于计算吸光度）
        spectro_is_measuring: 当前是否正在测量
        spectro_sample_rate: 采样率（Hz）
        spectro_voltage_data: 电压数据缓冲区
        spectro_absorbance_data: 吸光度数据缓冲区
    """

    def _spectro_init_vars(self) -> None:
        """初始化所有光谱仪相关的实例变量。"""
        self.spectro_reference_voltage: Optional[float] = None
        self.spectro_is_measuring: bool = False
        self.spectro_task: Any = None
        self.spectro_voltage_data: list[float] = []
        self.spectro_absorbance_data: list[float] = []
        self.spectro_max_data_points: int = 500
        self.spectro_sample_rate: int = 100
        self.spectro_data_log: list[dict[str, float]] = []
        self.spectro_daq_thread: Optional[DAQThread] = None
        self.spectro_timer = QTimer(self)  # type: ignore[arg-type]
        self.spectro_timer.setTimerType(Qt.PreciseTimer)
        self.spectro_timer.timeout.connect(self._spectro_update_charts)

    def init_spectro_tab(self):
        """初始化光谱分析标签页的UI。"""
        if not NIDAQMX_AVAILABLE:
            # 如果库不可用，显示一个提示信息
            layout = QVBoxLayout(self.spectro_tab)
            label = QLabel("光谱仪功能不可用，因为缺少必要的依赖库\n(nidaqmx, pyqtgraph, scipy)。")
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont("Microsoft YaHei", 14))
            layout.addWidget(label)
            return

        main_layout = QHBoxLayout(self.spectro_tab)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧控制面板
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(10)

        # 右侧图表面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])  # 设置初始大小比例

        # 填充左右面板
        self._spectro_create_device_selection_group(left_layout)
        self._spectro_create_measurement_group(left_layout)
        self._spectro_create_control_buttons(left_layout)
        left_layout.addStretch(1)

        self._spectro_create_charts_group(right_layout)

    def _spectro_create_device_selection_group(self, parent_layout):
        group = QGroupBox("设备选择")
        layout = QFormLayout()
        layout.setSpacing(8)

        self.spectro_device_combo = QComboBox()
        self.spectro_channel_combo = QComboBox()
        self.spectro_rate_spin = QSpinBox()
        self.spectro_rate_spin.setRange(1, 1000)
        self.spectro_rate_spin.setValue(self.spectro_sample_rate)
        self.spectro_rate_spin.valueChanged.connect(self._spectro_update_sample_rate)
        refresh_btn = QPushButton("刷新设备")
        refresh_btn.clicked.connect(self._spectro_refresh_devices)

        layout.addRow("设备:", self.spectro_device_combo)
        layout.addRow("通道:", self.spectro_channel_combo)
        layout.addRow("采样率 (Hz):", self.spectro_rate_spin)
        layout.addRow(refresh_btn)

        group.setLayout(layout)
        parent_layout.addWidget(group)

        self.spectro_device_combo.currentIndexChanged.connect(self._spectro_update_channels)

    def _spectro_create_measurement_group(self, parent_layout):
        group = QGroupBox("实时测量")
        layout = QFormLayout()
        layout.setSpacing(8)

        self.spectro_voltage_value = QLabel("0.0000 V")
        self.spectro_voltage_value.setStyleSheet(
            "font-size: 20px; color: #007AFF; font-weight: bold;"
        )
        self.spectro_absorbance_value = QLabel("0.0000")
        self.spectro_absorbance_value.setStyleSheet(
            "font-size: 20px; color: #FF2D55; font-weight: bold;"
        )
        self.spectro_ref_value = QLabel("未设置")
        self.spectro_ref_value.setStyleSheet("font-size: 16px; color: #5856D6;")

        layout.addRow("电压:", self.spectro_voltage_value)
        layout.addRow("吸光度:", self.spectro_absorbance_value)
        layout.addRow("参考电压:", self.spectro_ref_value)

        group.setLayout(layout)
        parent_layout.addWidget(group)

    def _spectro_create_control_buttons(self, parent_layout):
        group = QGroupBox("操作控制")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        self.spectro_start_btn = QPushButton("开始测量")
        self.spectro_start_btn.clicked.connect(self._spectro_toggle_measurement)
        self.spectro_ref_btn = QPushButton("设置参考")
        self.spectro_ref_btn.clicked.connect(self._spectro_set_reference)
        self.spectro_ref_btn.setEnabled(False)
        self.spectro_clear_btn = QPushButton("清除数据")
        self.spectro_clear_btn.clicked.connect(self._spectro_clear_data)
        self.spectro_save_btn = QPushButton("保存数据")
        self.spectro_save_btn.clicked.connect(self._spectro_save_data)

        layout.addWidget(self.spectro_start_btn)
        layout.addWidget(self.spectro_ref_btn)
        layout.addWidget(self.spectro_clear_btn)
        layout.addWidget(self.spectro_save_btn)

        group.setLayout(layout)
        parent_layout.addWidget(group)

    def _spectro_create_charts_group(self, parent_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        charts_container = QWidget()
        charts_layout = QVBoxLayout(charts_container)
        charts_layout.setSpacing(15)

        # Voltage Plot
        voltage_group = QGroupBox("电压 (V)")
        v_layout = QVBoxLayout(voltage_group)
        self.spectro_voltage_plot = pg.PlotWidget()
        self.spectro_voltage_plot.setBackground("w")
        self.spectro_voltage_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_voltage_curve = self.spectro_voltage_plot.plot(
            pen=pg.mkPen(color="#007AFF", width=2)
        )
        self.spectro_voltage_plot.setMinimumHeight(200)
        v_layout.addWidget(self.spectro_voltage_plot)
        charts_layout.addWidget(voltage_group)

        # Absorbance Plot
        absorbance_group = QGroupBox("吸光度 (Abs)")
        a_layout = QVBoxLayout(absorbance_group)
        self.spectro_absorbance_plot = pg.PlotWidget()
        self.spectro_absorbance_plot.setBackground("w")
        self.spectro_absorbance_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_absorbance_curve = self.spectro_absorbance_plot.plot(
            pen=pg.mkPen(color="#FF2D55", width=2)
        )
        self.spectro_absorbance_plot.setMinimumHeight(200)
        a_layout.addWidget(self.spectro_absorbance_plot)
        charts_layout.addWidget(absorbance_group)

        scroll_area.setWidget(charts_container)
        parent_layout.addWidget(scroll_area)

    def _spectro_refresh_devices(self):
        try:
            system = nidaqmx.system.System.local()
            devices = system.devices
            self.spectro_device_combo.clear()
            for device in devices:
                self.spectro_device_combo.addItem(device.name)
            if self.spectro_device_combo.count() > 0:
                self.log(f"找到 {len(devices)} 个NI设备")
                self._spectro_update_channels()
            else:
                self.log("未找到NI设备")
        except Exception as e:
            self.log(f"刷新NI设备错误: {e}")

    def _spectro_update_channels(self):
        try:
            device_name = self.spectro_device_combo.currentText()
            if not device_name:
                return
            device = nidaqmx.system.Device(device_name)
            ai_ports = [ch.name for ch in device.ai_physical_chans]
            self.spectro_channel_combo.clear()
            self.spectro_channel_combo.addItems(ai_ports)
        except Exception as e:
            self.log(f"更新通道错误: {e}")

    def _spectro_update_sample_rate(self, rate):
        self.spectro_sample_rate = rate
        self.status_bar.showMessage(f"采样率设置为 {rate} Hz")

    def _spectro_toggle_measurement(self):
        if not self.spectro_is_measuring:
            try:
                device = self.spectro_device_combo.currentText()
                channel = self.spectro_channel_combo.currentText()
                if not device or not channel:
                    self.log("请选择设备和通道")
                    return

                if self.spectro_daq_thread and self.spectro_daq_thread.isRunning():
                    self.spectro_daq_thread.stop()

                self.spectro_daq_thread = DAQThread(device, channel, self.spectro_sample_rate)
                self.spectro_daq_thread.data_acquired.connect(self._spectro_handle_acquired_data)
                self.spectro_daq_thread.error_occurred.connect(self._spectro_handle_daq_error)
                self.spectro_daq_thread.start()

                self.spectro_is_measuring = True
                self.spectro_start_btn.setText("停止测量")
                self.spectro_ref_btn.setEnabled(True)
                self.status_bar.showMessage("测量中...")
                self.log("光谱仪开始测量")
                self.spectro_timer.start(100)  # 10Hz 更新图表
                self.spectro_start_time = time.time()
            except Exception as e:
                self.log(f"开始测量失败: {e}")
                self.spectro_is_measuring = False
                self.spectro_start_btn.setText("开始测量")
        else:
            self._spectro_stop_measurement()

    def _spectro_stop_measurement(self):
        if self.spectro_timer.isActive():
            self.spectro_timer.stop()
        if self.spectro_daq_thread and self.spectro_daq_thread.isRunning():
            self.spectro_daq_thread.stop()

        self.spectro_is_measuring = False
        self.spectro_start_btn.setText("开始测量")
        self.spectro_ref_btn.setEnabled(False)
        self.status_bar.showMessage("测量已停止")
        self.log("光谱仪停止测量")

    def _spectro_handle_acquired_data(self, voltage):
        self.spectro_voltage_data.append(voltage)
        if len(self.spectro_voltage_data) > self.spectro_max_data_points:
            self.spectro_voltage_data.pop(0)

        self.spectro_voltage_value.setText(f"{voltage:.4f} V")

        absorbance = 0.0
        if self.spectro_reference_voltage is not None and self.spectro_reference_voltage > 1e-9:
            transmittance = voltage / self.spectro_reference_voltage
            absorbance = -np.log10(transmittance) if transmittance > 0 else 0.0
            self.spectro_absorbance_value.setText(f"{absorbance:.4f}")
        else:
            self.spectro_absorbance_value.setText("N/A")

        self.spectro_absorbance_data.append(absorbance)
        if len(self.spectro_absorbance_data) > self.spectro_max_data_points:
            self.spectro_absorbance_data.pop(0)

        timestamp = time.time() - self.spectro_start_time
        self.spectro_data_log.append(
            {
                "timestamp": timestamp,
                "voltage": voltage,
                "absorbance": absorbance,
            }
        )

    def _spectro_handle_daq_error(self, error_msg):
        self.log(f"DAQ 错误: {error_msg}")
        self._spectro_stop_measurement()
        QMessageBox.critical(self, "测量错误", error_msg)

    def _spectro_set_reference(self):
        if self.spectro_is_measuring and len(self.spectro_voltage_data) > 0:
            avg_voltage = np.mean(self.spectro_voltage_data[-5:])
            self.spectro_reference_voltage = avg_voltage
            self.spectro_ref_value.setText(f"{self.spectro_reference_voltage:.4f} V")
            self.log(f"参考电压设置为 {self.spectro_reference_voltage:.4f} V")

    def _spectro_clear_data(self):
        self.spectro_voltage_data.clear()
        self.spectro_absorbance_data.clear()
        self.spectro_data_log.clear()
        self._spectro_update_charts()
        self.log("光谱数据已清除")

    def _spectro_update_charts(self):
        self.spectro_voltage_curve.setData(self.spectro_voltage_data)
        self.spectro_absorbance_curve.setData(self.spectro_absorbance_data)

    def _spectro_save_data(self):
        if not self.spectro_data_log:
            QMessageBox.warning(self, "保存错误", "没有数据可以保存")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"absorbance_data_{timestamp}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "保存数据", filename, "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="") as csvfile:
                fieldnames = ["timestamp", "voltage", "absorbance"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.spectro_data_log)
            self.log(f"光谱数据已保存至 {os.path.basename(path)}")
        except Exception as e:
            self.log(f"保存数据失败: {e}")
            QMessageBox.critical(self, "保存错误", f"文件保存失败: {e}")
