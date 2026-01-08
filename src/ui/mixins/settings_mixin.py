"""设置管理 Mixin 模块。

该模块提供应用设置的保存和加载功能，包括：
- UI设置保存到JSON文件
- 从JSON文件加载UI设置
- 预设组合框更新

Note:
    此模块设计为 Mixin 类，需要与 QMainWindow 子类一起使用。
"""

import json
import os
from typing import Dict, Any

from PySide6.QtWidgets import QApplication

# 检查NIDAQMX是否可用
try:
    import nidaqmx
    NIDAQMX_AVAILABLE = True
except ImportError:
    NIDAQMX_AVAILABLE = False


class SettingsMixin:
    """设置管理功能 Mixin。

    提供应用设置的保存、加载和预设管理功能。

    Attributes:
        settings_manager: 设置管理器实例
        settings_file: 设置文件路径
        presets: 预设字典
    """

    def save_settings(self) -> None:
        """将当前UI设置保存到JSON文件。"""
        # 使用settings_manager的内部设置，确保保留motor配置
        self.settings_manager.load()

        # 更新UI相关设置到settings_manager
        self.settings_manager.set_section(
            "serial",
            {"port": self.port_combo.currentText(), "baudrate": self.baud_combo.currentText()}
        )
        self.settings_manager.set_section(
            "window", {"width": self.size().width(), "height": self.size().height()}
        )
        self.settings_manager.set_section(
            "calibration",
            {
                "enabled": self.auto_cal_switch.isChecked(),
                "amplitude": self.calibration_amp_input.text(),
            }
        )

        # 仅当光谱仪库可用时才保存相关设置
        if NIDAQMX_AVAILABLE:
            self.settings_manager.set_section(
                "spectrometer",
                {
                    "device": self.spectro_device_combo.currentText(),
                    "channel": self.spectro_channel_combo.currentText(),
                    "rate": self.spectro_rate_spin.value(),
                }
            )

        # 保存 PID 参数设置
        if hasattr(self, 'pid_optimizer_panel'):
            self.settings_manager.set_section(
                "pid_params",
                {
                    "Kp": self.pid_optimizer_panel.kp_input.value(),
                    "Ki": self.pid_optimizer_panel.ki_input.value(),
                    "Kd": self.pid_optimizer_panel.kd_input.value(),
                }
            )

        # 使用settings_manager保存
        if self.settings_manager.save():
            self.log("设置已成功保存。")
        else:
            self.log("保存设置时出错。")

    def load_settings(self) -> None:
        """从JSON文件加载UI设置。"""
        if not os.path.exists(self.settings_file):
            self.log("未找到设置文件，使用默认值。")
            return

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)

            # 加载串口设置
            serial_settings = settings.get("serial", {})
            if "port" in serial_settings:
                saved_port = serial_settings["port"]
                available_ports = [
                    self.port_combo.itemText(i) for i in range(self.port_combo.count())
                ]
                if saved_port in available_ports:
                    self.port_combo.setCurrentText(saved_port)
                elif available_ports:
                    self.port_combo.setCurrentIndex(0)
            if "baudrate" in serial_settings:
                self.baud_combo.setCurrentText(serial_settings["baudrate"])

            # 加载窗口尺寸
            window_settings = settings.get("window", {})
            if "width" in window_settings and "height" in window_settings:
                self.resize(window_settings["width"], window_settings["height"])

            # 加载自动校准设置
            cal_settings = settings.get("calibration", {})
            if "enabled" in cal_settings:
                self.auto_cal_switch.setChecked(cal_settings["enabled"])
            if "amplitude" in cal_settings:
                self.calibration_amp_input.setText(cal_settings["amplitude"])

            # 加载光谱仪设置
            if NIDAQMX_AVAILABLE:
                spectro_settings = settings.get("spectrometer", {})
                if "device" in spectro_settings:
                    saved_device = spectro_settings["device"]
                    available_devices = [
                        self.spectro_device_combo.itemText(i)
                        for i in range(self.spectro_device_combo.count())
                    ]
                    if saved_device in available_devices:
                        self.spectro_device_combo.setCurrentText(saved_device)

                QApplication.processEvents()  # 等待UI响应设备更改

                if "channel" in spectro_settings:
                    saved_channel = spectro_settings["channel"]
                    available_channels = [
                        self.spectro_channel_combo.itemText(i)
                        for i in range(self.spectro_channel_combo.count())
                    ]
                    if saved_channel in available_channels:
                        self.spectro_channel_combo.setCurrentText(saved_channel)

                if "rate" in spectro_settings:
                    self.spectro_rate_spin.setValue(spectro_settings["rate"])

            # 加载零点偏移量
            self.angle_offsets = self.settings_manager.get_angle_offsets()
            self._update_offset_labels()
            self.log(f"零点偏移量已加载: {self.angle_offsets}")

            # 加载 PID 参数设置
            pid_params = settings.get("pid_params", {})
            if pid_params and hasattr(self, 'pid_optimizer_panel'):
                if "Kp" in pid_params:
                    self.pid_optimizer_panel.kp_input.setValue(pid_params["Kp"])
                if "Ki" in pid_params:
                    self.pid_optimizer_panel.ki_input.setValue(pid_params["Ki"])
                if "Kd" in pid_params:
                    self.pid_optimizer_panel.kd_input.setValue(pid_params["Kd"])
                self.log(f"PID参数已加载: Kp={pid_params.get('Kp', 0.14):.4f}, Ki={pid_params.get('Ki', 0.015):.5f}, Kd={pid_params.get('Kd', 0.06):.4f}")

            self.log("设置已成功加载。")
        except Exception as e:
            self.log(f"加载设置时出错: {str(e)}。将使用默认值。")

    def update_preset_combos(self) -> None:
        """更新预设组合框。"""
        manual_presets = [k[7:] for k in self.presets if k.startswith("manual_")]
        self.manual_preset_combo.clear()
        self.manual_preset_combo.addItems(sorted(manual_presets))

        auto_presets = [k[5:] for k in self.presets if k.startswith("auto_")]
        self.auto_preset_combo.clear()
        self.auto_preset_combo.addItems(sorted(auto_presets))
