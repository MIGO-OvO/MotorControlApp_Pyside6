"""手动控制 Mixin 模块。

该模块提供手动控制页面相关功能，包括：
- 电机手动控制UI和命令发送
- 定时运行功能（运行/暂停/继续/取消）
- 手动预设管理（保存/加载）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class ManualMixin:
    """手动控制功能 Mixin。

    提供电机手动控制、定时运行和预设管理功能。

    Attributes:
        motor_widgets: 电机控制组件字典
        timer: 定时运行计时器
        remaining_seconds: 剩余运行时间（秒）
    """

    def init_manual_tab(self) -> None:
        """初始化手动控制标签页的UI。"""
        layout = QVBoxLayout(self.manual_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # 微泵控制区
        motor_frame = QFrame()
        grid_layout = QGridLayout(motor_frame)
        self.motor_widgets = {}

        # 存储手动控制页的GroupBox引用，用于刷新标题
        self.manual_motor_groups = {}

        motors = [("X", 0, 0), ("Y", 0, 1), ("Z", 1, 0), ("A", 1, 1)]
        for motor, row, col in motors:
            # 获取备注并生成标题
            note = self.settings_manager.get_pump_note(motor)
            title = f"微泵 {motor} ({note})" if note else f"微泵 {motor}"
            group = QGroupBox(title)
            group.setFont(QFont("Microsoft YaHei", 16))
            self.manual_motor_groups[motor] = group

            # 启用右键菜单
            group.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            group.customContextMenuRequested.connect(
                lambda pos, m=motor, g=group: self.show_pump_note_menu(m, pos, g)
            )

            vbox = QVBoxLayout(group)

            # 启用和持续开关
            switch_frame = QFrame()
            hbox = QHBoxLayout(switch_frame)
            enable_check = QCheckBox("启用")
            enable_check.setFont(QFont("Microsoft YaHei", 16))
            continuous_check = QCheckBox("持续")
            continuous_check.setFont(QFont("Microsoft YaHei", 16))
            hbox.addWidget(enable_check)
            hbox.addWidget(continuous_check)
            vbox.addWidget(switch_frame)

            # 方向选择
            dir_group = QButtonGroup(self)
            dir_frame = QFrame()
            hbox_dir = QHBoxLayout(dir_frame)
            forward_btn = QRadioButton("正转")
            backward_btn = QRadioButton("反转")
            forward_btn.setFont(QFont("Microsoft YaHei", 16))
            backward_btn.setFont(QFont("Microsoft YaHei", 16))
            dir_group.addButton(forward_btn)
            dir_group.addButton(backward_btn)
            forward_btn.setChecked(True)
            hbox_dir.addWidget(forward_btn)
            hbox_dir.addWidget(backward_btn)
            vbox.addWidget(dir_frame)

            # 参数输入
            speed_entry = QLineEdit()
            speed_entry.setPlaceholderText("速度值 (RPM)")
            speed_entry.setFont(QFont("Microsoft YaHei", 16))
            speed_entry.setFixedHeight(40)
            vbox.addWidget(speed_entry)

            angle_entry = QLineEdit()
            angle_entry.setPlaceholderText("角度")
            angle_entry.setFont(QFont("Microsoft YaHei", 16))
            angle_entry.setFixedHeight(40)
            vbox.addWidget(angle_entry)

            self.motor_widgets[motor] = {
                "enable": enable_check,
                "direction": dir_group,
                "speed": speed_entry,
                "angle": angle_entry,
                "continuous": continuous_check,
            }

            grid_layout.addWidget(group, row, col)

        layout.addWidget(motor_frame)

        # 控制按钮区
        control_frame = QFrame()
        hbox = QHBoxLayout(control_frame)

        send_btn = QPushButton("发送指令")
        send_btn.setFont(QFont("Microsoft YaHei", 16))
        send_btn.setFixedHeight(40)
        send_btn.clicked.connect(self.send_manual_command)
        hbox.addWidget(send_btn)

        # 预设管理
        preset_frame = QFrame()
        preset_layout = QHBoxLayout(preset_frame)
        preset_lbl = QLabel("手动预设:")
        preset_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.manual_preset_combo = QComboBox()
        self.manual_preset_combo.setFont(QFont("Microsoft YaHei", 16))
        self.manual_preset_combo.setFixedWidth(150)

        load_btn = QPushButton("加载")
        load_btn.setFont(QFont("Microsoft YaHei", 16))
        load_btn.clicked.connect(self.load_manual_preset)

        save_btn = QPushButton("保存")
        save_btn.setFont(QFont("Microsoft YaHei", 16))
        save_btn.clicked.connect(self.save_manual_preset)

        del_manual_btn = QPushButton("删除")
        del_manual_btn.clicked.connect(lambda: self.delete_preset("manual"))

        preset_layout.addWidget(preset_lbl)
        preset_layout.addWidget(self.manual_preset_combo)
        preset_layout.addWidget(load_btn)
        preset_layout.addWidget(save_btn)
        preset_layout.addWidget(del_manual_btn)
        hbox.addWidget(preset_frame)

        layout.addWidget(control_frame)

        # 定时运行控件
        timer_frame = QFrame()
        timer_layout = QHBoxLayout(timer_frame)

        timer_label = QLabel("定时运行:")
        timer_label.setFont(QFont("Microsoft YaHei", 16))

        self.timer_input = QLineEdit()
        self.timer_input.setPlaceholderText("时长")
        self.timer_input.setFont(QFont("Microsoft YaHei", 16))
        self.timer_input.setFixedWidth(100)

        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["秒", "分钟", "小时"])
        self.time_unit_combo.setFont(QFont("Microsoft YaHei", 16))
        self.time_unit_combo.setFixedWidth(100)

        # 按钮容器
        btn_container = QFrame()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.timer_run_btn = QPushButton("运行")
        self.timer_run_btn.setFont(QFont("Microsoft YaHei", 16))
        self.timer_run_btn.clicked.connect(self.start_timed_run)

        self.timer_pause_btn = QPushButton("暂停")
        self.timer_pause_btn.setFont(QFont("Microsoft YaHei", 16))
        self.timer_pause_btn.clicked.connect(self.pause_timed_run)
        self.timer_pause_btn.setEnabled(False)

        self.timer_resume_btn = QPushButton("继续")
        self.timer_resume_btn.setFont(QFont("Microsoft YaHei", 16))
        self.timer_resume_btn.clicked.connect(self.resume_timed_run)
        self.timer_resume_btn.setEnabled(False)

        self.timer_cancel_btn = QPushButton("取消")
        self.timer_cancel_btn.setFont(QFont("Microsoft YaHei", 16))
        self.timer_cancel_btn.clicked.connect(self.cancel_timed_run)
        self.timer_cancel_btn.setEnabled(False)

        btn_layout.addWidget(self.timer_run_btn)
        btn_layout.addWidget(self.timer_pause_btn)
        btn_layout.addWidget(self.timer_resume_btn)
        btn_layout.addWidget(self.timer_cancel_btn)

        timer_layout.addWidget(timer_label)
        timer_layout.addWidget(self.timer_input)
        timer_layout.addWidget(self.time_unit_combo)
        timer_layout.addWidget(btn_container)
        layout.addWidget(timer_frame)

        # 定时器相关初始化
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.remaining_seconds = 0
        self.is_paused = False
        self.paused_seconds = 0

    def start_timed_run(self):
        try:
            duration = float(self.timer_input.text())
            unit = self.time_unit_combo.currentText()

            if unit == "分钟":
                duration *= 60
            elif unit == "小时":
                duration *= 3600

            if duration <= 0:
                raise ValueError("时长必须大于0")

        except ValueError as e:
            QMessageBox.critical(self, "输入错误", str(e))
            return

        if not self.send_continuous_run_command():
            return

        self.remaining_seconds = int(duration)
        self.timer.start(1000)
        self.timer_run_btn.setEnabled(False)
        self.update_status_message()
        self.timer_run_btn.setEnabled(False)
        self.timer_pause_btn.setEnabled(True)
        self.timer_cancel_btn.setEnabled(True)
        self.timer_resume_btn.setEnabled(False)
        self.is_paused = False

    def send_continuous_run_command(self):
        command = ""
        for motor in ["X", "Y", "Z", "A"]:
            widgets = self.motor_widgets[motor]
            if widgets["enable"].isChecked():
                speed = widgets["speed"].text()
                if not speed.isdigit():
                    QMessageBox.critical(self, "错误", f"电机{motor}速度值无效")
                    return False
                direction = "F" if widgets["direction"].checkedButton().text() == "正转" else "B"
                command += f"{motor}E{direction}V{speed}JG"

        if not command:
            QMessageBox.critical(self, "错误", "没有启用的电机")
            return False

        return self.send_command(command + "\r\n")

    def update_timer(self):
        if not self.is_paused:
            self.remaining_seconds -= 1
            if self.remaining_seconds <= 0:
                self.stop_timed_run()
                self.send_stop_command()
            self.update_status_message()

    def update_status_message(self):
        mins, secs = divmod(self.remaining_seconds, 60)
        hours, mins = divmod(mins, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
        self.status_bar.showMessage(f"运行中 - 剩余时间: {time_str}")

    def pause_timed_run(self):
        command = "".join([f"{motor}DFV0J0" for motor in ["X", "Y", "Z", "A"]])
        self.send_command(command + "\r\n")
        self.timer.stop()
        self.is_paused = True
        self.paused_seconds = self.remaining_seconds

        self.timer_pause_btn.setEnabled(False)
        self.timer_resume_btn.setEnabled(True)
        self.status_bar.showMessage(
            f"运行已暂停，剩余时间: {self.format_time(self.paused_seconds)}"
        )

    def resume_timed_run(self):
        if not self.send_continuous_run_command():
            return
        self.remaining_seconds = self.paused_seconds
        self.timer.start(1000)
        self.is_paused = False

        self.timer_pause_btn.setEnabled(True)
        self.timer_resume_btn.setEnabled(False)
        self.update_status_message()

    def cancel_timed_run(self):
        self.timer.stop()
        self.send_stop_command()
        self.remaining_seconds = 0
        self.is_paused = False

        self.timer_run_btn.setEnabled(True)
        self.timer_pause_btn.setEnabled(False)
        self.timer_resume_btn.setEnabled(False)
        self.timer_cancel_btn.setEnabled(False)
        self.status_bar.showMessage("运行已取消")

    def format_time(self, seconds):
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def stop_timed_run(self):
        self.timer.stop()
        self.timer_run_btn.setEnabled(True)
        self.timer_pause_btn.setEnabled(False)
        self.timer_resume_btn.setEnabled(False)
        self.timer_cancel_btn.setEnabled(False)
        self.status_bar.showMessage("定时运行完成")

    def send_stop_command(self):
        command = "".join([f"{motor}DFV0J0" for motor in ["X", "Y", "Z", "A"]])
        self.send_command(command + "\r\n")

    def send_manual_command(self):
        """发送手动控制指令"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        self.running_mode = "manual"

        # 收集参数并生成指令
        step_params = {}
        for motor in ["X", "Y", "Z", "A"]:
            widgets = self.motor_widgets[motor]
            if widgets["enable"].isChecked():
                step_params[motor] = {
                    "enable": "E",  # 必须添加启用标志，否则 generate_command 会跳过
                    "direction": (
                        "F" if widgets["direction"].checkedButton().text() == "正转" else "B"
                    ),
                    "speed": widgets["speed"].text() or "0",
                    "angle": widgets["angle"].text() or "0",
                    "continuous": widgets["continuous"].isChecked(),
                }

        if not step_params:
            QMessageBox.warning(self, "警告", "请至少启用一个电机")
            return

        # 生成指令
        command = self.generate_command(step_params)
        if command:
            self.send_command(command)

    def save_manual_preset(self):
        """保存手动控制预设"""
        name, ok = QInputDialog.getText(self, "保存预设", "请输入预设名称:")
        if not ok or not name:
            return

        preset_data = {}
        for motor in ["X", "Y", "Z", "A"]:
            widgets = self.motor_widgets[motor]
            preset_data[motor] = {
                "enable": widgets["enable"].isChecked(),
                "direction": "F" if widgets["direction"].checkedButton().text() == "正转" else "B",
                "speed": widgets["speed"].text(),
                "angle": widgets["angle"].text(),
                "continuous": widgets["continuous"].isChecked(),
            }

        self._preset_manager.save_manual_preset(name, preset_data)
        self.update_preset_combos()
        self.log(f"手动预设 '{name}' 已保存")

    def load_manual_preset(self):
        """加载手动控制预设"""
        name = self.manual_preset_combo.currentText()
        if not name:
            return

        preset_data = self._preset_manager.load_manual_preset(name)
        if not preset_data:
            self.log(f"预设 '{name}' 不存在")
            return

        for motor, data in preset_data.items():
            if motor in self.motor_widgets:
                widgets = self.motor_widgets[motor]
                # 兼容旧版预设数据格式（enable可能是字符串"E"/"D"或布尔值）
                enable_val = data.get("enable", False)
                if isinstance(enable_val, str):
                    enable_val = enable_val == "E" or enable_val.lower() == "true"
                widgets["enable"].setChecked(bool(enable_val))
                widgets["speed"].setText(str(data.get("speed", "")))
                widgets["angle"].setText(str(data.get("angle", "")))
                # continuous也需要类型转换
                continuous_val = data.get("continuous", False)
                if isinstance(continuous_val, str):
                    continuous_val = continuous_val.lower() == "true"
                widgets["continuous"].setChecked(bool(continuous_val))

                # 设置方向
                direction = data.get("direction", "F")
                for btn in widgets["direction"].buttons():
                    if (direction == "F" and btn.text() == "正转") or (
                        direction == "B" and btn.text() == "反转"
                    ):
                        btn.setChecked(True)
                        break

        self.log(f"手动预设 '{name}' 已加载")
