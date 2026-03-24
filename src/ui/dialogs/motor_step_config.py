"""微泵步骤配置对话框"""

import weakref
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from ...config.constants import MOTOR_NAMES
from ...config.settings import SettingsManager


class MotorStepConfig(QDialog):
    """微泵步骤配置对话框"""

    def __init__(self, parent, step_num: int, initial_params: Optional[Dict] = None):
        """
        初始化对话框

        Args:
            parent: 父窗口
            step_num: 步骤编号
            initial_params: 初始参数
        """
        super().__init__(parent)
        self.parent = weakref.ref(parent)
        self.step_params = initial_params or {}
        self.setWindowTitle(f"步骤 {step_num} 参数配置")
        self.setFixedSize(500, 780)
        self.setWindowModality(Qt.ApplicationModal)
        self.init_ui()
        self.load_initial_params()

    def init_ui(self):
        """初始化UI"""
        layout = QGridLayout()
        self.widgets = {}

        # 获取设置管理器用于读取备注
        self._settings_manager = None
        parent_ref = self.parent()
        if parent_ref and hasattr(parent_ref, "settings_manager"):
            self._settings_manager = parent_ref.settings_manager
        else:
            # 如果父窗口没有settings_manager，创建一个临时的
            self._settings_manager = SettingsManager("data/settings.json")
            self._settings_manager.load()

        # 步骤名称
        name_frame = QFrame()
        hbox = QHBoxLayout(name_frame)
        name_lbl = QLabel("步骤名称:")
        name_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.name_entry = QLineEdit()
        self.name_entry.setFont(QFont("Microsoft YaHei", 16))
        self.name_entry.setFixedHeight(40)
        self.name_entry.setPlaceholderText("输入步骤名称")
        hbox.addWidget(name_lbl)
        hbox.addWidget(self.name_entry)
        layout.addWidget(name_frame, 0, 0, 1, 2)

        # 微泵控制区
        for i, motor in enumerate(MOTOR_NAMES):
            # 获取备注并生成标题
            note = self._settings_manager.get_pump_note(motor) if self._settings_manager else ""
            title = f"微泵 {motor} ({note})" if note else f"微泵 {motor}"
            group = QGroupBox(title)
            group.setFont(QFont("Microsoft YaHei", 13))
            vbox = QVBoxLayout(group)

            # 启用开关
            enable_check = QCheckBox("启用微泵")
            enable_check.setFont(QFont("Microsoft YaHei", 16))
            vbox.addWidget(enable_check)

            # 方向选择
            dir_group = QButtonGroup(self)
            dir_frame = QFrame()
            hbox = QHBoxLayout(dir_frame)
            forward_btn = QRadioButton("正转")
            backward_btn = QRadioButton("反转")
            forward_btn.setFont(QFont("Microsoft YaHei", 16))
            backward_btn.setFont(QFont("Microsoft YaHei", 16))
            dir_group.addButton(forward_btn)
            dir_group.addButton(backward_btn)
            forward_btn.setChecked(True)
            hbox.addWidget(forward_btn)
            hbox.addWidget(backward_btn)
            vbox.addWidget(dir_frame)

            # 速度和角度输入
            speed_entry = QLineEdit()
            speed_entry.setPlaceholderText("速度值 (RPM)")
            speed_entry.setFont(QFont("Microsoft YaHei", 16))
            speed_entry.setFixedHeight(40)
            vbox.addWidget(speed_entry)

            angle_entry = QLineEdit()
            angle_entry.setPlaceholderText("角度值")
            angle_entry.setFont(QFont("Microsoft YaHei", 16))
            angle_entry.setFixedHeight(40)
            vbox.addWidget(angle_entry)

            self.widgets[motor] = {
                "enable": enable_check,
                "direction": dir_group,
                "speed": speed_entry,
                "angle": angle_entry,
            }

            layout.addWidget(group, (i // 2) + 1, i % 2)

        # 进样泵控制
        pump_group = QGroupBox("进样泵控制")
        pump_group.setFont(QFont("Microsoft YaHei", 13))
        pump_vbox = QVBoxLayout(pump_group)

        # 启用开关
        self.pump_enable_check = QCheckBox("启用进样泵")
        self.pump_enable_check.setFont(QFont("Microsoft YaHei", 16))
        pump_vbox.addWidget(self.pump_enable_check)

        # 转速设置
        pump_speed_frame = QFrame()
        pump_speed_layout = QHBoxLayout(pump_speed_frame)
        pump_speed_lbl = QLabel("转速:")
        pump_speed_lbl.setFont(QFont("Microsoft YaHei", 16))
        pump_speed_layout.addWidget(pump_speed_lbl)

        self.pump_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.pump_speed_slider.setRange(0, 100)
        self.pump_speed_slider.setValue(50)
        self.pump_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.pump_speed_slider.setTickInterval(10)
        self.pump_speed_slider.valueChanged.connect(self._sync_pump_spinbox)
        pump_speed_layout.addWidget(self.pump_speed_slider)

        self.pump_speed_spinbox = QSpinBox()
        self.pump_speed_spinbox.setRange(0, 100)
        self.pump_speed_spinbox.setValue(50)
        self.pump_speed_spinbox.setSuffix("%")
        self.pump_speed_spinbox.setFont(QFont("Microsoft YaHei", 16))
        self.pump_speed_spinbox.setFixedWidth(100)
        self.pump_speed_spinbox.valueChanged.connect(self._sync_pump_slider)
        pump_speed_layout.addWidget(self.pump_speed_spinbox)

        pump_vbox.addWidget(pump_speed_frame)
        layout.addWidget(pump_group, 3, 0, 1, 2)

        # 间隔时间
        interval_frame = QFrame()
        hbox = QHBoxLayout(interval_frame)
        interval_lbl = QLabel("间隔时间(s):")
        interval_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry = QLineEdit()
        self.interval_entry.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry.setFixedHeight(40)
        hbox.addWidget(interval_lbl)
        hbox.addWidget(self.interval_entry)
        layout.addWidget(interval_frame, 4, 0, 1, 2)

        # 按钮
        btn_frame = QFrame()
        hbox_btn = QHBoxLayout(btn_frame)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = QPushButton("确认")
        confirm_btn.clicked.connect(self.save_params)
        hbox_btn.addWidget(cancel_btn)
        hbox_btn.addWidget(confirm_btn)
        layout.addWidget(btn_frame, 5, 0, 1, 2)

        self.setLayout(layout)

    def load_initial_params(self):
        """加载初始参数"""
        if self.step_params:
            self.name_entry.setText(self.step_params.get("name", ""))
            for motor in MOTOR_NAMES:
                params = self.step_params.get(motor, {})
                widgets = self.widgets[motor]
                widgets["enable"].setChecked(params.get("enable", "D") == "E")
                if params.get("direction", "F") == "F":
                    widgets["direction"].buttons()[0].setChecked(True)
                else:
                    widgets["direction"].buttons()[1].setChecked(True)
                widgets["speed"].setText(params.get("speed", ""))
                widgets["angle"].setText(params.get("angle", ""))

            # 加载进样泵参数
            pump_params = self.step_params.get("pump", {})
            self.pump_enable_check.setChecked(pump_params.get("enable", False))
            pump_speed = pump_params.get("speed", 50)
            self.pump_speed_slider.setValue(pump_speed)
            self.pump_speed_spinbox.setValue(pump_speed)

            # 转换为秒显示
            interval_ms = self.step_params.get("interval", 0)
            self.interval_entry.setText(str(interval_ms / 1000.0))

    def save_params(self):
        """保存参数"""
        try:
            params = {"name": self.name_entry.text()}
            for motor in MOTOR_NAMES:
                widgets = self.widgets[motor]
                enable = "E" if widgets["enable"].isChecked() else "D"
                direction = "F" if widgets["direction"].checkedButton().text() == "正转" else "B"

                speed_text = widgets["speed"].text().strip()
                speed = (
                    "0" if not speed_text else f"{float(speed_text):.1f}".rstrip("0").rstrip(".")
                )

                angle_text = widgets["angle"].text().strip().upper()
                if not angle_text:
                    angle = "0"
                elif angle_text == "G":
                    raise ValueError("自动化步骤不再支持角度 'G'，请填写数值")
                else:
                    angle = f"{float(angle_text):.3f}".rstrip("0").rstrip(".")

                params[motor] = {
                    "enable": enable,
                    "direction": direction,
                    "speed": speed,
                    "angle": angle,
                }

            # 保存进样泵参数
            params["pump"] = {
                "enable": self.pump_enable_check.isChecked(),
                "speed": self.pump_speed_spinbox.value(),
            }

            interval_text = self.interval_entry.text().strip()
            # 转换为毫秒保存
            params["interval"] = 5000 if not interval_text else int(float(interval_text) * 1000)

            self.step_params = params
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "输入错误", str(e))

    def _sync_pump_spinbox(self, value: int) -> None:
        """同步进样泵转速数值框。

        Args:
            value: 滑块值
        """
        self.pump_speed_spinbox.blockSignals(True)
        self.pump_speed_spinbox.setValue(value)
        self.pump_speed_spinbox.blockSignals(False)

    def _sync_pump_slider(self, value: int) -> None:
        """同步进样泵转速滑块。

        Args:
            value: 数值框值
        """
        self.pump_speed_slider.blockSignals(True)
        self.pump_speed_slider.setValue(value)
        self.pump_speed_slider.blockSignals(False)
