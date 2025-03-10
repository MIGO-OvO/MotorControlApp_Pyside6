# main.py
import ctypes
import json
import os
import sys
import threading
import time
import traceback
import weakref
import resource
import serial
import platform
import math
from collections import deque
if platform.system() == 'Windows':
    from ctypes import windll
    windll.winmm.timeBeginPeriod(1)
from datetime import datetime
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("motor.control.v1")
from serial.tools import list_ports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QFrame, QLabel, QPushButton, QTextEdit,
    QComboBox, QLineEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QStatusBar, QInputDialog, QMessageBox, QRadioButton,
    QButtonGroup, QCheckBox, QTabWidget, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QModelIndex, QTimer, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QTextCursor, QIcon, QColor, QPainter, QPen, QBrush
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

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

MotorStatusButton {
    background-color: #007aff;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 80px;
}
MotorStatusButton:checked {
    background-color: #004999;
}
MotorCircle {
    border: 2px solid #007aff;
    border-radius: 50%;
}
ChartWidget {
    background-color: white;
    border-radius: 8px;
    padding: 15px;
}
"""


class MotorCircle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.target_angle = 0
        self.setFixedSize(150, 150)

        # 先初始化动画相关属性
        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setDuration(1000)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

    def set_angle(self, angle):
        self.target_angle = angle
        if hasattr(self, 'animation'):
            self.animation.stop()
            self.animation.setStartValue(self._angle)
            self.animation.setEndValue(angle)
            self.animation.start()
        self._angle = angle
        self.update()  # 触发重绘

    def get_angle(self):
        return self._angle

    angle = property(get_angle, set_angle)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制背景圆
        painter.setPen(QPen(QColor(200, 200, 200), 3))
        painter.drawEllipse(10, 10, 130, 130)

        # 绘制转轴
        painter.setPen(QPen(QColor(0, 122, 255), 5))
        painter.setBrush(QBrush(QColor(0, 122, 255, 50)))
        radius = 50
        center = QPointF(75, 75)
        end_x = center.x() + radius * math.cos(math.radians(self.angle - 90))
        end_y = center.y() + radius * math.sin(math.radians(self.angle - 90))
        painter.drawLine(center, QPointF(end_x, end_y))
        painter.drawEllipse(center, 15, 15)

    angle = property(get_angle, set_angle)


class AnalysisChart(QChart):
    def __init__(self):
        super().__init__()
        self.series = {}
        self.axisX = QValueAxis()
        self.axisY = QValueAxis()
        self.init_chart()

    def init_chart(self):
        colors = [QColor(255, 0, 0), QColor(0, 255, 0), QColor(0, 0, 255), QColor(255, 165, 0)]
        for i, motor in enumerate(["X", "Y", "Z", "A"]):
            series = QLineSeries()
            series.setName(f"电机{motor}偏差")
            series.setColor(colors[i])
            self.addSeries(series)
            self.series[motor] = series
        self.addAxis(self.axisX, Qt.AlignBottom)
        self.addAxis(self.axisY, Qt.AlignLeft)
        self.axisX.setRange(0, 60)
        self.axisX.setTitleText("时间 (秒)")
        self.axisY.setTitleText("角度偏差")
        self.legend().setVisible(True)
        for series in self.series.values():
            series.attachAxis(self.axisX)
            series.attachAxis(self.axisY)
        self.data = {motor: deque(maxlen=60) for motor in ["X", "Y", "Z", "A"]}
        self.time_counter = 0

    def update_data(self, deviations):
        self.time_counter += 1
        for motor, dev in deviations.items():
            self.data[motor].append((self.time_counter, dev))
            self.series[motor].replace([QPointF(x[0], x[1]) for x in self.data[motor]])

class PresetManager:
    PRESETS_FILE = "presets.json"

    def __init__(self, win):
        self.win = win

    def __del__(self):
        self.win = None

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


class DragDropTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)  # 设置为内部移动模式
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setIndentation(0)  # 删除缩进防止误操作
        self.setRootIsDecorated(False)  # 隐藏根项装饰
        self.setExpandsOnDoubleClick(False)  # 禁止双击展开
        self.setDragDropOverwriteMode(True) # 禁止创建子项
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        """重写drop事件精确控制项目移动"""
        dragged_item = self.currentItem()
        if not dragged_item:
            return

        # 获取目标位置
        drop_pos = event.position().toPoint()
        target_item = self.itemAt(drop_pos)

        # 计算插入位置
        new_index = self.indexAt(drop_pos).row()
        new_index = max(0, new_index) if new_index != -1 else self.topLevelItemCount()

        # 执行移动逻辑
        if dragged_item.parent() is None:  # 确保是顶级项
            # 移除原始项目
            source_index = self.indexOfTopLevelItem(dragged_item)
            item = self.takeTopLevelItem(source_index)

            # 插入到新位置
            if new_index >= self.topLevelItemCount():
                self.addTopLevelItem(item)
            else:
                self.insertTopLevelItem(new_index, item)

            # 设置选中状态
            self.setCurrentItem(item)

        # 添加同步调用
        parent_app = self.window()
        if isinstance(parent_app, MotorControlApp):
            parent_app.sync_automation_steps_order()

        event.accept()

class MotorStepConfig(QDialog):
    def __init__(self, parent, step_num, initial_params=None):
        super().__init__(parent)
        self.parent = weakref.ref(parent)
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


class SerialReader(QThread):
    data_received = Signal(str)
    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True

    def run(self):
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # 先检查缓存中是否有数据
                    if self.serial_port.in_waiting > 0:
                        # 读取所有可用数据
                        raw_data = self.serial_port.read(self.serial_port.in_waiting)
                        print(f"[DEBUG] Raw bytes received: {raw_data}")  # 打印原始字节

                        # 尝试UTF-8解码（兼容ASCII）
                        try:
                            data = raw_data.decode('utf-8')
                        except UnicodeDecodeError:
                            # 使用替代策略解码
                            data = raw_data.decode('utf-8', errors='replace')
                            print(f"[WARN] 解码错误，使用替换字符")

                        # 拆分可能的多条消息
                        for line in data.split('\n'):
                            line = line.strip()
                            if line:
                                print(f"[DEBUG] Processing line: {line}")
                                self.data_received.emit(line)

                except Exception as e:
                    print(f"Serial read error: {str(e)}")
                    break
            time.sleep(0.01)  # 防止CPU占用过高
    def stop(self):
        self.running = False

class AutomationThread(QThread):
    update_status = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()
    progress_updated = Signal(int)


    def __init__(self, parent, steps, loop_count, serial_port):
        super().__init__()
        self.parent_ref = weakref.ref(parent)
        self.steps = self._deep_copy_steps(steps)
        self.loop_count = loop_count
        self.serial_port = serial_port  # 使用主线程的串口实例
        self._running = threading.Event()
        self._running.set()
        self._paused = threading.Event()
        self._current_step = 0
        self._current_loop = 1
        self.lock = parent.serial_lock

    def _deep_copy_steps(self, steps):
        """安全的深拷贝方法"""
        try:
            return json.loads(json.dumps(steps))
        except Exception as e:
            self.error_occurred.emit(f"步骤数据解析失败: {str(e)}")
            return []

    def run(self):
        try:
            while self._running.is_set() and self._should_continue():
                try:
                    self._execute_loop()
                except serial.SerialException as e:
                    self.error_occurred.emit(f"串口通信失败: {str(e)}")
                    break
                except Exception as e:
                    self.error_occurred.emit(f"未知错误: {str(e)}")
                    break
        except Exception as e:
            self.error_occurred.emit(f"线程初始化失败: {str(e)}")
        finally:
            self.finished.emit()



    def _should_continue(self):
        """线程继续条件判断"""
        if self.loop_count == 0:
            return True
        return self._current_loop <= self.loop_count

    def _execute_loop(self):
        """执行单个循环"""
        self.update_status.emit(f"自动运行中 (循环 {self._current_loop}/{self.loop_count or '∞'})...")
        self.progress_updated.emit(0)  # 重置进度

        for step_idx, step in enumerate(self.steps):
            if not self._running.is_set():
                break

            # 暂停处理
            while self._paused.is_set():
                time.sleep(0.1)

            self._current_step = step_idx
            self.progress_updated.emit(int((step_idx+1)/len(self.steps)*100))

            if not self._send_step_command(step):
                break

            self._wait_interval(step.get("interval", 0))

        self._current_loop += 1

    def _send_step_command(self, step):
        """发送步骤命令"""
        try:
            parent = self.parent_ref()
            if not parent or not self.serial_port:
                return False

            command = parent.generate_command(step)
            with self.lock:  # 使用主线程的串口锁
                if not self.serial_port.is_open:
                    self.error_occurred.emit("串口连接已断开")
                    return False

                try:
                    self.serial_port.write(command.encode('utf-8'))
                    self.serial_port.flush()
                    parent.log(f"指令已发送: {command.strip()}")
                    return True
                except (serial.SerialException, OSError) as e:
                    self.error_occurred.emit(f"指令发送失败: {str(e)}")
                    return False

        except Exception as e:
            self.error_occurred.emit(f"发送指令异常: {str(e)}")
            return False

    def _wait_interval(self, interval_ms):
        """超高精度间隔等待（误差<3ms）"""
        interval = interval_ms / 1000  # 转换为秒
        if interval <= 0:
            return

        # 使用最高精度时钟
        get_time = time.perf_counter
        deadline = get_time() + interval
        error_correction = 0.0  # 误差修正量

        while get_time() < deadline and self._running.is_set():
            # 计算剩余时间（考虑误差修正）
            remaining = deadline - get_time() - error_correction

            if remaining <= 0.002:  # 2ms时进入最终阶段
                break

            # 动态睡眠策略
            if remaining > 0.01:  # 10ms以上使用分级睡眠
                sleep_time = remaining * 0.75  # 保留25%余量
                sleep_time = max(sleep_time, 0.005)  # 最小睡眠5ms
                t1 = get_time()
                time.sleep(sleep_time)
                t2 = get_time()
                error_correction += (t2 - t1) - sleep_time  # 累计误差
            else:  # 10ms以下使用自适应忙等待
                while (get_time() + error_correction) < deadline:
                    if (deadline - get_time()) > 0.002:  # 2ms时切换微睡眠
                        time.sleep(0.001)
                    pass

        # 最终修正阶段
        while (get_time() + error_correction) < deadline:
            pass

        # 检查暂停状态（优化后的检查频率）
        check_pause_interval = 0.005  # 5ms检查一次
        while self._paused.is_set():
            t1 = get_time()
            time.sleep(check_pause_interval)
            deadline += get_time() - t1  # 延长截止时间

    def _cleanup_resources(self):
        """资源清理"""
        with self.lock:
            if self.safe_serial and self.safe_serial.is_open:
                try:
                    self.safe_serial.close()
                except Exception:
                    pass
            self.safe_serial = None

    def stop(self):
        """安全停止"""
        self._running.clear()
        self._paused.clear()
        if self.isRunning():
            self.wait(2500)  # 增加等待时间

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()




class MotorControlApp(QMainWindow):
    log_signal = Signal(str)
    angle_update = Signal(dict)
    def __init__(self):
        super().__init__()
        self.angle_update.connect(lambda x: print(f"Signal received: {x}"))
        self.log_signal.connect(lambda x: print(f"Log: {x}"))
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize)
        self.serial_port = None
        self.automation_steps = []
        self.current_step = 0
        self.running = False
        self.serial_lock = threading.Lock()
        self.loop_count = 0
        self.presets = PresetManager.load_presets()
        self.automation_thread = None
        self.log_signal.connect(self._log_impl)
        self.init_ui()
        self.update_preset_combos()
        self.setStyleSheet(MACOS_STYLE)
        self.setMinimumSize(1080, 800)
        self.resize(1080, 800)
        self.setWindowIcon(QIcon(':/meow.ico'))
        self.angle_data = {"PRE": {}, "POST": {}}
        self.angle_update.connect(self.update_angles)


    def init_ui(self):
        self.setWindowTitle("四轴步进电机控制程序")

        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # 左侧导航栏
        self.nav_frame = QFrame()
        self.nav_frame.setFixedWidth(200)
        self.nav_layout = QVBoxLayout(self.nav_frame)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(8)

        # ================= 控制模式 =================
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

        self.nav_layout.addWidget(control_group)

        # ================= 电机状态 =================
        self.motor_status_group = QGroupBox("电机状态")
        self.motor_status_group.setFont(QFont("Microsoft YaHei", 13))
        motor_status_layout = QVBoxLayout(self.motor_status_group)

        self.position_btn = QPushButton("位置数据")
        self.position_btn.setCheckable(True)
        self.analysis_btn = QPushButton("数据分析")
        self.analysis_btn.setCheckable(True)

        for btn in [self.position_btn, self.analysis_btn]:
            btn.setFont(QFont("Microsoft YaHei", 13))
            btn.setFixedHeight(40)
            motor_status_layout.addWidget(btn)

        self.nav_layout.addWidget(self.motor_status_group)

        # ================= 串口设置 =================
        serial_group = QGroupBox("串口设置")
        serial_group.setFont(QFont("Microsoft YaHei", 13))
        serial_layout = QVBoxLayout(serial_group)

        # 端口选择
        self.port_combo = QComboBox()
        self.port_combo.addItems(self.get_available_ports())
        if "COM7" in self.get_available_ports():
            self.port_combo.setCurrentText("COM7")

        # 波特率选择
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.setCurrentText("115200")

        # 统一样式
        for widget in [self.port_combo, self.baud_combo]:
            widget.setFont(QFont("Microsoft YaHei", 16))
            widget.setFixedHeight(40)
            serial_layout.addWidget(widget)

        # 操作按钮
        self.connect_btn = QPushButton("打开串口")
        refresh_btn = QPushButton("刷新端口")

        for btn in [self.connect_btn, refresh_btn]:
            btn.setFont(QFont("Microsoft YaHei", 16))
            btn.setFixedHeight(40)
            serial_layout.addWidget(btn)

        self.nav_layout.addWidget(serial_group)
        self.nav_layout.addStretch()

        # 主内容区
        content_frame = QFrame()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # ================= 标签页 =================
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

        # 新增的状态页
        self.position_tab = QWidget()
        self.init_position_tab()
        self.tab_widget.addTab(self.position_tab, "")

        self.analysis_tab = QWidget()
        self.init_analysis_tab()
        self.tab_widget.addTab(self.analysis_tab, "")

        content_layout.addWidget(self.tab_widget)

        # ================= 日志区域 =================
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

        # 组合布局
        main_layout.addWidget(self.nav_frame)
        main_layout.addWidget(content_frame)

        # ================= 信号连接 =================
        self.manual_btn.clicked.connect(lambda: self.switch_tab(0))
        self.auto_btn.clicked.connect(lambda: self.switch_tab(1))
        self.position_btn.clicked.connect(lambda: self.switch_tab(2))
        self.analysis_btn.clicked.connect(lambda: self.switch_tab(3))

        self.connect_btn.clicked.connect(self.toggle_serial)
        refresh_btn.clicked.connect(self.refresh_serial_ports)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def init_position_tab(self):
        layout = QGridLayout(self.position_tab)
        self.motors = {}
        for i, motor in enumerate(["X", "Y", "Z", "A"]):
            group = QGroupBox(f"电机 {motor}")
            circle = MotorCircle()
            self.motors[motor] = circle
            layout.addWidget(group, i // 2, i % 2)
            group_layout = QVBoxLayout(group)
            group_layout.addWidget(circle)

    def init_analysis_tab(self):
        layout = QVBoxLayout(self.analysis_tab)
        self.chart_view = QChartView(AnalysisChart())
        layout.addWidget(self.chart_view)

    def switch_tab(self, index):
        self.tab_widget.setCurrentIndex(index)
        self.position_btn.setChecked(index == 2)
        self.analysis_btn.setChecked(index == 3)

    def update_angles(self, data):
        # 更新电机位置动画
        for motor, angle in data.items():
            if motor in self.motors:
                widget = self.motors[motor]
                current = widget.angle

                # 直接使用原始角度值（不进行模运算）
                diff = angle - current

                # 添加更新阈值（避免频繁微调）
                if abs(diff) >= 0.01:  # 当角度变化超过0.01度时更新
                    widget.set_angle(angle)

        # 更新偏差图表
        deviations = self.calculate_deviations()
        self.chart_view.chart().update_data(deviations)

    def calculate_deviations(self):
        # 计算角度偏差
        deviations = {}
        for motor in ["X", "Y", "Z", "A"]:
            pre = self.angle_data["PRE"].get(motor, 0)
            post = self.angle_data["POST"].get(motor, 0)
            dev = abs((post - pre + 180) % 360 - 180)
            deviations[motor] = dev
        return deviations

    def handle_serial_data(self, data):
        clean_data = data.strip()
        if not clean_data:
            return

        self.log(f"接收: {clean_data}")

        # 新增角度数据解析
        if data.startswith("ANGLE"):
            import re
            # 修改正则表达式以兼容不同小数位数
            pattern = r"([A-Z])(\d+\.?\d*)"  # 匹配电机代号和数字（允许整数或小数）
            matches = re.findall(pattern, data)
            print(f"[DEBUG] Matches: {matches}")  # 调试输出匹配结果

            if matches:
                angle_dict = {}
                for motor, value in matches:
                    try:
                        angle = float(value)
                        if motor not in ["X", "Y", "Z", "A"]:
                            self.log(f"无效电机代号: {motor}")
                            continue
                        angle_dict[motor] = angle
                        print(f"[DEBUG] Parsed: {motor}={angle}")  # 调试输出解析结果
                    except ValueError:
                        self.log(f"无效角度值: {motor}{value}")
                        continue

                if angle_dict:
                    self.angle_update.emit(angle_dict)
                    self.angle_data["POST"].update(angle_dict)
                    print(f"[DEBUG] Emitted angles: {angle_dict}")  # 调试信号发射
            else:
                self.log(f"格式错误: {clean_data}")

    def set_size_policy(self, h_policy, v_policy):
        """通用尺寸策略设置方法"""
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QGroupBox, QFrame)):
                widget.setSizePolicy(
                    QSizePolicy(h_policy, v_policy,
                                QSizePolicy.ControlType.DefaultType)
                )

    def resizeEvent(self, event):
        self.resize_timer.start(200)
        super().resizeEvent(event)
    def handle_resize(self):
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
        self.steps_table = DragDropTreeWidget()
        self.steps_table.setHeaderLabels(["编号", "名称", "参数配置", "间隔(ms)"])
        self.steps_table.setRootIsDecorated(False)  # 隐藏根节点展开图标
        self.steps_table.setUniformRowHeights(True)  # 统一行高
        self.steps_table.setSortingEnabled(False)  # 禁用排序
        self.steps_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)# 设置不可编辑
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

    def sync_automation_steps_order(self):
        """精确同步步骤顺序"""
        try:
            # 清空旧数据时保留有效项
            valid_items = [
                (self.steps_table.topLevelItem(i), i)
                for i in range(self.steps_table.topLevelItemCount())
                if self.steps_table.topLevelItem(i) is not None
            ]

            # 按显示顺序重建数据
            new_steps = []
            for idx, (item, _) in enumerate(valid_items, 1):
                if not item:
                    continue
                step_data = item.data(0, Qt.UserRole)
                if step_data:  # 有效性检查
                    new_steps.append(step_data)
                    item.setText(0, str(idx))  # 强制刷新编号

            # 重建数据内存
            self.automation_steps.clear()
            self.automation_steps.extend(new_steps)

            # 清除无效空白项并重新加载表格
            self.steps_table.clear()
            for step in self.automation_steps:
                self._add_step_to_table(step)

            self.log("步骤顺序已调整")
        except Exception as e:
            self.log(f"同步步骤顺序失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"同步步骤顺序失败: {str(e)}")

    def _add_step_to_table(self, step):
        """安全的表格项添加方法"""
        try:
            current_count = self.steps_table.topLevelItemCount()
            idx = current_count + 1

            # 参数解析逻辑
            params_desc = []
            for motor in ["X", "Y", "Z", "A"]:
                cfg = step.get(motor, {})
                if cfg.get("enable") == "E":
                    desc = f"{motor}:方向{cfg.get('direction', '?')} 速度{cfg.get('speed', '?')} 角度{cfg.get('angle', '?')}"
                    params_desc.append(desc)
            params_str = " | ".join(params_desc) if params_desc else "所有电机脱机"
            interval = step.get("interval", 0)
            name = step.get("name", f"步骤 {idx}")

            # 创建表格项
            item = QTreeWidgetItem([
                str(idx),
                name,
                params_str,
                str(interval)
            ])
            item.setData(0, Qt.UserRole, step)

            # 确保属性设置
            for i in range(self.steps_table.columnCount()):
                item.setTextAlignment(i, Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)  # 禁止作为拖放目标

            self.steps_table.addTopLevelItem(item)

        except Exception as e:
            self.log(f"步骤添加错误: {str(e)}")
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
                    f"V{config.get('speed', '0')}"
                    f"JG"
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
        current_baud = self.baud_combo.currentText()
        self.port_combo.clear()
        available_ports = self.get_available_ports()
        self.port_combo.addItems(available_ports)
        self.baud_combo.setCurrentText(current_baud)
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

            # 添加详细的连接参数打印
            print(f"尝试连接串口: {port}@{baudrate}")
            print(f"当前线程: {threading.current_thread().name}")

            # 创建临时串口对象测试连接
            test_serial = serial.Serial()
            test_serial.port = port
            test_serial.baudrate = baudrate
            test_serial.timeout = 2
            test_serial.open()
            print(f"连接测试成功，当前缓存状态: in_waiting={test_serial.in_waiting}")
            test_serial.close()

            # 正式连接
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,  # 明确设置参数
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2,
                write_timeout=2
            )

            # 验证流控制
            print(f"最终连接参数: {self.serial_port}")
            print(f"流控制设置: {self.serial_port.rtscts} {self.serial_port.dsrdtr}")

            # 清空缓冲区
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            # 启动读取线程
            self.serial_reader = SerialReader(self.serial_port)
            self.serial_reader.data_received.connect(self.handle_serial_data)
            self.serial_reader.start()  # 注意这里要调用start()而不是run()

            self.connect_btn.setText("关闭串口")
            self.log(f"串口已连接 {port}@{baudrate}")
            self.status_bar.showMessage(f"已连接 {port}@{baudrate}")

        except serial.SerialException as e:
            error_msg = f"串口连接失败: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(f"可用端口列表: {serial.tools.list_ports.comports()}")
            QMessageBox.critical(self, "串口错误", error_msg)
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            print(f"[ERROR] {traceback.format_exc()}")
            QMessageBox.critical(self, "错误", error_msg)

    def close_serial(self):
        with self.serial_lock:  # 加锁保证原子操作
            if self.serial_port and self.serial_port.is_open:
                if hasattr(self, 'serial_reader'):
                    self.serial_reader.stop()
                    self.serial_reader.wait(1000)
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
            self.serial_port.write_timeout = 1
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
        # 前置检查
        if not hasattr(self, '_automation_mutex'):
            self._automation_mutex = threading.Lock()

        with self._automation_mutex:
            if self.automation_thread and self.automation_thread.isRunning():
                QMessageBox.warning(self, "警告", "已有正在运行的自动化任务")
                return

            # 参数验证
            if not self.serial_port or not self.serial_port.is_open:
                QMessageBox.critical(self, "错误", "串口未连接")
                return

            try:
                self.loop_count = max(0, int(self.loop_entry.text()))
            except ValueError:
                QMessageBox.critical(self, "错误", "无效的循环次数")
                return


            # 初始化线程
            self.automation_thread = AutomationThread(
                parent=self,
                steps=self.automation_steps,
                loop_count=self.loop_count,
                serial_port=self.serial_port  # 传递参数而非对象
            )

            # 信号连接
            self.automation_thread.update_status.connect(self.status_bar.showMessage)
            self.automation_thread.error_occurred.connect(self.handle_automation_error)
            self.automation_thread.finished.connect(self._on_automation_finished)
            self.automation_thread.progress_updated.connect(self._update_progress)

            # 启动前清理
            self._clear_serial_buffers()

            # 启动线程
            self.automation_thread.start()
            self.log("自动化任务安全启动")

    def _on_automation_finished(self):
        """线程结束后的清理"""
        if self.automation_thread is not None:
            # 安全断开信号连接
            try:
                self.automation_thread.update_status.disconnect()
                self.automation_thread.error_occurred.disconnect()
                self.automation_thread.finished.disconnect()
                self.automation_thread.progress_updated.disconnect()
            except (TypeError, RuntimeError):
                pass  # 如果信号已自动断开则忽略

            # 安全清理线程
            if self.automation_thread.isRunning():
                self.automation_thread.quit()
                self.automation_thread.wait(1000)

            self.automation_thread = None

        self.status_bar.showMessage("自动化运行已完成")
        self._clear_serial_buffers()

    def _clear_serial_buffers(self):
        """清理串口缓冲区"""
        with self.serial_lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.reset_input_buffer()
                    self.serial_port.reset_output_buffer()
                except Exception as e:
                    self.log(f"清理缓冲区失败: {str(e)}")

    def _update_progress(self, value):
        """更新进度显示"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)

    def handle_automation_error(self, message):
        self.stop_automation()
        QMessageBox.critical(self, "运行错误", message)
        self.log(f"错误: {message}")

    def closeEvent(self, event):
        if platform.system() == 'Windows':
            from ctypes import windll
            windll.winmm.timeEndPeriod(1)
        self.stop_automation()  # 确保关闭时停止线程
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        event.accept()

    def stop_automation(self):
        if self.automation_thread is not None:
            # 请求线程停止
            self.automation_thread.stop()
            # 确保线程安全结束
            if self.automation_thread.isRunning():
                self.automation_thread.quit()
                self.automation_thread.wait(1000)
            self.automation_thread = None  # 确保在此处置空
        self.running = False
        self.log("自动化运行已停止")
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
            except:
                pass

    def on_automation_finished(self):
        self.status_bar.showMessage("自动化运行完成")
        self.log("自动化运行已结束")
        # 清理线程引用
        if self.automation_thread is not None:
            self.automation_thread = None

    def update_steps_table(self):
        current_steps = [s for s in self.automation_steps if isinstance(s, dict)]

        # 获取当前所有项
        existing_items = [self.steps_table.topLevelItem(i) for i in range(self.steps_table.topLevelItemCount())]

        # 更新或新增项
        for idx, step in enumerate(current_steps):
            if idx < len(existing_items) and existing_items[idx] is not None:
                self._update_step_item(existing_items[idx], step, idx + 1)
            else:
                self._add_step_to_table(step)

        # 删除多余项
        for i in range(len(current_steps), len(existing_items)):
            self.steps_table.takeTopLevelItem(len(current_steps))

    def _update_step_item(self, item, step, idx):
        params_desc = []
        for motor in ["X", "Y", "Z", "A"]:
            cfg = step.get(motor, {})
            if cfg.get("enable") == "E":
                desc = f"{motor}:方向{cfg.get('direction', '?')} 速度{cfg.get('speed', '?')} 角度{cfg.get('angle', '?')}"
                params_desc.append(desc)
        params_str = " | ".join(params_desc) if params_desc else "所有电机脱机"
        item.setText(0, str(idx))
        item.setText(1, step.get("name", f"步骤 {idx}"))
        item.setText(2, params_str)
        item.setText(3, str(step.get("interval", 0)))
        item.setData(0, Qt.UserRole, step)

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
        self.log_signal.emit(message)  # 通过信号发送日志消息

    def _log_impl(self, message):
        """实际执行日志记录的槽函数"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.moveCursor(QTextCursor.End)

    def clear_log(self):
        self.log_text.clear()




if __name__ == "__main__":
    if os.name == 'nt':
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 设置为系统DPI感知
    # 设置高DPI缩放策略
    QApplication.setHighDpiScaleFactorRoundingPolicy(
       Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    #ctypes.windll.ntdll.RtlSetHeapProtection(ctypes.c_void_p(-1), ctypes.c_ulong(0x00000001))

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(':/meow.ico'))
    app.setStyleSheet(MACOS_STYLE)
    window = MotorControlApp()
    window.show()
    sys.exit(app.exec())