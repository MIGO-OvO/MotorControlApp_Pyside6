"""位置监控 Mixin 模块。

该模块提供电机位置监控相关功能，包括：
- 电机位置实时显示和角度监控
- 零点标定和偏移量管理
- 微泵备注管理
- PID 校准控制
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.config.constants import (
    DEFAULT_I2C_MAPPING,
    BUTTON_DANGER,
    BUTTON_SECONDARY,
    COLOR_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_ACCENT_ORANGE,
)
from src.ui.widgets import IOSSwitch, MotorCircle


class PositionMixin:
    """位置监控功能 Mixin。

    提供电机位置显示、角度监控、零点标定和微泵备注管理功能。

    Attributes:
        motors: 电机动画组件字典
        angle_labels: 角度显示标签字典
        calibration_switches: 校准开关字典
        zero_buttons: 零点标定按钮字典
        offset_labels: 偏移量显示标签字典
    """

    def init_position_tab(self) -> None:
        """初始化位置监控标签页的UI。"""
        layout = QVBoxLayout(self.position_tab)

        # 电机状态展示区 - 使用2x2网格布局
        motor_frame = QFrame()
        motor_layout = QGridLayout(motor_frame)
        motor_layout.setSpacing(10)
        self.motors = {}
        self.angle_labels = {}
        self.calibration_switches = {}  # 新增校准开关字典

        # 初始化零点标定UI字典
        self.zero_buttons = {}
        self.offset_labels = {}

        # 存储位置监控页的GroupBox引用，用于刷新标题
        self.position_motor_groups = {}

        # 2x2网格位置映射
        grid_positions = {"X": (0, 0), "Y": (0, 1), "Z": (1, 0), "A": (1, 1)}

        for motor in ["X", "Y", "Z", "A"]:
            # 获取备注并生成标题
            note = self.settings_manager.get_pump_note(motor)
            title = f"微泵 {motor} ({note})" if note else f"微泵 {motor}"
            group = QGroupBox(title)
            self.position_motor_groups[motor] = group

            # 启用右键菜单
            group.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            group.customContextMenuRequested.connect(
                lambda pos, m=motor, g=group: self.show_pump_note_menu(m, pos, g)
            )

            vbox = QVBoxLayout(group)
            vbox.setAlignment(Qt.AlignCenter)
            vbox.setSpacing(5)

            # 动画组件
            circle = MotorCircle()
            self.motors[motor] = circle

            # 角度显示
            label = QLabel("0.000°", alignment=Qt.AlignCenter)
            label.setStyleSheet(f"font-size: 24px; color: {COLOR_PRIMARY};")
            self.angle_labels[motor] = label

            # 零点标定按钮
            zero_btn = QPushButton("设为零点")
            zero_btn.setFont(QFont("Microsoft YaHei", 10))
            zero_btn.setStyleSheet("font-size: 12px; padding: 4px;")
            zero_btn.clicked.connect(lambda checked, m=motor: self.set_current_as_zero(m))
            self.zero_buttons[motor] = zero_btn

            # 偏移量显示
            offset_label = QLabel("偏移: 0.0°")
            offset_label.setAlignment(Qt.AlignCenter)
            offset_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
            self.offset_labels[motor] = offset_label

            # 复位开关
            switch_frame = QFrame()
            hbox = QHBoxLayout(switch_frame)
            hbox.setContentsMargins(0, 0, 0, 0)
            switch_label = QLabel("复位开关:")
            switch = IOSSwitch(accessible_name=f"微泵{motor}复位开关")
            self.calibration_switches[motor] = switch
            hbox.addWidget(switch_label)
            hbox.addWidget(switch)

            vbox.addWidget(circle, alignment=Qt.AlignCenter)
            vbox.addWidget(label)
            vbox.addWidget(zero_btn)
            vbox.addWidget(offset_label)
            vbox.addWidget(switch_frame)

            # 使用2x2网格布局
            row, col = grid_positions[motor]
            motor_layout.addWidget(group, row, col)

        layout.addWidget(motor_frame)

        # 控制按钮区域
        btn_frame = QFrame()
        hbox = QHBoxLayout(btn_frame)
        self.init_btn = QPushButton("微泵复位")
        self.init_btn.clicked.connect(self.start_calibration)

        # 实时角度按钮
        self.stream_btn = QPushButton("实时角度")
        self.stream_btn.setCheckable(True)
        self.stream_btn.setToolTip("开启/关闭实时角度数据流")
        self.stream_btn.clicked.connect(self.toggle_streaming)

        # 重置零点按钮
        self.reset_zero_btn = QPushButton("重置零点")
        self.reset_zero_btn.setStyleSheet(BUTTON_DANGER)
        self.reset_zero_btn.setToolTip("将所有电机当前位置设为零点")
        self.reset_zero_btn.clicked.connect(self.reset_zero_offsets)

        # 重置偏差按钮
        self.reset_deviation_btn = QPushButton("重置偏差")
        self.reset_deviation_btn.setToolTip("清除累计偏差数据并重新计算")
        self.reset_deviation_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT_ORANGE};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #8B4F00;
            }}
        """)
        self.reset_deviation_btn.clicked.connect(self.reset_deviation_data)

        for btn in [self.init_btn, self.stream_btn, self.reset_zero_btn, self.reset_deviation_btn]:
            if btn not in [self.reset_zero_btn, self.reset_deviation_btn]:  # 这两个按钮已有样式
                btn.setStyleSheet("font-size: 18px; padding: 8px;")
            hbox.addWidget(btn)

        layout.addWidget(btn_frame)

        # I2C 设置已迁移到左侧导航独立入口，这里只初始化底层数据控件。
        self._init_i2c_mapping_controls()

    def _init_i2c_mapping_controls(self) -> None:
        """初始化 I2C 通道映射控件（供设置弹窗与配置保存复用）。"""
        defaults = DEFAULT_I2C_MAPPING
        angles = defaults.get("angles", {"X": 0, "Y": 3, "Z": 4, "A": 7})
        spec_ch = defaults.get("spectro_channel", 2)

        self.i2c_map_spins = {}
        for motor in ["X", "Y", "Z", "A"]:
            spin = QSpinBox()
            spin.setRange(0, 7)
            spin.setValue(angles.get(motor, 0))
            self.i2c_map_spins[motor] = spin

        spec_spin = QSpinBox()
        spec_spin.setRange(0, 7)
        spec_spin.setValue(spec_ch)
        self.i2c_map_spins["SPEC"] = spec_spin

    def _create_i2c_mapping_group(self, parent_layout) -> None:
        """兼容保留：I2C 设置已迁移到独立对话框。"""
        self._init_i2c_mapping_controls()

    def _i2c_read_from_device(self) -> None:
        """向下位机查询当前 I2C 通道映射。"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return
        self.send_command("I2CMAP?\r\n")

    def _i2c_apply_to_device(self) -> None:
        """将 UI 上的 I2C 通道映射发送给下位机。"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return
        x = self.i2c_map_spins["X"].value()
        y = self.i2c_map_spins["Y"].value()
        z = self.i2c_map_spins["Z"].value()
        a = self.i2c_map_spins["A"].value()
        s = self.i2c_map_spins["SPEC"].value()
        cmd = f"I2CMAP:X={x},Y={y},Z={z},A={a},SPEC={s}\r\n"
        self.send_command(cmd)

    def start_calibration(self) -> None:
        """开始 PID 闭环校准流程（下位机自主完成）"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        # 收集需要校准的电机
        motors_to_cal = ""
        for motor in ["X", "Y", "Z", "A"]:
            if self.calibration_switches[motor].isChecked():
                motors_to_cal += motor

        if not motors_to_cal:
            QMessageBox.warning(self, "提示", "请至少选择一个需要校准的电机。")
            return

        # 发送 PID 校准指令（下位机自主完成闭环控制）
        command = f"CAL{motors_to_cal}\r\n"
        if self.send_command(command):
            self.calibration_in_progress = True
            self.log(f"开始 PID 校准: {motors_to_cal}")
            self.status_bar.showMessage(f"正在校准 {motors_to_cal}...")

    def stop_calibration(self):
        """停止校准"""
        if self.send_command("CALSTOP\r\n"):
            self.calibration_in_progress = False
            self.log("校准已停止")
            self.status_bar.showMessage("校准已停止")

    def handle_calibration_message(self, data):
        """处理下位机校准状态消息"""
        if data.startswith("CAL_START"):
            self.log(f"校准开始: {data}")
            self.calibration_in_progress = True

        elif data.startswith("CAL_DONE:"):
            # 单个电机完成，如 CAL_DONE:X=0.32
            motor_info = data.replace("CAL_DONE:", "")
            self.log(f"电机校准完成: {motor_info}")

        elif data.startswith("CAL_COMPLETE"):
            # 全部完成
            self.calibration_in_progress = False
            self.log("所有电机校准完成")
            self.clear_chart()
            self.status_bar.showMessage("校准完成")
            QMessageBox.information(self, "完成", "电机 PID 校准完成")

        elif data.startswith("CAL_FAIL"):
            # 校准失败
            self.calibration_in_progress = False
            error_info = data.replace("CAL_FAIL:", "")
            self.log(f"校准失败: {error_info}")
            self.status_bar.showMessage("校准失败")
            QMessageBox.warning(self, "错误", f"校准失败: {error_info}")

        elif data.startswith("CAL_STATUS"):
            # 校准进度状态
            status_info = data.replace("CAL_STATUS:", "")
            self.log(f"校准状态: {status_info}")

        elif data.startswith("CAL_STOPPED"):
            self.calibration_in_progress = False
            self.log("校准已停止")

        elif data.startswith("CAL_ERR"):
            self.log(f"校准错误: {data}")

    def toggle_streaming(self, checked: bool):
        """
        切换实时角度流模式

        Args:
            checked: 是否开启实时流
        """
        if not self.serial_port or not self.serial_port.is_open:
            self.stream_btn.setChecked(False)
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        if checked:
            self.send_command("ANGLESTREAM_START\r\n")
            self.log("实时角度流已开启")
        else:
            self.send_command("ANGLESTREAM_STOP\r\n")
            self.log("实时角度流已关闭")

    # ============= 零点标定功能 =============

    def set_current_as_zero(self, motor: str) -> None:
        """将当前角度设为零点"""
        if motor not in self.raw_angles:
            self.log(f"微泵{motor}原始角度数据不可用")
            return

        # 使用原始物理角度作为偏移量
        offset = self.raw_angles[motor]
        self.angle_offsets[motor] = offset

        # 保存到配置
        self.settings_manager.set_angle_offset(motor, offset)

        # 立即刷新显示（当前角度变为0）
        self.current_angles[motor] = 0.0
        self._update_angle_displays()
        self._update_offset_labels()

        # 日志输出
        self.log(f"微泵{motor}零点已设置: 物理角度={offset:.2f}°")

    def reset_zero_offsets(self) -> None:
        """重置所有零点偏移"""
        self.angle_offsets = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}

        # 保存到配置
        self.settings_manager.reset_angle_offsets()

        # 恢复为原始角度
        for motor in ["X", "Y", "Z", "A"]:
            self.current_angles[motor] = self.raw_angles[motor]

        self._update_angle_displays()
        self._update_offset_labels()
        self.log("所有微泵零点已重置")

    def reset_deviation_data(self) -> None:
        """重置偏差计算相关数据"""
        # 重置理论偏差相关
        self.initial_angle_base = {m: None for m in ["X", "Y", "Z", "A"]}
        self.accumulated_rotation = {m: 0.0 for m in ["X", "Y", "Z", "A"]}
        self.theoretical_deviations = {m: None for m in ["X", "Y", "Z", "A"]}
        self.theoretical_target = {m: None for m in ["X", "Y", "Z", "A"]}

        # 重置实时偏差相关
        self.pending_targets = {}
        self.expected_rotation = {"X": 0, "Y": 0, "Z": 0, "A": 0}
        self.expected_changes = {}

        # 构造数据并调用现有方法刷新表格
        data = {
            "current": {m: self.current_angles.get(m, 0.0) for m in ["X", "Y", "Z", "A"]},
            "targets": {m: None for m in ["X", "Y", "Z", "A"]},
            "theoretical": {m: None for m in ["X", "Y", "Z", "A"]},
            "realtime": {m: None for m in ["X", "Y", "Z", "A"]},
        }
        self.update_angles(data)

        self.log("偏差数据已重置")

    def _update_angle_displays(self) -> None:
        """更新所有角度相关显示"""
        # 触发现有的角度更新机制
        current_angles = {m: self.current_angles.get(m, 0.0) for m in ["X", "Y", "Z", "A"]}

        # 更新电机圆圈动画和角度标签
        for motor in ["X", "Y", "Z", "A"]:
            if motor in self.motors:
                angle = current_angles[motor]
                self.motors[motor].set_angle(-angle)  # 负号用于顺时针旋转
            if motor in self.angle_labels:
                self.angle_labels[motor].setText(f"{current_angles[motor]:.3f}°")

    def _update_offset_labels(self) -> None:
        """更新偏移量显示标签"""
        if not hasattr(self, "offset_labels"):
            return

        for motor in ["X", "Y", "Z", "A"]:
            offset = self.angle_offsets.get(motor, 0.0)
            if motor in self.offset_labels:
                self.offset_labels[motor].setText(f"偏移: {offset:.2f}°")
                # 偏移量为0时显示灰色，非零时显示蓝色
                color = COLOR_TEXT_SECONDARY if offset == 0.0 else COLOR_PRIMARY
                self.offset_labels[motor].setStyleSheet(f"color: {color}; font-size: 13px;")

    # ============= 微泵备注功能 =============

    def show_pump_note_menu(self, motor: str, pos, group=None) -> None:
        """显示微泵备注右键菜单"""
        menu = QMenu(self)

        edit_action = menu.addAction("编辑备注")
        edit_action.triggered.connect(lambda: self.edit_pump_note(motor))

        current_note = self.settings_manager.get_pump_note(motor)
        if current_note:
            clear_action = menu.addAction("清除备注")
            clear_action.triggered.connect(lambda: self.clear_pump_note(motor))

        # 使用传入的group或sender来映射坐标
        widget = group if group else self.sender()
        if widget:
            menu.exec(widget.mapToGlobal(pos))

    def edit_pump_note(self, motor: str) -> None:
        """编辑微泵备注"""
        current_note = self.settings_manager.get_pump_note(motor)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"微泵 {motor} 备注")
        dialog.setFixedSize(300, 140)

        layout = QVBoxLayout(dialog)

        # 输入框
        note_input = QLineEdit(current_note)
        note_input.setMaxLength(8)
        note_input.setPlaceholderText("输入备注(最多8字)")
        note_input.setFont(QFont("Microsoft YaHei", 14))
        layout.addWidget(note_input)

        # 提示
        hint = QLabel("限制8个字符")
        hint.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(lambda: note_input.clear())
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.Accepted:
            new_note = note_input.text().strip()
            self.settings_manager.set_pump_note(motor, new_note)
            self.refresh_pump_titles()
            self.log(f"微泵{motor}备注已更新: {new_note if new_note else '(已清除)'}")

    def clear_pump_note(self, motor: str) -> None:
        """清除微泵备注"""
        self.settings_manager.clear_pump_note(motor)
        self.refresh_pump_titles()
        self.log(f"微泵{motor}备注已清除")

    def refresh_pump_titles(self) -> None:
        """刷新所有微泵卡片标题"""
        for motor in ["X", "Y", "Z", "A"]:
            note = self.settings_manager.get_pump_note(motor)
            title = f"微泵 {motor} ({note})" if note else f"微泵 {motor}"

            # 更新转子监控页的卡片标题
            if hasattr(self, "position_motor_groups") and motor in self.position_motor_groups:
                self.position_motor_groups[motor].setTitle(title)

            # 更新手动控制页的卡片标题
            if hasattr(self, "manual_motor_groups") and motor in self.manual_motor_groups:
                self.manual_motor_groups[motor].setTitle(title)

    def get_pump_title(self, motor: str) -> str:
        """获取带备注的微泵标题"""
        note = self.settings_manager.get_pump_note(motor)
        return f"微泵 {motor} ({note})" if note else f"微泵 {motor}"
