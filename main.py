# main.py
import ctypes
import json
import os
import sys
import time
import traceback
import serial
import resource

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("motor.control.v1")

from serial.tools import list_ports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QFrame, QLabel, QPushButton, QTextEdit,
    QComboBox, QLineEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QStatusBar, QInputDialog, QMessageBox, QRadioButton,
    QButtonGroup, QCheckBox, QTabWidget, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QTextCursor, QIcon

# 样式表
MACOS_STYLE = """
QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
    font-size: 18px;
    color: #000000;
    background-color: #FFFFFF;
}

QGroupBox {
    border: 1px solid #D3D3D3;
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 15px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    color: #1d1d1f;
    font-weight: 500;
}

QPushButton {
    background-color: #007aff;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #0063cc;
}

QPushButton:pressed {
    background-color: #004999;
}

QComboBox, QLineEdit, QTextEdit {
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 6px;
    background: white;
    selection-background-color: #007aff;
}

QTreeWidget {
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    background: white;
    alternate-background-color: #f5f5f7;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d1d1d6;
    color: #6e6e73;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QRadioButton::indicator {
    width: 18px;
    height: 18px;
}

QTabWidget::pane {
    border: 0;
}
"""


class PresetManager:
    PRESETS_FILE = "presets.json"

    @classmethod
    def load_presets(cls):
        if not os.path.exists(cls.PRESETS_FILE):
            return {}
        try:
            with open(cls.PRESETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载预设文件错误: {str(e)}")
            return {}

    @classmethod
    def save_presets(cls, presets):
        try:
            with open(cls.PRESETS_FILE, 'w') as f:
                json.dump(presets, f, indent=2)
        except Exception as e:
            QMessageBox.critical(None, "保存错误", f"无法保存预设文件: {str(e)}")


class MotorStepConfig(QDialog):
    def __init__(self, parent, step_num, initial_params=None):
        super().__init__(parent)
        self.parent = parent
        self.step_params = initial_params or {}
        self.motors = ["X", "Y", "Z", "A"]
        self.setWindowTitle(f"步骤 {step_num} 参数配置")
        self.setFixedSize(500, 650)
        self.setWindowModality(Qt.ApplicationModal)
        self.init_ui()
        self.load_initial_params()

    def init_ui(self):
        layout = QGridLayout()
        self.widgets = {}

        # 添加步骤名称输入框
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

        #电机控制区
        for i, motor in enumerate(self.motors):
            group = QGroupBox(f"电机 {motor}")
            group.setFont(QFont("Microsoft YaHei", 13))
            vbox = QVBoxLayout(group)

            # 启用开关
            enable_check = QCheckBox("启用电机")
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

            # 参数输入
            speed_entry = QLineEdit()
            speed_entry.setPlaceholderText("速度值")
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
                "angle": angle_entry
            }

            layout.addWidget(group, (i // 2)+1, i % 2)

        # 间隔时间
        interval_frame = QFrame()
        hbox = QHBoxLayout(interval_frame)
        interval_lbl = QLabel("间隔时间（ms）:")
        interval_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry = QLineEdit()
        self.interval_entry.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry.setFixedHeight(40)
        hbox.addWidget(interval_lbl)
        hbox.addWidget(self.interval_entry)
        layout.addWidget(interval_frame, 3, 0, 1, 2)

        # 按钮区域
        btn_frame = QFrame()
        hbox_btn = QHBoxLayout(btn_frame)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = QPushButton("确认")
        confirm_btn.clicked.connect(self.save_params)
        hbox_btn.addWidget(cancel_btn)
        hbox_btn.addWidget(confirm_btn)
        layout.addWidget(btn_frame, 4, 0, 1, 2)

        self.setLayout(layout)

    def load_initial_params(self):
        if self.step_params:
            self.name_entry.setText(self.step_params.get("name", ""))
            for motor in self.motors:
                params = self.step_params.get(motor, {})
                widgets = self.widgets[motor]
                widgets["enable"].setChecked(params.get("enable", "D") == "E")
                if params.get("direction", "F") == "F":
                    widgets["direction"].buttons()[0].setChecked(True)
                else:
                    widgets["direction"].buttons()[1].setChecked(True)
                widgets["speed"].setText(params.get("speed", ""))
                widgets["angle"].setText(params.get("angle", ""))
            self.interval_entry.setText(str(self.step_params.get("interval", 0)))

    def save_params(self):
        try:
            params = {}
            params["name"] = self.name_entry.text()  # 保存步骤名称
            for motor in self.motors:
                widgets = self.widgets[motor]
                enable = "E" if widgets["enable"].isChecked() else "D"
                direction = "F" if widgets["direction"].checkedButton().text() == "正转" else "B"
                speed = widgets["speed"].text()
                angle = widgets["angle"].text().upper()

                if not speed.isdigit() or not (0 <= int(speed)):
                    raise ValueError(f"电机{motor}速度值无效")

                if not (angle.isdigit() and 0 <= int(angle)) and angle.upper() != "G":
                    raise ValueError(f"电机{motor}角度值无效")

                params[motor] = {
                    "enable": enable,
                    "direction": direction,
                    "speed": speed,
                    "angle": angle
                }

            interval = self.interval_entry.text()
            if not interval.isdigit() or int(interval) < 0:
                raise ValueError("间隔时间必须为0或正整数")
            params["interval"] = int(interval)
            self.step_params = params
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "输入错误", str(e))


class AutomationThread(QThread):
    update_status = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, parent, steps, loop_count, serial_port):
        super().__init__()
        self.parent = parent
        self.steps = steps
        self.loop_count = loop_count
        self.serial_port = serial_port
        self.running = True
        self.paused = False

    def run(self):
        current_loop = 1
        try:
            while self.running and (self.loop_count == 0 or current_loop <= self.loop_count):
                if not self.serial_port.is_open:
                    raise serial.SerialException("串口连接已断开")

                while self.paused:
                    time.sleep(0.1)

                self.update_status.emit(f"自动化运行中（第{current_loop}次循环）...")

                for step in self.steps:
                    if not self.running:
                        break

                    # 发送指令
                    command = self.parent.generate_command(step)
                    self.serial_port.write(command.encode())
                    self.parent.log(f"已发送指令: {command.strip()!r}")

                    time.sleep(step["interval"] / 1000)

                current_loop += 1

        except Exception as e:
            self.error_occurred.emit(f"自动化运行失败: {str(e)}")
            traceback.print_exc()
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class MotorControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.automation_steps = []
        self.current_step = 0
        self.running = False
        self.loop_count = 0
        self.presets = PresetManager.load_presets()
        self.automation_thread = None
        self.init_ui()
        self.update_preset_combos()
        self.setStyleSheet(MACOS_STYLE)
        self.setMinimumSize(1080, 800)
        self.resize(1080, 800)
        self.setWindowIcon(QIcon(':/meow.ico'))

    def init_ui(self):
        self.setWindowTitle("四轴步进电机控制程序")

        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.set_size_policy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # 左侧导航栏
        nav_frame = QFrame()
        nav_frame.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)

        # 控制模式
        control_group = QGroupBox("控制模式")
        control_group.setFont(QFont("Microsoft YaHei", 13))
        control_layout = QVBoxLayout(control_group)

        self.manual_btn = QPushButton("手动控制")
        self.manual_btn.setCheckable(True)
        self.manual_btn.setChecked(True)
        self.auto_btn = QPushButton("自动控制")
        self.auto_btn.setCheckable(True)

        for btn in [self.manual_btn, self.auto_btn]:
            btn.setFont(QFont("Microsoft YaHei", 13))
            btn.setFixedHeight(40)
            control_layout.addWidget(btn)

        nav_layout.addWidget(control_group)

        # 串口配置
        serial_group = QGroupBox("串口设置")
        serial_group.setFont(QFont("Microsoft YaHei", 13))
        serial_layout = QVBoxLayout(serial_group)

        self.port_combo = QComboBox()
        self.port_combo.addItems(self.get_available_ports())
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])

        for widget in [self.port_combo, self.baud_combo]:
            widget.setFont(QFont("Microsoft YaHei", 16))
            widget.setFixedHeight(40)
            serial_layout.addWidget(widget)

        self.connect_btn = QPushButton("打开串口")
        refresh_btn = QPushButton("刷新端口")

        for btn in [self.connect_btn, refresh_btn]:
            btn.setFont(QFont("Microsoft YaHei", 16))
            btn.setFixedHeight(40)
            serial_layout.addWidget(btn)

        nav_layout.addWidget(serial_group)
        nav_layout.addStretch()

        # 主内容区
        content_frame = QFrame()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 标签页
        self.tab_widget = QTabWidget()
        self.tab_widget.tabBar().hide()

        # 手动控制页
        self.manual_tab = QWidget()
        self.init_manual_tab()
        self.tab_widget.addTab(self.manual_tab, "")

        # 自动控制页
        self.auto_tab = QWidget()
        self.init_auto_tab()
        self.tab_widget.addTab(self.auto_tab, "")

        content_layout.addWidget(self.tab_widget)

        # 日志区域
        log_group = QGroupBox("系统日志")
        log_group.setFont(QFont("Microsoft YaHei", 16))
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Menlo", 11))
        log_layout.addWidget(self.log_text)

        clear_btn = QPushButton("清空日志")
        clear_btn.setFont(QFont("Microsoft YaHei", 16))
        clear_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_btn)

        content_layout.addWidget(log_group)

        main_layout.addWidget(nav_frame)
        main_layout.addWidget(content_frame)

        # 信号连接
        self.manual_btn.clicked.connect(lambda: self.switch_tab(0))
        self.auto_btn.clicked.connect(lambda: self.switch_tab(1))
        self.connect_btn.clicked.connect(self.toggle_serial)
        refresh_btn.clicked.connect(self.refresh_serial_ports)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def set_size_policy(self, h_policy, v_policy):
        """通用尺寸策略设置方法"""
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QGroupBox, QFrame)):
                widget.setSizePolicy(
                    QSizePolicy(h_policy, v_policy,
                                QSizePolicy.ControlType.DefaultType)
                )

    def resizeEvent(self, event):
        """窗口缩放时自适应字体"""
        base_size = 34
        scale = min(self.width() / 1920, self.height() / 1080)  # 基于基准缩放
        new_size = int(base_size * scale)
        self.setStyleSheet(f"""
            QWidget {{ font-size: {new_size}px; }}
            QGroupBox {{ font-size: {new_size + 2}px; }}
            QPushButton, QComboBox {{ padding: {max(4, int(4 * scale))}px; }}
        """)
        total_width = self.steps_table.width()
        column_count = self.steps_table.columnCount()
        ratio = [0.1, 0.1, 0.7, 0.1]  # 每列比例，调整以适配需求

        for i in range(column_count):
            self.steps_table.setColumnWidth(i, int(total_width * ratio[i]))

        super().resizeEvent(event)

    def switch_tab(self, index):
        self.tab_widget.setCurrentIndex(index)
        self.manual_btn.setChecked(index == 0)
        self.auto_btn.setChecked(index == 1)

    def switch_to_manual(self):
        self.tab_widget.setCurrentIndex(0)
        self.manual_btn.setChecked(True)
        self.auto_btn.setChecked(False)

    def switch_to_auto(self):
        self.tab_widget.setCurrentIndex(1)
        self.auto_btn.setChecked(True)
        self.manual_btn.setChecked(False)

    def init_manual_tab(self):
        layout = QVBoxLayout(self.manual_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # 电机控制区
        motor_frame = QFrame()
        grid_layout = QGridLayout(motor_frame)
        self.motor_widgets = {}

        motors = [("X", 0, 0), ("Y", 0, 1), ("Z", 1, 0), ("A", 1, 1)]
        for motor, row, col in motors:
            group = QGroupBox(f"电机 {motor}")
            group.setFont(QFont("Microsoft YaHei", 16))
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
            speed_entry.setPlaceholderText("速度值")
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
                "continuous": continuous_check
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

        preset_layout.addWidget(preset_lbl)
        preset_layout.addWidget(self.manual_preset_combo)
        preset_layout.addWidget(load_btn)
        preset_layout.addWidget(save_btn)
        hbox.addWidget(preset_frame)

        layout.addWidget(control_frame)

    def init_auto_tab(self):
        layout = QVBoxLayout(self.auto_tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # 预设管理
        preset_frame = QFrame()
        hbox = QHBoxLayout(preset_frame)

        # 新增自动预设combo定义
        self.auto_preset_combo = QComboBox()
        self.auto_preset_combo.setFont(QFont("Microsoft YaHei", 16))
        self.auto_preset_combo.setFixedWidth(200)

        preset_lbl = QLabel("自动预设:")
        load_btn = QPushButton("加载")
        load_btn.clicked.connect(self.load_auto_preset)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_auto_preset)

        # 将控件添加到布局
        hbox.addWidget(QLabel("自动预设:"))
        hbox.addWidget(self.auto_preset_combo)
        hbox.addWidget(load_btn)
        hbox.addWidget(save_btn)
        layout.addWidget(preset_frame)

        # 步骤表格
        self.steps_table = QTreeWidget()
        self.steps_table.setHeaderLabels(["编号", "名称", "参数配置", "间隔(ms)"])
        for i in range(self.steps_table.columnCount()):
            header_item = self.steps_table.headerItem()
            header_item.setTextAlignment(i, Qt.AlignmentFlag.AlignCenter)
        self.steps_table.setColumnWidth(0, 80)
        self.steps_table.setColumnWidth(1, 150)
        self.steps_table.setColumnWidth(2, 500)
        self.steps_table.setColumnWidth(3, 120)
        self.steps_table.itemDoubleClicked.connect(self.edit_step)
        layout.addWidget(self.steps_table)

        # 控制按钮
        btn_frame = QFrame()
        hbox = QHBoxLayout(btn_frame)
        buttons = [
            ("添加步骤", self.add_step),
            ("删除步骤", self.remove_step),
            ("开始执行", self.start_automation),
            ("停止执行", self.stop_automation)
        ]
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.setFont(QFont("Microsoft YaHei", 16))
            btn.setFixedHeight(40)
            btn.clicked.connect(slot)
            hbox.addWidget(btn)
        layout.addWidget(btn_frame)

        # 循环次数设置
        loop_frame = QFrame()
        hbox = QHBoxLayout(loop_frame)
        loop_label = QLabel("循环次数 (0=无限):")
        self.loop_entry = QLineEdit("1")
        self.loop_entry.setFixedWidth(100)
        hbox.addWidget(loop_label)
        hbox.addWidget(self.loop_entry)
        hbox.addStretch()
        layout.addWidget(loop_frame)

    def edit_step(self, item, column):
        step_index = self.steps_table.indexOfTopLevelItem(item)
        if step_index >= 0 and step_index < len(self.automation_steps):
            step = self.automation_steps[step_index]
            config_window = MotorStepConfig(self, step_index + 1, step)
            if config_window.exec() == QDialog.DialogCode.Accepted:
                # 更新步骤参数
                self.automation_steps[step_index] = config_window.step_params
                self.update_steps_table()
                self.log(f"步骤 {step_index + 1} 已编辑")

    def generate_command(self, step):
        command = ""
        for motor in ["X", "Y", "Z", "A"]:
            config = step.get(motor, {})
            angle = config.get("angle", "0")
            is_continuous = config.get("continuous", False)

            if is_continuous and angle.isdigit() and int(angle) >= 0:
                cmd = (
                    f"{motor}"
                    f"{config.get('enable', 'D')}"
                    f"{config.get('direction', 'F')}"
                    f"V0"
                    f"G"
                )
            else:
                cmd = (
                    f"{motor}"
                    f"{config.get('enable', 'D')}"
                    f"{config.get('direction', 'F')}"
                    f"V{config.get('speed', '0')}"
                    f"J{config.get('angle', '0')}"
                )
            command += cmd
        return command + "\r\n"

    def get_available_ports(self):
        # 固定添加COM1和COM2
        ports = {port.device for port in list_ports.comports()}
        fixed_ports = {"COM1", "COM2"}
        return sorted(fixed_ports.union(ports), key=lambda x: int(x[3:]) if x.startswith("COM") else 999)

    def refresh_serial_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()
        available_ports = self.get_available_ports()
        self.port_combo.addItems(available_ports)
        # 检查当前端口是否在新的可用端口中
        if current in available_ports:
            self.port_combo.setCurrentText(current)
        else:
            # 如果不在，则选择第一个端口或保持为空
            if available_ports:
                self.port_combo.setCurrentText(available_ports[0])
            else:
                self.port_combo.setCurrentText("")  # 或者保持空白

    def toggle_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self):
        try:
            port = self.port_combo.currentText()
            baudrate = int(self.baud_combo.currentText())
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            self.connect_btn.setText("关闭串口")
            self.log(f"串口已连接 {port}@{baudrate}")
            self.status_bar.showMessage(f"已连接 {port}@{baudrate}")
        except Exception as e:
            QMessageBox.critical(self, "串口错误", str(e))

    def close_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.connect_btn.setText("打开串口")
        self.log("串口已关闭")
        self.status_bar.showMessage("串口已关闭")

    def send_manual_command(self):
        params = {}
        for motor, widgets in self.motor_widgets.items():
            params[motor] = {
                "enable": "E" if widgets["enable"].isChecked() else "D",
                "direction": "F" if widgets["direction"].checkedButton().text() == "正转" else "B",
                "speed": widgets["speed"].text(),
                "angle": widgets["angle"].text().upper(),
                "continuous": widgets["continuous"].isChecked()
            }
            # 验证输入
            if not params[motor]["speed"].isdigit():
                QMessageBox.critical(self, "输入错误", f"电机{motor}速度值无效")
                return
            if not (params[motor]["angle"].isdigit() or params[motor]["angle"] == "G"):
                QMessageBox.critical(self, "输入错误", f"电机{motor}角度值无效")
                return

        command = self.generate_command(params)
        if self.send_command(command):
            self.status_bar.showMessage("手动指令已发送")

    def send_command(self, command):
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.critical(self, "错误", "请先打开串口连接！")
            return False
        try:
            self.serial_port.write(command.encode())
            self.log(f"已发送指令: {command.strip()}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "发送错误", str(e))
            return False

    def add_step(self):
        try:
            step_num = len(self.automation_steps) + 1
            config_window = MotorStepConfig(self, step_num)
            if config_window.exec() == QDialog.DialogCode.Accepted:
                if config_window.step_params:
                    self.automation_steps.append(config_window.step_params)
                    self.update_steps_table()
                    self.log(f"已成功添加步骤 {step_num}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加步骤失败: {str(e)}")

    def remove_step(self):
        selected = self.steps_table.selectedItems()
        if selected:
            index = self.steps_table.indexOfTopLevelItem(selected[0])
            if 0 <= index < len(self.automation_steps):
                del self.automation_steps[index]
                self.update_steps_table()
                self.log(f"已删除步骤 {index + 1}")

    def start_automation(self):
        # 串口状态检查
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.critical(self, "串口错误", "请先打开串口连接！")
            return

        if not self.automation_steps:
            QMessageBox.warning(self, "警告", "请先添加执行步骤！")
            return
        try:
            self.loop_count = int(self.loop_entry.text())
            if self.loop_count < 0:
                raise ValueError
        except:
            QMessageBox.critical(self, "输入错误", "请输入有效的循环次数（≥0的整数）")
            return

        self.running = True
        self.automation_thread = AutomationThread(
            self,
            self.automation_steps,
            self.loop_count,
            self.serial_port
        )
        self.automation_thread.update_status.connect(self.status_bar.showMessage)
        self.automation_thread.finished.connect(self.on_automation_finished)
        self.automation_thread.error_occurred.connect(self.handle_automation_error)  # 连接错误信号
        self.automation_thread.start()
        self.log("自动化运行已启动")

    def handle_automation_error(self, message):
        self.stop_automation()
        QMessageBox.critical(self, "运行错误", message)
        self.log(f"错误: {message}")

    def closeEvent(self, event):
        self.stop_automation()  # 确保关闭时停止线程
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        event.accept()

    def stop_automation(self):
        if self.automation_thread:
            self.automation_thread.stop()
        self.running = False
        self.log("自动化运行已停止")

    def on_automation_finished(self):
        self.status_bar.showMessage("自动化运行完成")
        self.log("自动化运行已结束")

    def update_steps_table(self):
        try:
            self.steps_table.clear()  # 清空现有内容
            # 遍历所有步骤生成显示项
            for idx, step in enumerate(self.automation_steps, 1):
                params_desc = []
                # 遍历每个电机配置
                for motor in ["X", "Y", "Z", "A"]:
                    cfg = step.get(motor, {})
                    if cfg.get("enable") == "E":
                        desc = f"{motor}:方向{cfg.get('direction', '?')} 速度{cfg.get('speed', '?')} 角度{cfg.get('angle', '?')}"
                        params_desc.append(desc)
                # 生成显示文本
                params_str = " | ".join(params_desc) if params_desc else "所有电机脱机"
                interval = step.get("interval", 0)
                name = step.get("name", f"步骤 {idx}")  # 获取步骤名称，如果不存在则使用默认名称
                # 创建表格项
                item = QTreeWidgetItem([
                    str(idx),
                    name,
                    params_str,
                    str(interval)
                ])
                # 设置每个列的内容居中显示
                for i in range(self.steps_table.columnCount()):
                    item.setTextAlignment(i, Qt.AlignmentFlag.AlignCenter)
                self.steps_table.addTopLevelItem(item)
            self.log(f"已更新步骤列表，当前步骤数：{len(self.automation_steps)}")
        except Exception as e:
            self.log(f"更新步骤列表失败: {str(e)}")


    def save_manual_preset(self):
        try:
            # 获取预设名称
            preset_name, ok = QInputDialog.getText(
                self,
                "保存手动预设",
                "输入预设名称:",
                QLineEdit.EchoMode.Normal
            )
            if not ok or not preset_name.strip():
                QMessageBox.warning(self, "警告", "预设名称不能为空")
                return

            # 收集参数
            manual_params = {}
            for motor, widgets in self.motor_widgets.items():
                manual_params[motor] = {
                    "enable": "E" if widgets["enable"].isChecked() else "D",
                    "direction": "F" if widgets["direction"].checkedButton().text() == "正转" else "B",
                    "speed": widgets["speed"].text(),
                    "angle": widgets["angle"].text(),
                    "continuous": widgets["continuous"].isChecked()
                }

            self.presets[f"manual_{preset_name}"] = manual_params
            PresetManager.save_presets(self.presets)

            self.update_preset_combos()

            QMessageBox.information(self, "成功", "预设保存成功")
            self.log(f"手动预设 '{preset_name}' 已保存")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")

    def load_manual_preset(self):
        name = self.manual_preset_combo.currentText()
        if not name:
            return
        preset_data = self.presets.get(f"manual_{name}")
        if preset_data:
            for motor, params in preset_data.items():
                if motor in self.motor_widgets:
                    widgets = self.motor_widgets[motor]
                    widgets["enable"].setChecked(params["enable"] == "E")
                    if params["direction"] == "F":
                        widgets["direction"].buttons()[0].setChecked(True)
                    else:
                        widgets["direction"].buttons()[1].setChecked(True)
                    widgets["speed"].setText(params["speed"])
                    widgets["angle"].setText(params["angle"])
                    widgets["continuous"].setChecked(params["continuous"])
            self.log(f"已加载手动预设 '{name}'")

    def save_auto_preset(self):
        try:
            # 获取预设名称
            preset_name, ok = QInputDialog.getText(
                self,
                "保存预设",
                "输入预设名称:",
                QLineEdit.EchoMode.Normal,
                ""
            )
            if not ok or not preset_name:
                return

            # 收集需要保存的数据
            preset_data = {
                "steps": [s.copy() for s in self.automation_steps],  # 深拷贝步骤数据
                "loop_count": self.loop_entry.text()
            }

            # 更新预设数据
            self.presets[f"auto_{preset_name}"] = preset_data
            PresetManager.save_presets(self.presets)

            # 刷新下拉框
            self.update_preset_combos()

            # 日志反馈
            self.log(f"自动预设 '{preset_name}' 已保存")
            QMessageBox.information(self, "成功", "预设保存成功")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")
            self.log(f"保存预设时出错: {str(e)}")

    def load_auto_preset(self):
        try:
            preset_name = self.auto_preset_combo.currentText()
            if not preset_name:
                QMessageBox.warning(self, "警告", "请先选择要加载的预设")
                return

            # 从预设数据获取配置
            full_name = f"auto_{preset_name}"
            preset_data = self.presets.get(full_name)

            if not preset_data:
                QMessageBox.critical(self, "错误", "找不到指定的预设")
                return

            # 更新自动化步骤
            self.automation_steps = [step.copy() for step in preset_data.get("steps", [])]

            # 更新循环次数
            self.loop_entry.setText(str(preset_data.get("loop_count", 1)))

            # 刷新界面
            self.update_steps_table()

            # 日志反馈
            self.log(f"已加载自动预设 '{preset_name}'")
            QMessageBox.information(self, "成功", "预设加载成功")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败: {str(e)}")
            self.log(f"加载预设时出错: {str(e)}")

    def update_preset_combos(self):
        """更新所有预设下拉框"""
        try:
            # 关键修复点3：正确过滤手动预设
            manual_presets = [
                k[7:]  # 去除"manual_"前缀
                for k in self.presets.keys()
                if k.startswith("manual_")
            ]

            # 关键修复点4：清空后重新添加项
            self.manual_preset_combo.clear()
            self.manual_preset_combo.addItems(sorted(manual_presets))

            # 自动预设更新（保持不变）
            auto_presets = [k[5:] for k in self.presets if k.startswith("auto_")]
            self.auto_preset_combo.clear()
            self.auto_preset_combo.addItems(sorted(auto_presets))

        except Exception as e:
            self.log(f"更新预设列表失败: {str(e)}")

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.log_text.clear()

    def closeEvent(self, event):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        event.accept()


if __name__ == "__main__":
    if os.name == 'nt':
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 设置为系统DPI感知

    # 设置高DPI缩放策略
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(':/meow.ico'))
    app.setStyleSheet(MACOS_STYLE)
    window = MotorControlApp()
    window.show()
    sys.exit(app.exec())