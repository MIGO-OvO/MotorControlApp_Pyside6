# main.py
import ctypes
import json
import os
import re
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
import csv
import datetime
import numpy as np

# 动态导入可选的依赖库，并提供友好的错误提示
try:
    import nidaqmx
    from nidaqmx.constants import TerminalConfiguration
    import pyqtgraph as pg

    NIDAQMX_AVAILABLE = True
except ImportError:
    NIDAQMX_AVAILABLE = False


    # 创建占位符，以防程序在没有库的情况下崩溃
    class DAQThread:
        pass


    class pg:
        pass

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
    QButtonGroup, QCheckBox, QTabWidget, QGroupBox, QSizePolicy, QHeaderView, QTableWidget, QTableWidgetItem,
    QFormLayout, QGraphicsDropShadowEffect, QGraphicsView, QFileDialog, QSplitter,
    QSpinBox, QDoubleSpinBox, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QModelIndex, QTimer, QPointF, QPropertyAnimation, QEasingCurve, \
    QMargins
from PySide6.QtGui import QFont, QTextCursor, QIcon, QColor, QPainter, QPen, QBrush, QLinearGradient, QGradient, \
    QPainterPath, QDoubleValidator, QAction
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QLegend, QScatterSeries

# 样式表 (保持不变)
MACOS_STYLE = """
QWidget {
    font-family: 'Times New Roman', 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
    font-size: 18px;
    color: #000000;
    background-color: #FFFFFF;
}

QGroupBox {
    border: 1px solid #D3D3D3;
    border-radius: 10px;
    margin-top: 8px;
    padding-top: 12px;
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

QPushButton:disabled {
    background-color: #C0C0C0;
}

QComboBox, QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
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

# --- 从 ABS.py 移植过来的 DAQThread ---
if NIDAQMX_AVAILABLE:
    class DAQThread(QThread):
        data_acquired = Signal(float)
        error_occurred = Signal(str)

        def __init__(self, device_name, channel_name, sample_rate, parent=None):
            super().__init__(parent)
            self.device_name = device_name
            self.channel_name = channel_name
            self.sample_rate = sample_rate
            self.running = False
            self.task = None
            self.start_time = time.time()

        def run(self):
            try:
                self.running = True
                self.task = nidaqmx.Task()
                self.task.ai_channels.add_ai_voltage_chan(
                    self.channel_name,
                    terminal_config=TerminalConfiguration.RSE
                )

                interval = 1.0 / self.sample_rate

                while self.running:
                    start_time = time.time()
                    voltage = self.task.read()
                    self.data_acquired.emit(voltage)

                    # 控制采样率
                    elapsed = time.time() - start_time
                    sleep_time = max(0, interval - elapsed)
                    time.sleep(sleep_time)

            except Exception as e:
                self.error_occurred.emit(str(e))
            finally:
                if self.task:
                    self.task.close()
                    self.task = None

        def stop(self):
            self.running = False
            if self.isRunning():
                self.wait(500)  # 等待线程结束


# --- 以下是原有 main.py 的类 ---

class IOSSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 30)
        self.setStyleSheet("""
            QCheckBox {
                background-color: #e5e5e5;
                border-radius: 15px;
            }
            QCheckBox::indicator {
                width: 30px;
                height: 30px;
                border-radius: 15px;
                background-color: white;
                border: 1px solid #cccccc;
            }
            QCheckBox::indicator:checked {
                background-color: #34c759;
                border: none;
                image: none;
                margin-left: 30px;
            }
        """)


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
        painter.setPen(QPen(QColor(200, 200, 200), 4))
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
        self.markers = {}
        self.data = {
            "X": deque(maxlen=10000),
            "Y": deque(maxlen=10000),
            "Z": deque(maxlen=10000),
            "A": deque(maxlen=10000)
        }
        self.init_chart()
        self.setup_axes()
        self.auto_scale_margin = 0.1  # 10%的边距

    def init_chart(self):

        colors = [
            QColor("#1f77b4"),  # 蓝色
            QColor("#2ca02c"),  # 绿色
            QColor("#d62728"),  # 红色
            QColor("#9467bd")  # 紫色
        ]
        # 创建系列并设置样式
        for i, motor in enumerate(["X", "Y", "Z", "A"]):
            # 主曲线设置
            main_series = QLineSeries()
            pen = QPen(colors[i])
            pen.setWidth(2)
            pen.setStyle(Qt.SolidLine)
            main_series.setPen(pen)
            main_series.setName(f"Motor {motor}")
            # 数据标记设置
            marker_series = QScatterSeries()
            marker_series.setMarkerSize(6)
            marker_series.setColor(colors[i])
            marker_series.setBorderColor(Qt.black)
            marker_series.setMarkerShape(QScatterSeries.MarkerShapeCircle)
            # 存储系列引用
            self.series[motor] = main_series
            self.markers[motor] = marker_series
            # 添加到图表
            self.addSeries(main_series)
            self.addSeries(marker_series)
        # 坐标轴设置
        self.axisX = QValueAxis()
        self.axisY = QValueAxis()

        # X轴样式
        self.axisX.setTitleText("Time Sequence")
        self.axisX.setTitleFont(QFont("Times New Roman", 18))
        self.axisX.setLabelsFont(QFont("Times New Roman", 12))
        self.axisX.setGridLineColor(QColor(220, 220, 220))
        self.axisX.setLinePen(QPen(Qt.black, 1.5))
        self.axisX.setLabelFormat("%d")
        # Y轴样式
        self.axisY.setTitleText("Deviation（°）")
        self.axisY.setTitleFont(QFont("Times New Roman", 18))
        self.axisY.setLabelsFont(QFont("Times New Roman", 12))
        self.axisY.setGridLineColor(QColor(220, 220, 220))
        self.axisY.setLinePen(QPen(Qt.black, 1.5))
        self.axisY.setLabelFormat("%.2f")
        # 添加坐标轴
        self.addAxis(self.axisX, Qt.AlignBottom)
        self.addAxis(self.axisY, Qt.AlignLeft)

        # 将系列附加到坐标轴
        for series in self.series.values():
            series.attachAxis(self.axisX)
            series.attachAxis(self.axisY)
            series.setUseOpenGL(True)  # 启用硬件加速
            series.setPointsVisible(False)

        # 标记点优化
        for marker in self.markers.values():
            marker.setBorderColor(Qt.transparent)  # 移除黑色边框
            marker.setBrush(QBrush(Qt.SolidPattern))

        # 图例设置
        self.legend().setVisible(True)
        self.legend().setAlignment(Qt.AlignTop)
        self.legend().setFont(QFont("Times New Roman", 14))
        self.legend().setLabelColor(Qt.black)

        # 图表整体样式
        self.setBackgroundVisible(False)
        self.setMargins(QMargins(10, 10, 10, 5))
        self.setContentsMargins(0, 0, 0, 0)

    def setup_axes(self):
        # 初始化轴范围
        self.axisX.setRange(0, 60)
        self.axisY.setRange(-5, 5)

        # 设置轴自适应策略
        self.axisX.setLabelFormat("%.0f")
        self.axisY.setLabelFormat("%.2f")
        self.axisY.applyNiceNumbers()

    def update_data(self, deviations):
        """只更新启用电机的数据"""
        # 获取当前活动电机（从父窗口）
        parent = self.parent()
        active_motors = parent.active_motors if hasattr(parent, 'active_motors') else ["X", "Y", "Z", "A"]

        # 过滤数据，只处理活动电机
        valid_data = {
            k: round(v, 3)
            for k, v in deviations.get("theoretical", {}).items()
            if v is not None and k in self.data and k in active_motors
        }

        # 更新数据存储
        for motor, dev in valid_data.items():
            self.data[motor].append(dev)
            points = [QPointF(x, y) for x, y in enumerate(self.data[motor])]
            self.series[motor].replace(points[-100:])  # 只显示最近100个点

            # 更新标记点（只显示最新点）
            if points:
                marker_point = [points[-1]]
                self.markers[motor].replace(marker_point)

        # 智能坐标轴调整
        self.auto_scale_axes()

    def auto_scale_axes(self):
        """智能坐标轴缩放算法"""
        # Y轴缩放
        y_values = [y for d in self.data.values() for y in d]
        if y_values:
            y_min = min(y_values)
            y_max = max(y_values)
            y_range = y_max - y_min

            # 动态边距计算
            margin = y_range * self.auto_scale_margin if y_range != 0 else 1
            self.axisY.setRange(y_min - margin, y_max + margin)
        else:
            self.axisY.setRange(-5, 5)  # 默认范围
        # X轴智能缩放
        max_length = max(len(d) for d in self.data.values())
        if max_length > 0:
            visible_points = 100  # 默认显示100个点
            start = max(0, max_length - visible_points)
            self.axisX.setRange(start, max_length)
        else:
            self.axisX.setRange(0, 100)

    def clear(self):
        """清空所有数据"""
        for motor in ["X", "Y", "Z", "A"]:
            self.data[motor].clear()
            self.series[motor].replace([])
            self.markers[motor].replace([])
        self.setup_axes()
        self.update()

    def get_chart_data(self):
        """获取当前图表数据"""
        return {
            motor: list(self.data[motor])
            for motor in ["X", "Y", "Z", "A"]
        }

    def get_motor_data(self, motor):
        """获取指定电机的完整数据"""
        return list(self.data.get(motor, []))

    def replace_data(self, motor, data_points):
        """替换指定电机的数据序列"""
        if motor in self.series:
            points = [QPointF(x, y) for x, y in enumerate(data_points)]
            self.series[motor].replace(points)
            self.data[motor] = deque(data_points, maxlen=200)
            self.auto_scale_axes()


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
        self.setDragDropOverwriteMode(True)  # 禁止创建子项
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

        # 电机控制区
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

            layout.addWidget(group, (i // 2) + 1, i % 2)

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
            params["name"] = self.name_entry.text()
            for motor in self.motors:
                widgets = self.widgets[motor]
                enable = "E" if widgets["enable"].isChecked() else "D"
                direction = "F" if widgets["direction"].checkedButton().text() == "正转" else "B"

                # 处理速度值（空值默认为0）
                speed_text = widgets["speed"].text().strip()
                if not speed_text:
                    speed = "0"
                else:
                    try:
                        speed_val = float(speed_text)
                        if speed_val < 0:
                            raise ValueError
                        speed = f"{speed_val:.1f}".rstrip('0').rstrip('.')  # 保留1位小数并优化格式
                    except ValueError:
                        raise ValueError(f"电机{motor}速度值无效")

                # 处理角度值（空值默认为0，支持G指令）
                angle_text = widgets["angle"].text().strip().upper()
                if not angle_text:
                    angle = "0"
                elif angle_text == "G":
                    angle = "G"
                else:
                    try:
                        angle_val = float(angle_text)
                        if angle_val < 0:
                            raise ValueError
                        angle = f"{angle_val:.3f}".rstrip('0').rstrip('.')  # 保留3位小数并优化格式
                    except ValueError:
                        raise ValueError(f"电机{motor}角度值无效")

                params[motor] = {
                    "enable": enable,
                    "direction": direction,
                    "speed": speed,
                    "angle": angle
                }

            # 处理间隔时间（空值默认为5000ms）
            interval_text = self.interval_entry.text().strip()
            if not interval_text:
                interval = 5000
            else:
                try:
                    interval = int(interval_text)
                    if interval < 0:
                        raise ValueError("间隔时间不能为负数")
                except ValueError:
                    raise ValueError("间隔时间必须为0或正整数")
            params["interval"] = interval

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
        self.buffer = ''

    def run(self):
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        raw_data = self.serial_port.read(self.serial_port.in_waiting)
                        try:
                            data = raw_data.decode('utf-8')
                        except UnicodeDecodeError:
                            data = raw_data.decode('utf-8', errors='replace')
                        self.buffer += data  # 数据累积到缓冲区
                        # 分割完整行
                        while '\n' in self.buffer:
                            line, self.buffer = self.buffer.split('\n', 1)
                            line = line.strip()
                            if line:
                                self.data_received.emit(line)
                except Exception as e:
                    print(f"Serial read error: {str(e)}")
                    break
            time.sleep(0.01)  # 防止CPU占用过高

    def stop(self):
        self.running = False
        if self.isRunning():
            self.wait(200)


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

    def safe_stop(self):
        """停止"""
        self._running.clear()
        self._paused.clear()

        # 尝试中断任何可能的阻塞操作
        with self.lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # 发送紧急停止指令
                    self.serial_port.write(b"XDFV0J0 YDFV0J0 ZDFV0J0 ADFV0J0\r\n")
                    self.serial_port.flush()
                except Exception:
                    pass

                # 关闭串口（仅关闭自动化线程的副本）
                try:
                    self.serial_port.close()
                except Exception:
                    pass

        # 等待线程安全退出
        if self.isRunning():
            self.wait(1000)  # 最多等待1秒

    def _deep_copy_steps(self, steps):
        """拷贝方法"""
        try:
            return json.loads(json.dumps(steps))
        except Exception as e:
            self.error_occurred.emit(f"步骤数据解析失败: {str(e)}")
            return []

    def run(self):
        try:
            while self._running.is_set() and self._should_continue():
                try:
                    # 在关键操作前增加停止检查
                    if not self._running.is_set():
                        break

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
            # 确保最终清理
            try:
                with self.lock:
                    if self.serial_port and self.serial_port.is_open:
                        self.serial_port.close()
            except Exception:
                pass

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
            self.progress_updated.emit(int((step_idx + 1) / len(self.steps) * 100))

            if not self._send_step_command(step):
                break

            self._wait_interval(step.get("interval", 0))

        self._current_loop += 1

    def _send_step_command(self, step):
        """发送步骤命令"""
        # 首先检查是否已停止
        if not self._running.is_set():
            return False

        try:
            parent = self.parent_ref()
            if not parent or not self.serial_port:
                return False

            command = parent.generate_command(step)

            # 再次检查是否已停止
            if not self._running.is_set():
                return False

            with self.lock:  # 使用主线程的串口锁
                # 发送前再次检查
                if not self._running.is_set():
                    return False

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

        # --- 初始化光谱仪相关变量 ---
        if not NIDAQMX_AVAILABLE:
            QMessageBox.critical(self, "依赖库缺失",
                                 "未找到 nidaqmx 或 pyqtgraph 库。\n请运行 'pip install nidaqmx pyqtgraph scipy' 进行安装。\n光谱仪功能将不可用。")

        self._spectro_init_vars()

        # --- 原有初始化 ---
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
        self.angle_update.connect(self.update_angles)
        self.expected_changes = {}  # 记录每个电机理论转动角度
        self.last_angles = {}  # 记录上一次接收到的角度
        self.current_angles = {"X": 0, "Y": 0, "Z": 0, "A": 0}  # 添加当前角度记录
        self.pending_targets = {}
        self.expected_changes = {}  # 保持理论变化量
        self.realtime_deviation_history = {m: deque(maxlen=1000) for m in ["X", "Y", "Z", "A"]}
        self.expected_rotation = {"X": 0, "Y": 0, "Z": 0, "A": 0}  # 预计转动量
        self.theoretical_deviations = {m: None for m in ["X", "Y", "Z", "A"]}  # 理论偏差存储
        self.auto_calibration_enabled = False
        self.copied_step = None
        self.expected_angles = {m: 0.0 for m in ["X", "Y", "Z", "A"]}
        self.is_initializing = False
        self.active_motors = set(["X", "Y", "Z", "A"])
        self.initial_angle_base = {m: None for m in ["X", "Y", "Z", "A"]}  # 初始基准角度
        self.accumulated_rotation = {m: 0.0 for m in ["X", "Y", "Z", "A"]}  # 累积原始转动量
        self.theoretical_target = {m: None for m in ["X", "Y", "Z", "A"]}  # 理论目标角度
        self.is_first_command = True  # 是否是第一条指令
        self.running_mode = "manual"
        self.calibration_amplitude = 1.0

    def init_ui(self):
        self.setWindowTitle("环境现场监测系统控制程序")

        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # 左侧导航栏
        self.nav_frame = QFrame()
        self.nav_frame.setFixedWidth(220)  # 稍微加宽以容纳新标题
        self.nav_layout = QVBoxLayout(self.nav_frame)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(8)

        # ================= 控制模式 =================
        control_group = QGroupBox("电机控制模式")
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
        self.motor_status_group = QGroupBox("电机状态与分析")
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

        # ================= 光谱仪控制 (新增) =================
        spectro_control_group = QGroupBox("光谱仪控制")
        spectro_control_group.setFont(QFont("Microsoft YaHei", 13))
        spectro_control_layout = QVBoxLayout(spectro_control_group)

        self.spectro_btn = QPushButton("光谱分析")
        self.spectro_btn.setCheckable(True)
        self.spectro_btn.setFont(QFont("Microsoft YaHei", 13))
        self.spectro_btn.setFixedHeight(40)
        spectro_control_layout.addWidget(self.spectro_btn)
        self.nav_layout.addWidget(spectro_control_group)

        # ================= 串口设置 =================
        serial_group = QGroupBox("串口设置")
        serial_group.setFont(QFont("Microsoft YaHei", 13))
        serial_layout = QVBoxLayout(serial_group)

        # 端口选择
        self.port_combo = QComboBox()
        self.port_combo.addItems(self.get_available_ports())
        if "COM4" in self.get_available_ports():
            self.port_combo.setCurrentText("COM4")

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

        # ================= 自动校准开关 (移动到电机状态组内或保持独立) =================
        self.add_auto_calibration_switch()  # 保持原位

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

        # 位置数据页
        self.position_tab = QWidget()
        self.init_position_tab()
        self.tab_widget.addTab(self.position_tab, "")

        # 数据分析页
        self.analysis_tab = QWidget()
        self.init_analysis_tab()
        self.tab_widget.addTab(self.analysis_tab, "")

        # 光谱分析页 (新增)
        self.spectro_tab = QWidget()
        self.init_spectro_tab()
        self.tab_widget.addTab(self.spectro_tab, "")

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
        self.spectro_btn.clicked.connect(lambda: self.switch_tab(4))  # 新增连接

        self.connect_btn.clicked.connect(self.toggle_serial)
        refresh_btn.clicked.connect(self.refresh_serial_ports)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 初始刷新光谱仪设备
        if NIDAQMX_AVAILABLE:
            self._spectro_refresh_devices()

    # --- 以下是所有光谱仪相关方法 ---

    def _spectro_init_vars(self):
        """初始化所有光谱仪相关的实例变量。"""
        self.spectro_reference_voltage = None
        self.spectro_is_measuring = False
        self.spectro_task = None
        self.spectro_voltage_data = []
        self.spectro_absorbance_data = []
        self.spectro_max_data_points = 500
        self.spectro_sample_rate = 100
        self.spectro_data_log = []
        self.spectro_daq_thread = None
        self.spectro_timer = QTimer(self)
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
        self.spectro_voltage_value.setStyleSheet("font-size: 20px; color: #007AFF; font-weight: bold;")
        self.spectro_absorbance_value = QLabel("0.0000")
        self.spectro_absorbance_value.setStyleSheet("font-size: 20px; color: #FF2D55; font-weight: bold;")
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
        self.spectro_voltage_plot.setBackground('w')
        self.spectro_voltage_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_voltage_curve = self.spectro_voltage_plot.plot(pen=pg.mkPen(color='#007AFF', width=2))
        self.spectro_voltage_plot.setMinimumHeight(200)
        v_layout.addWidget(self.spectro_voltage_plot)
        charts_layout.addWidget(voltage_group)

        # Absorbance Plot
        absorbance_group = QGroupBox("吸光度 (Abs)")
        a_layout = QVBoxLayout(absorbance_group)
        self.spectro_absorbance_plot = pg.PlotWidget()
        self.spectro_absorbance_plot.setBackground('w')
        self.spectro_absorbance_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectro_absorbance_curve = self.spectro_absorbance_plot.plot(pen=pg.mkPen(color='#FF2D55', width=2))
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
            if not device_name: return
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
        self.spectro_data_log.append({
            'timestamp': timestamp,
            'voltage': voltage,
            'absorbance': absorbance,
        })

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
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"absorbance_data_{timestamp}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "保存数据", filename, "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, 'w', newline='') as csvfile:
                fieldnames = ['timestamp', 'voltage', 'absorbance']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.spectro_data_log)
            self.log(f"光谱数据已保存至 {os.path.basename(path)}")
        except Exception as e:
            self.log(f"保存数据失败: {e}")
            QMessageBox.critical(self, "保存错误", f"文件保存失败: {e}")

    # --- 以下是原有 main.py 的方法 ---

    def add_auto_calibration_switch(self):
        """在左侧导航栏添加自动校准开关和幅值输入"""
        auto_cal_group = QGroupBox("自动校准")
        auto_cal_group.setFont(QFont("Microsoft YaHei", 13))
        auto_cal_layout = QVBoxLayout(auto_cal_group)
        # 开关布局
        switch_frame = QFrame()
        hbox = QHBoxLayout(switch_frame)
        auto_cal_label = QLabel("校准开关:")
        self.auto_cal_switch = IOSSwitch()
        hbox.addWidget(auto_cal_label)
        hbox.addWidget(self.auto_cal_switch)
        auto_cal_layout.addWidget(switch_frame)
        # 校准幅值输入框
        amplitude_frame = QFrame()
        hbox_amp = QHBoxLayout(amplitude_frame)
        amp_label = QLabel("校准幅值：")
        self.calibration_amp_input = QLineEdit()
        self.calibration_amp_input.setFixedWidth(80)
        self.calibration_amp_input.setText("1.0")
        self.calibration_amp_input.setValidator(QDoubleValidator(0.0, 2.0, 2))  # 限制输入范围0-2，两位小数
        hbox_amp.addWidget(amp_label)
        hbox_amp.addWidget(self.calibration_amp_input)
        auto_cal_layout.addWidget(amplitude_frame)
        # 初始状态设置
        self.calibration_amp_input.setEnabled(False)  # 默认禁用
        # 信号连接
        self.auto_cal_switch.stateChanged.connect(self.toggle_auto_calibration)
        self.calibration_amp_input.textChanged.connect(self.update_calibration_amplitude)
        self.nav_layout.insertWidget(3, auto_cal_group)

    def update_calibration_amplitude(self):
        """更新校准幅值"""
        try:
            self.calibration_amplitude = float(self.calibration_amp_input.text())
        except ValueError:
            self.log("校准幅值无效，已重置为1.0")
            self.calibration_amp_input.setText("1.0")
            self.calibration_amplitude = 1.0

    def toggle_auto_calibration(self, state):
        self.auto_calibration_enabled = state
        self.calibration_amp_input.setEnabled(state)
        status = "启用" if state else "停用"
        self.log(f"自动校准已{status}")

    def init_position_tab(self):
        layout = QVBoxLayout(self.position_tab)

        # 电机状态展示区
        motor_frame = QFrame()
        motor_layout = QHBoxLayout(motor_frame)
        self.motors = {}
        self.angle_labels = {}
        self.calibration_switches = {}  # 新增校准开关字典

        for motor in ["X", "Y", "Z", "A"]:
            group = QGroupBox(f"电机 {motor}")
            vbox = QVBoxLayout(group)
            vbox.setAlignment(Qt.AlignCenter)

            # 动画组件
            circle = MotorCircle()
            self.motors[motor] = circle

            # 角度显示
            label = QLabel("0.000°", alignment=Qt.AlignCenter)
            label.setStyleSheet("font-size: 24px; color: #007AFF;")
            self.angle_labels[motor] = label

            # 校准开关
            switch_frame = QFrame()
            hbox = QHBoxLayout(switch_frame)
            hbox.setContentsMargins(0, 0, 0, 0)
            switch_label = QLabel("校准开关:")
            switch = IOSSwitch()
            self.calibration_switches[motor] = switch
            hbox.addWidget(switch_label)
            hbox.addWidget(switch)

            vbox.addWidget(circle, alignment=Qt.AlignCenter)
            vbox.addWidget(label)
            vbox.addWidget(switch_frame)
            motor_layout.addWidget(group)

        layout.addWidget(motor_frame)

        # 实时角度表格
        self.angle_table = QTableWidget()
        self.angle_table.setRowCount(4)
        self.angle_table.setColumnCount(5)
        self.angle_table.setHorizontalHeaderLabels([
            "电机",
            "当前角度",
            "目标角度",
            "理论偏差",
            "实时偏差"
        ])
        # 设置表格样式
        self.angle_table.verticalHeader().setVisible(False)  # 隐藏垂直表头
        self.angle_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)  # 自动拉伸列宽
        self.angle_table.setAlternatingRowColors(True)  # 交替行颜色
        # 设置表头居中
        header = self.angle_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
                QHeaderView::section {
                    font-size: 18px;
                    padding: 5px;
                    background-color: #f0f0f0;
                }
            """)

        # 设置表格内容全局居中
        self.angle_table.setStyleSheet("""
                QTableWidget {
                    font-size: 18px;
                }
                QTableWidget QTableCornerButton::section {
                    background-color: #f0f0f0;
                }
                QTableWidget::item {
                    text-align: center;
                }
            """)

        # 新增初始化按钮
        btn_frame = QFrame()
        hbox = QHBoxLayout(btn_frame)
        self.init_btn = QPushButton("电机初始化")
        self.init_btn.clicked.connect(self.start_calibration)
        self.get_angle_btn = QPushButton("获取当前角度")
        self.get_angle_btn.clicked.connect(self.request_angles)

        for btn in [self.init_btn, self.get_angle_btn]:
            btn.setStyleSheet("font-size: 18px; padding: 8px;")
            hbox.addWidget(btn)

        layout.addWidget(QLabel("实时角度数据:"))
        layout.addWidget(self.angle_table)
        layout.addWidget(btn_frame)

    def start_calibration(self):
        """开始初始化流程"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        self.calibration_attempts = 0
        self.last_calibration_angles = {m: [] for m in ["X", "Y", "Z", "A"]}
        self.send_calibration_command()

    def send_calibration_command(self):
        motor_commands = {}
        for motor in ["X", "Y", "Z", "A"]:
            if self.calibration_switches[motor].isChecked():
                current_angle = (self.current_angles.get(motor, 0.0) or 0.0) % 360

                # 计算最短路径
                if current_angle > 180:
                    target_angle = 360 - current_angle
                    direction = "EF"  # 正向转动
                else:
                    target_angle = current_angle
                    direction = "EB"  # 反向转动

                # 生成校准指令（固定速度5RPM，三位小数精度）
                motor_commands[motor] = f"{motor}{direction}V5J{target_angle:.3f}"
            else:
                # 未选择的电机发送停转指令
                motor_commands[motor] = f"{motor}DFV0J0"

        # 按X/Y/Z/A顺序拼接完整指令
        full_command = "".join([motor_commands[m] for m in ["X", "Y", "Z", "A"]]) + "\r\n"

        if self.send_command(full_command):
            # 发送校准命令后等待10秒再读取角度
            QTimer.singleShot(10000, self.send_angle_request)

    def format_number(self, value):
        """格式化数值，去除末尾多余的零和小数点"""
        s = "{:.3f}".format(value).rstrip('0').rstrip('.')
        return s

    def send_angle_request(self):
        self.request_angles()  # 发送获取角度指令
        # 等待50ms后处理校准结果
        QTimer.singleShot(50, self.process_calibration_result)

    def process_calibration_result(self):
        validation_passed = True
        for motor in ["X", "Y", "Z", "A"]:
            if self.calibration_switches[motor].isChecked():
                # 获取校准后的最新角度
                current_angle = self.current_angles.get(motor, 0) % 360

                # 验证校准精度（±1°范围内视为成功）
                if min(current_angle, 360 - current_angle) > 1.5:
                    validation_passed = False
                    self.log(f"电机{motor}校准偏差过大：{current_angle:.2f}°")

        if validation_passed or self.calibration_attempts >= 3:
            if validation_passed:
                self.log("校准成功完成")
                self.clear_chart()
                QMessageBox.information(self, "完成", "电机校准完成")
            else:
                self.log("校准失败，请检查机械结构")
                QMessageBox.warning(self, "错误", "校准失败，请检查电机是否卡顿")
        else:
            self.calibration_attempts += 1
            self.send_calibration_command()

    def run_calibration_cycle(self):
        # 发送获取角度指令
        self.request_angles()

        # 延时后执行校准
        QTimer.singleShot(500, self.process_calibration)

    def process_calibration(self):
        # 生成校准指令
        command = ""
        for motor in ["X", "Y", "Z", "A"]:
            if self.calibration_switches[motor].isChecked():
                current = self.current_angles.get(motor, 0)
                angle_to_move = -round(current % 360, 3)

                # 生成带三位小数的角度指令
                cmd = f"{motor}EFV20J{abs(angle_to_move):.3f}"  # 固定速度20RPM
                if angle_to_move < 0:
                    cmd = cmd.replace("EF", "EB")
                command += cmd

        # 发送完整指令（包含所有电机）
        full_command = ""
        for m in ["X", "Y", "Z", "A"]:
            if m in command:
                full_command += command.split(m)[1].split("J")[0] + "J"  # 提取对应电机指令
            else:
                full_command += f"{m}DFV0J0"  # 未校准电机发送停转指令

        if self.send_command(full_command + "\r\n"):
            self.calibration_attempts += 1
            QTimer.singleShot(1000, self.validate_calibration)

    def validate_calibration(self):
        # 检查最近两次角度值
        valid = True
        for motor in ["X", "Y", "Z", "A"]:
            if self.calibration_switches[motor].isChecked():
                angles = self.last_calibration_angles[motor][-2:]
                if len(angles) < 2 or any(abs(a) > 0.5 for a in angles):
                    valid = False

        if valid or self.calibration_attempts >= 5:  # 最大尝试5次
            if valid:
                self.log("校准成功完成")
                QMessageBox.information(self, "完成", "电机校准完成")
            else:
                self.log("校准失败，请检查连接")
                QMessageBox.warning(self, "错误", "校准失败，请手动检查")
        else:
            self.run_calibration_cycle()

    def init_analysis_tab(self):
        """初始化分析标签页布局"""
        layout = QVBoxLayout(self.analysis_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # ================= 图表展示区域 =================
        self.chart_view = QChartView(AnalysisChart())
        self.chart_view.setRenderHint(QPainter.Antialiasing, True)
        self.chart_view.setMinimumHeight(350)
        layout.addWidget(self.chart_view, stretch=3)

        # ================= 控制按钮区域 =================
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(10)

        # 电机选择组件
        motor_selector = QFrame()
        hbox_motor = QHBoxLayout(motor_selector)
        hbox_motor.setContentsMargins(0, 0, 0, 0)
        hbox_motor.addWidget(QLabel("保存电机数据:"))

        self.export_motor_combo = QComboBox()
        self.export_motor_combo.addItems(["全部", "X轴", "Y轴", "Z轴", "A轴"])
        self.export_motor_combo.setFixedWidth(120)
        self.export_motor_combo.setFont(QFont("Microsoft YaHei", 10))
        hbox_motor.addWidget(self.export_motor_combo)

        control_layout.addWidget(motor_selector)

        # 操作按钮组
        button_style = """
        QPushButton {
            font-size: 12px;
            padding: 5px 8px;
            min-width: 70px;
            max-height: 28px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        """

        action_buttons = [
            ("导入数据", self.import_chart_data),  # 新增按钮
            ("清空图表", self.clear_chart),
            ("保存图片", self.save_chart_image),
            ("导出数据", self.export_chart_data)
        ]

        for btn_text, handler in action_buttons:
            btn = QPushButton(btn_text)
            btn.setStyleSheet(button_style)
            btn.clicked.connect(handler)
            control_layout.addWidget(btn)

        control_layout.addStretch(1)  # 右侧弹性空间
        layout.addWidget(control_frame, stretch=0)

        # ================= 统计面板区域 =================
        stats_group = QGroupBox("偏差统计")
        stats_group.setFont(QFont("Microsoft YaHei", 12))
        stats_layout = QHBoxLayout(stats_group)

        # 为每个电机创建统计面板
        self.stats_widgets = {}
        for motor in ["X", "Y", "Z", "A"]:
            group = QGroupBox(f"电机{motor}")
            form = QFormLayout(group)

            labels = {
                'current': QLabel("0.00°"),
                'theoretical': QLabel("0.00°"),
                'average': QLabel("0.00°"),
                'dev_rate': QLabel("N/A")
            }

            # 设置标签样式
            for lbl in labels.values():
                lbl.setFont(QFont("Roboto Mono", 10))
                lbl.setAlignment(Qt.AlignRight)

            form.addRow("实时偏差:", labels['current'])
            form.addRow("理论偏差:", labels['theoretical'])
            form.addRow("平均偏差:", labels['average'])
            form.addRow("偏差率:", labels['dev_rate'])

            self.stats_widgets[motor] = labels
            stats_layout.addWidget(group)

        layout.addWidget(stats_group, stretch=1)

    def clear_chart(self):
        # 清空图表数据
        self.chart_view.chart().clear()
        # 重置偏差数据集
        self.deviation_data = {m: deque(maxlen=100) for m in ["X", "Y", "Z", "A"]}
        self.theoretical_deviations = {m: None for m in ["X", "Y", "Z", "A"]}
        self.target_angles = {m: None for m in ["X", "Y", "Z", "A"]}
        self.expected_rotation = {m: 0.0 for m in ["X", "Y", "Z", "A"]}
        # 更新实时数据表
        current_angles = {m: self.current_angles.get(m, 0.0) for m in ["X", "Y", "Z", "A"]}
        deviations = {m: None for m in ["X", "Y", "Z", "A"]}
        self.update_angle_table(current_angles, self.target_angles, deviations)
        # 重置统计数据和颜色
        for motor in ["X", "Y", "Z", "A"]:
            labels = self.stats_widgets[motor]
            labels['current'].setText("N/A°")
            labels['theoretical'].setText("N/A°")
            labels['average'].setText("N/A°")
            labels['dev_rate'].setText("N/A")
            for label in labels.values():
                label.setStyleSheet("color: black;")
        self.log("图表和统计数据已重置")

    def save_chart_image(self):
        """保存为图片文件"""
        options = QFileDialog.Options()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图表", "",
            "PNG图像 (*.png);;JPEG图像 (*.jpg)",
            options=options
        )

        if path:
            pixmap = self.chart_view.grab()
            if pixmap.save(path):
                self.log(f"图表已保存至 {path}")
            else:
                QMessageBox.warning(self, "错误", "图片保存失败")

    def export_chart_data(self):
        try:
            import pandas as pd
        except ImportError:
            QMessageBox.critical(self, "错误", "请先安装pandas库：pip install pandas")
            return
        # 获取选择的电机
        selected = self.export_motor_combo.currentText()
        motor_map = {
            "全部": ["X", "Y", "Z", "A"],
            "X轴": ["X"],
            "Y轴": ["Y"],
            "Z轴": ["Z"],
            "A轴": ["A"]
        }
        selected_motors = motor_map[selected]

        # 获取数据并对齐长度
        chart_data = self.chart_view.chart().get_chart_data()
        max_length = max(len(chart_data[m]) for m in selected_motors if chart_data[m]) if any(
            chart_data.values()) else 0
        if max_length == 0:
            QMessageBox.warning(self, "警告", "当前没有可导出的数据")
            return

        # 填充缺失值为NaN
        data_dict = {}
        for motor in selected_motors:
            values = chart_data[motor]
            if len(values) < max_length:
                values += [float('nan')] * (max_length - len(values))
            data_dict[f"{motor}轴偏差"] = values

        # 保存对话框
        options = QFileDialog.Options()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出数据", "",
            "Excel文件 (*.xlsx)",
            options=options
        )

        if path:
            try:
                df = pd.DataFrame(data_dict)
                df.index.name = "采样序列"
                with pd.ExcelWriter(path) as writer:
                    df.to_excel(writer)
                self.log(f"数据已导出至 {path}")
            except Exception as e:
                QMessageBox.critical(self, "导出错误", f"文件写入失败: {str(e)}")

    def import_chart_data(self):
        """支持导入单轴Excel数据"""
        try:
            import pandas as pd
        except ImportError:
            QMessageBox.critical(self, "错误", "请先安装pandas库：pip install pandas")
            return
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择数据文件", "",
            "Excel文件 (*.xlsx);;CSV文件 (*.csv)",
            options=options
        )
        if not file_path:
            return
        try:
            # 读取数据文件
            if file_path.endswith('.xlsx'):
                df = pd.read_excel(file_path, index_col=0)
            else:
                df = pd.read_csv(file_path, index_col=0)
            # 识别有效数据列
            valid_columns = []
            motor_mapping = {
                'X轴偏差': 'X',
                'Y轴偏差': 'Y',
                'Z轴偏差': 'Z',
                'A轴偏差': 'A'
            }

            # 检查至少包含一个有效列
            for col in df.columns:
                if col in motor_mapping:
                    valid_columns.append(col)

            if not valid_columns:
                raise ValueError("未检测到有效偏差数据列（列名示例：X轴偏差）")
            # 弹窗选择导入模式
            mode = self._show_import_dialog()
            if not mode:
                return
            # 处理数据导入
            for col in valid_columns:
                motor = motor_mapping[col]
                data = df[col].dropna().tolist()

                if mode == "replace":
                    # 替换模式：清空现有数据
                    self.chart_view.chart().data[motor].clear()
                    self.chart_view.chart().data[motor].extend(data)
                else:
                    # 追加模式：添加到现有数据尾部
                    self.chart_view.chart().data[motor].extend(data)

                # 更新数据点（保留最近200个）
                points = [QPointF(x, y) for x, y in enumerate(self.chart_view.chart().data[motor])]
                self.chart_view.chart().series[motor].replace(points[-200:])
            # 刷新显示
            self.chart_view.chart().auto_scale_axes()
            self._update_stats_after_import(df, valid_columns)
            self.log(f"成功导入{len(valid_columns)}轴数据")
        except Exception as e:
            QMessageBox.critical(self, "导入错误", f"数据导入失败: {str(e)}")

    def _show_import_dialog(self):
        """显示导入选项对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("导入选项")
        layout = QVBoxLayout(dialog)

        # 模式选择
        mode_group = QButtonGroup(dialog)
        rb_replace = QRadioButton("替换现有数据", dialog)
        rb_append = QRadioButton("追加到现有数据", dialog)
        rb_replace.setChecked(True)

        mode_group.addButton(rb_replace)
        mode_group.addButton(rb_append)

        # 确认按钮
        btn_confirm = QPushButton("确认导入", dialog)
        btn_confirm.clicked.connect(dialog.accept)

        layout.addWidget(QLabel("请选择数据导入模式:"))
        layout.addWidget(rb_replace)
        layout.addWidget(rb_append)
        layout.addWidget(btn_confirm)

        if dialog.exec() == QDialog.Accepted:
            return "replace" if rb_replace.isChecked() else "append"
        return None

    def _update_stats_after_import(self, df, valid_columns):
        """更新统计信息（仅更新导入的轴）"""
        for col in valid_columns:
            motor = col[0]  # 从"X轴偏差"提取X
            data = df[col].dropna()

            if not data.empty:
                labels = self.stats_widgets[motor]
                labels['current'].setText(f"{data.iloc[-1]:.2f}°")
                labels['average'].setText(f"{data.mean():.2f}°")
                labels['dev_rate'].setText(
                    f"{(data.iloc[-1] / data.mean() * 100 if data.mean() != 0 else 0):.1f}%"
                )

    def _update_all_stats(self, df):
        """更新所有统计信息"""
        self.cumulative_deviations = {m: 0.0 for m in ["X", "Y", "Z", "A"]}

        for motor in ["X", "Y", "Z", "A"]:
            col = f"{motor}轴偏差"
            if col not in df.columns: continue
            data = df[col].dropna()

            if not data.empty:
                # 计算统计指标
                current = data.iloc[-1]
                avg = data.mean()

                # 更新显示
                labels = self.stats_widgets[motor]
                labels['current'].setText(f"{current:.2f}°")
                labels['average'].setText(f"{avg:.2f}°")
                labels['dev_rate'].setText(f"{(current / avg * 100 if avg != 0 else 0):.1f}%")

    def request_angles(self):
        """发送获取角度指令"""
        ANGLE_command = "GETANGLE"
        self.send_command(ANGLE_command + "\r\n")

    def switch_tab(self, index):
        self.tab_widget.setCurrentIndex(index)
        # 更新导航按钮的选中状态
        buttons = [self.manual_btn, self.auto_btn, self.position_btn, self.analysis_btn, self.spectro_btn]
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)

    def update_angles(self, data):
        """更新角度显示（适配新版数据结构）"""
        try:
            for motor in self.active_motors:
                current_angle = data["current"].get(motor, 0)
                self.motors[motor].set_angle(current_angle % 360)
                self.angle_labels[motor].setText(f"{current_angle:.3f}°")

            # 清空表格旧数据
            self.angle_table.clearContents()

            # 仅更新启用电机
            for motor in data["current"].keys():
                row = ["X", "Y", "Z", "A"].index(motor)

                current = data["current"][motor]
                target = data["targets"].get(motor)
                theo_dev = data["theoretical"].get(motor)
                real_dev = data["realtime"].get(motor)

                # 填充表格数据
                items = [
                    self._create_centered_item(motor),
                    self._create_centered_item(f"{current:.1f}°"),
                    self._create_centered_item(f"{target:.1f}°" if target is not None else "N/A"),
                    self._create_centered_item(f"{theo_dev:.1f}°" if theo_dev is not None else "N/A"),
                    self._create_centered_item(f"{real_dev:.1f}°" if real_dev is not None else "N/A")
                ]

                # 设置偏差颜色
                for dev, col in [(theo_dev, 3), (real_dev, 4)]:
                    if dev is not None:
                        color = "#FF0000" if abs(dev) > 5 else "#FFA500" if abs(dev) > 2 else "black"
                        items[col].setForeground(QColor(color))
                for col in range(5):
                    self.angle_table.setItem(row, col, items[col])

        except Exception as e:
            print(f"角度更新异常: {str(e)}")
            traceback.print_exc()

    def _update_angle_table_row(self, motor, current, target, deviation):
        """更新表格"""
        row = ["X", "Y", "Z", "A"].index(motor)
        # 创建表格项
        items = [
            self._create_centered_item(motor),
            self._create_centered_item(f"{current:.1f}°"),
            self._create_centered_item(f"{target:.1f}°" if target is not None else "N/A"),
            self._create_centered_item(f"{deviation:.1f}°" if deviation is not None else "N/A")
        ]
        # 偏差颜色设置
        if deviation is not None:
            if abs(deviation) > 20:
                items[-1].setForeground(QColor(255, 0, 0))
            elif abs(deviation) > 5:
                items[-1].setForeground(QColor(255, 165, 0))
        else:
            # 当偏差为None时，恢复默认颜色
            items[-1].setForeground(QColor(0, 0, 0))  # 黑色
        # 更新表格
        for col in range(4):
            self.angle_table.setItem(row, col, items[col])

    def _create_centered_item(self, text):
        """创建居中显示的表格项"""
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def update_angle_table(self, current_data, target_data, deviations):
        """更新实时角度表格（新增目标列）"""
        self.angle_table.setRowCount(4)

        for row, motor in enumerate(["X", "Y", "Z", "A"]):
            current = current_data.get(motor, 0)
            target = target_data.get(motor)
            deviation = deviations.get(motor)

            # 格式化显示内容
            items = [
                QTableWidgetItem(motor),
                QTableWidgetItem(f"{current:.3f}°"),
                QTableWidgetItem(f"{target:.3f}°" if target is not None else "N/A"),
                QTableWidgetItem(f"{deviation:.3f}°" if deviation is not None else "N/A")
            ]

            # 偏差颜色标记
            if deviation is not None:
                if abs(deviation) > 5:
                    items[-1].setForeground(QColor(255, 0, 0))  # 红色显示大偏差
                elif abs(deviation) > 2:
                    items[-1].setForeground(QColor(255, 165, 0))  # 橙色显示中等偏差

            # 填充表格
            for col in range(4):
                item = items[col]
                item.setTextAlignment(Qt.AlignCenter)
                self.angle_table.setItem(row, col, item)

    def handle_serial_data(self, data):
        """处理串口数据并计算两种偏差"""
        if data.startswith("ANGLE"):
            # 解析当前角度
            current_angles = {}
            matches = re.findall(r"([A-Z])(-?\d+\.\d{3})", data)
            for motor, value in matches:
                try:
                    current_angles[motor] = float(value) % 360
                except ValueError:
                    current_angles[motor] = 0.0

            # 计算两种偏差
            theoretical_deviations = {}
            theoretical_targets = {}
            realtime_deviations = {}

            for motor in ["X", "Y", "Z", "A"]:
                # 仅处理启用电机
                if motor not in self.active_motors:
                    theoretical_deviations[motor] = None
                    realtime_deviations[motor] = None
                    theoretical_targets[motor] = None
                    continue

                current = current_angles.get(motor, 0.0)

                # 实时偏差计算
                if motor in self.pending_targets and self.pending_targets[motor] is not None:
                    realtime_dev = (current - self.pending_targets[motor]) % 360
                    realtime_dev = realtime_dev - 360 if realtime_dev > 180 else realtime_dev
                    realtime_deviations[motor] = realtime_dev
                else:
                    realtime_deviations[motor] = None

                # 理论偏差计算
                if self.initial_angle_base.get(motor) is not None:
                    theoretical_target = (self.initial_angle_base[motor] +
                                          self.accumulated_rotation[motor]) % 360
                    theoretical_targets[motor] = theoretical_target
                    theoretical_dev = (current - theoretical_target) % 360
                    if theoretical_dev > 180:
                        theoretical_dev -= 360
                    theoretical_deviations[motor] = theoretical_dev
                else:
                    theoretical_deviations[motor] = None
                    theoretical_targets[motor] = None

            # 自动校准处理（仅自动模式）
            if self.running_mode == "auto" and self.auto_calibration_enabled:
                for motor in self.active_motors:
                    if theoretical_deviations[motor] is not None:
                        self.theoretical_deviations[motor] = theoretical_deviations[motor]

            # 更新界面数据
            self.current_angles.update(current_angles)
            filtered_data = {
                "current": {k: v for k, v in current_angles.items() if k in self.active_motors},
                "theoretical": {k: v for k, v in theoretical_deviations.items() if k in self.active_motors},
                "realtime": {k: v for k, v in realtime_deviations.items() if k in self.active_motors},
                "targets": {k: v for k, v in theoretical_targets.items() if k in self.active_motors}
            }
            self.angle_update.emit(filtered_data)  # 发送过滤后的数据
            self.chart_view.chart().update_data(filtered_data)
            self.update_stats_panel(filtered_data)
        else:
            # 其他非角度数据直接记录
            self.log(f"接收: {data}")

    def update_stats_panel(self, data):
        """更新统计面板，只处理启用的电机"""
        for motor in ["X", "Y", "Z", "A"]:
            labels = self.stats_widgets[motor]

            # 重置未启用电机的显示
            if motor not in self.active_motors:
                self._set_stat_na(motor)
                continue

            # 获取最新数据
            theo_dev = data["theoretical"].get(motor)
            real_dev = data["realtime"].get(motor)

            # 计算平均偏差（使用历史数据）
            motor_data = self.chart_view.chart().data[motor]
            avg_dev = sum(motor_data) / len(motor_data) if motor_data else 0

            # 计算偏差率（理论偏差/原始转动量）
            raw_rotation = abs(self.expected_rotation.get(motor, 1))  # 避免除零
            dev_rate = (abs(theo_dev / raw_rotation) * 100) if raw_rotation != 0 and theo_dev is not None else 0

            # 更新显示
            labels['current'].setText(f"{real_dev:.2f}°" if real_dev is not None else "N/A")
            labels['theoretical'].setText(f"{theo_dev:.2f}°" if theo_dev is not None else "N/A")
            labels['average'].setText(f"{avg_dev:.2f}°")
            labels['dev_rate'].setText(f"{dev_rate:.1f}%")

            # 根据偏差值设置颜色
            self._update_stat_color(labels, theo_dev if theo_dev is not None else 0)

    def _set_stat_na(self, motor):
        """设置未启用电机的统计显示"""
        labels = self.stats_widgets[motor]
        for key in ['current', 'theoretical', 'average', 'dev_rate']:
            labels[key].setText("N/A")
            labels[key].setStyleSheet("color: gray;")

    def _update_stat_color(self, labels, current_dev):
        """根据偏差值更新统计颜色"""
        dev_abs = abs(current_dev)
        color = "black"  # 默认黑色

        if dev_abs > 5.0:  # 严重偏差
            color = "#FF0000"  # 红色
        elif dev_abs > 2.0:  # 警告偏差
            color = "#FFA500"  # 橙色

        # 只更新数值标签的颜色
        for label_key in ['current', 'theoretical', 'average', 'dev_rate']:
            labels[label_key].setStyleSheet(f"color: {color};")

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
        base_size = 18
        scale_h = self.height() / 1080
        new_size = max(12, int(base_size * scale_h))

        # 更新全局样式，但不影响特定组件
        # self.setStyleSheet(MACOS_STYLE.replace("18px", f"{new_size}px"))

        # 调整表格列宽
        if hasattr(self, 'steps_table'):
            total_width = self.steps_table.width()
            column_count = self.steps_table.columnCount()
            if column_count > 0:
                ratio = [0.1, 0.15, 0.6, 0.15]
                for i in range(column_count):
                    self.steps_table.setColumnWidth(i, int(total_width * ratio[i]))

    # ... (此处省略了大量未修改的 main.py 原有方法以缩减篇幅) ...
    # ... (init_manual_tab, init_auto_tab, send_manual_command, etc.) ...
    # ... (所有电机控制、自动化流程、预设管理的方法都保持不变) ...
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

        del_manual_btn = QPushButton("删除")
        del_manual_btn.clicked.connect(lambda: self.delete_preset('manual'))

        preset_layout.addWidget(preset_lbl)
        preset_layout.addWidget(self.manual_preset_combo)
        preset_layout.addWidget(load_btn)
        preset_layout.addWidget(save_btn)
        preset_layout.addWidget(del_manual_btn)
        hbox.addWidget(preset_frame)

        layout.addWidget(control_frame)

        # +++ 新增定时运行控件 +++
        timer_frame = QFrame()
        timer_layout = QHBoxLayout(timer_frame)

        # 定时运行标签
        timer_label = QLabel("定时运行:")
        timer_label.setFont(QFont("Microsoft YaHei", 16))

        # 时间输入框
        self.timer_input = QLineEdit()
        self.timer_input.setPlaceholderText("时长")
        self.timer_input.setFont(QFont("Microsoft YaHei", 16))
        self.timer_input.setFixedWidth(100)

        # 时间单位选择
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["秒", "分钟", "小时"])
        self.time_unit_combo.setFont(QFont("Microsoft YaHei", 16))
        self.time_unit_combo.setFixedWidth(100)

        # 按钮容器
        btn_container = QFrame()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        # 运行按钮
        self.timer_run_btn = QPushButton("运行")
        self.timer_run_btn.setFont(QFont("Microsoft YaHei", 16))
        self.timer_run_btn.clicked.connect(self.start_timed_run)

        # 新增按钮
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
        # 验证输入
        try:
            duration = float(self.timer_input.text())
            unit = self.time_unit_combo.currentText()

            # 转换为秒
            if unit == "分钟":
                duration *= 60
            elif unit == "小时":
                duration *= 3600

            if duration <= 0:
                raise ValueError("时长必须大于0")

        except ValueError as e:
            QMessageBox.critical(self, "输入错误", str(e))
            return
        # 发送持续运行指令
        if not self.send_continuous_run_command():
            return
        # 启动定时器
        self.remaining_seconds = int(duration)
        self.timer.start(1000)  # 每秒更新
        self.timer_run_btn.setEnabled(False)
        self.update_status_message()
        # 更新按钮状态
        self.timer_run_btn.setEnabled(False)
        self.timer_pause_btn.setEnabled(True)
        self.timer_cancel_btn.setEnabled(True)
        self.timer_resume_btn.setEnabled(False)
        self.is_paused = False

    def send_continuous_run_command(self):
        # 生成持续运行指令（例如：XEFV100JG YEFV200JG）
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
        # 发送急停指令（示例指令，需根据实际协议调整）
        command = "".join([f"{motor}DFV0J0" for motor in ["X", "Y", "Z", "A"]])
        self.send_command(command + "\r\n")
        self.timer.stop()
        self.is_paused = True
        self.paused_seconds = self.remaining_seconds

        # 更新按钮状态
        self.timer_pause_btn.setEnabled(False)
        self.timer_resume_btn.setEnabled(True)
        self.status_bar.showMessage(f"运行已暂停，剩余时间: {self.format_time(self.paused_seconds)}")

    def resume_timed_run(self):
        if not self.send_continuous_run_command():
            return
        self.remaining_seconds = self.paused_seconds
        self.timer.start(1000)
        self.is_paused = False

        # 更新按钮状态
        self.timer_pause_btn.setEnabled(True)
        self.timer_resume_btn.setEnabled(False)
        self.update_status_message()

    def cancel_timed_run(self):
        self.timer.stop()
        self.send_stop_command()
        self.remaining_seconds = 0
        self.is_paused = False

        # 更新按钮状态
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
        # 发送脱机指令（例如：XDFV0J0 YDFV0J0）
        command = "".join([f"{motor}DFV0J0" for motor in ["X", "Y", "Z", "A"]])
        self.send_command(command + "\r\n")

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
        del_auto_btn = QPushButton("删除")
        del_auto_btn.clicked.connect(lambda: self.delete_preset('auto'))

        # 将控件添加到布局
        hbox.addWidget(QLabel("自动预设:"))
        hbox.addWidget(self.auto_preset_combo)
        hbox.addWidget(load_btn)
        hbox.addWidget(save_btn)
        hbox.addWidget(del_auto_btn)
        layout.addWidget(preset_frame)

        # 步骤表格
        self.steps_table = DragDropTreeWidget()
        self.steps_table.setHeaderLabels(["编号", "名称", "参数配置", "间隔(ms)"])
        self.steps_table.setRootIsDecorated(False)  # 隐藏根节点展开图标
        self.steps_table.setUniformRowHeights(True)  # 统一行高
        self.steps_table.setSortingEnabled(False)  # 禁用排序
        self.steps_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)  # 设置不可编辑
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
            ("复制步骤", self.copy_step),
            ("粘贴步骤", self.paste_step),
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

    def delete_preset(self, preset_type):
        """删除预设的通用方法"""
        combo = self.manual_preset_combo if preset_type == 'manual' else self.auto_preset_combo
        preset_name = combo.currentText()
        if not preset_name:
            QMessageBox.warning(self, "警告", "请先选择要删除的预设")
            return
        # 确认对话框
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除预设 '{preset_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            full_name = f"{preset_type}_{preset_name}"
            if full_name in self.presets:
                del self.presets[full_name]
                PresetManager.save_presets(self.presets)
                self.update_preset_combos()
                self.log(f"预设 '{preset_name}' 已删除")
            else:
                QMessageBox.critical(self, "错误", "找不到指定的预设")

    # 新增步骤复制粘贴功能
    def copy_step(self):
        selected = self.steps_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要复制的步骤")
            return

        item = selected[0]
        step_index = self.steps_table.indexOfTopLevelItem(item)
        if 0 <= step_index < len(self.automation_steps):
            self.copied_step = self.automation_steps[step_index].copy()
            self.log(f"已复制步骤 {step_index + 1}")

    def paste_step(self):
        if not self.copied_step:
            QMessageBox.warning(self, "警告", "请先复制一个步骤")
            return
        # 获取插入位置
        selected = self.steps_table.selectedItems()
        insert_index = len(self.automation_steps)  # 默认插入末尾
        if selected:
            insert_index = self.steps_table.indexOfTopLevelItem(selected[0])
        # 创建新步骤并插入
        new_step = self.copied_step.copy()
        new_step['name'] = f"{new_step.get('name', '步骤')} (副本)"
        self.automation_steps.insert(insert_index, new_step)
        self.update_steps_table()
        self.log(f"已粘贴步骤到位置 {insert_index + 1}")

    def generate_command(self, step_params):
        """生成带校准的指令"""
        command = ""
        self.pending_targets = {m: None for m in ["X", "Y", "Z", "A"]}
        self.expected_rotation = {m: 0 for m in ["X", "Y", "Z", "A"]}  # 记录原始转动量
        direction_map = {"F": 1, "B": -1}

        # 自动模式初始基准设置
        if self.running_mode == "auto" and self.is_first_command:
            for motor in self.active_motors:
                # 优先使用发送前读取的角度
                if self.current_angles[motor] is not None:
                    self.initial_angle_base[motor] = self.current_angles[motor]
                else:
                    # 标记需要等待第一次反馈设置基准
                    self.initial_angle_base[motor] = None

        for motor in ["X", "Y", "Z", "A"]:
            config = step_params.get(motor, {})
            enable = config.get("enable", "D")
            direction = config.get("direction", "F")
            speed = config.get("speed", "0")
            raw_angle = config.get("angle", "0").upper()
            is_continuous = config.get("continuous", False)

            if enable != "E" or motor not in self.active_motors:
                command += f"{motor}DFV0J0"
                continue

            # 方向系数
            dir_factor = direction_map[direction]

            try:
                if is_continuous:
                    # 持续模式处理
                    command += f"{motor}EFV{speed}JG"
                    self.pending_targets[motor] = None
                    continue

                # 记录原始转动量（用于偏差率计算）
                raw_rotation = float(raw_angle)
                self.expected_rotation[motor] = raw_rotation  # 保存原始值

                # 理论角度计算
                if self.running_mode == "auto":
                    # 初始基准尚未设置时（第一条指令且未读取到角度）
                    if self.initial_angle_base[motor] is None:
                        # 使用当前角度作为基准（可能为0，后续收到反馈会更新）
                        base = self.current_angles.get(motor, 0.0)
                        self.initial_angle_base[motor] = base

                    # 累积原始转动量（未校准的）
                    raw_rotation_signed = float(raw_angle) * dir_factor
                    self.accumulated_rotation[motor] += raw_rotation_signed

                    # 校准补偿
                    if self.auto_calibration_enabled:
                        compensation = (self.theoretical_deviations.get(motor) or 0.0) * self.calibration_amplitude
                        calibrated_rotation = raw_rotation_signed - compensation
                    else:
                        calibrated_rotation = raw_rotation_signed

                    # 实际发送的转动量
                    actual_rotation = abs(calibrated_rotation)

                    # 更新期望角度
                    self.expected_angles[motor] = (
                            (self.initial_angle_base[motor] +
                             self.accumulated_rotation[motor]) % 360)

                else:  # 手动模式
                    actual_rotation = float(raw_angle)
                    current = self.current_angles.get(motor, 0.0)
                    self.pending_targets[motor] = (current + actual_rotation * dir_factor) % 360

                # 构造指令
                command += f"{motor}E{direction}V{speed}J{actual_rotation:.3f}"

            except (ValueError, TypeError):
                self.log(f"电机{motor}参数错误: 速度='{speed}', 角度='{raw_angle}'")
                command += f"{motor}DFV0J0"

        self.is_first_command = False
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
            if available_ports:
                self.port_combo.setCurrentIndex(0)

    def toggle_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self):
        try:
            port = self.port_combo.currentText()
            baudrate = int(self.baud_combo.currentText())
            if not port:
                raise serial.SerialException("未选择端口")

            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1,
                write_timeout=1
            )
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self.serial_reader = SerialReader(self.serial_port)
            self.serial_reader.data_received.connect(self.handle_serial_data)
            self.serial_reader.start()

            self.connect_btn.setText("关闭串口")
            self.log(f"串口已连接 {port}@{baudrate}")
            self.status_bar.showMessage(f"已连接 {port}@{baudrate}")
        except serial.SerialException as e:
            QMessageBox.critical(self, "串口错误", f"串口连接失败: {e}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"发生未知错误: {e}")

    def close_serial(self):
        with self.serial_lock:  # 加锁保证原子操作
            if hasattr(self, 'serial_reader') and self.serial_reader.isRunning():
                self.serial_reader.stop()
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.serial_port = None
        self.connect_btn.setText("打开串口")
        self.log("串口已关闭")
        self.status_bar.showMessage("串口已关闭")

    def send_manual_command(self):
        params = {}
        active_motors = set()
        self.running_mode = "manual"
        for motor, widgets in self.motor_widgets.items():
            params[motor] = {
                "enable": "E" if widgets["enable"].isChecked() else "D",
                "direction": "F" if widgets["direction"].checkedButton().text() == "正转" else "B",
                "speed": widgets["speed"].text(),
                "angle": widgets["angle"].text().upper(),
                "continuous": widgets["continuous"].isChecked()
            }
            if params[motor]["enable"] == "E":
                active_motors.add(motor)
            # 验证输入
            try:
                if params[motor]["speed"]: float(params[motor]["speed"])
                if params[motor]["angle"] and params[motor]["angle"] != "G": float(params[motor]["angle"])
            except ValueError:
                QMessageBox.critical(self, "输入错误", f"电机 {motor} 的速度或角度值无效")
                return

        self.active_motors = active_motors
        command = self.generate_command(params)
        if self.send_command(command):
            self.status_bar.showMessage("手动指令已发送")

    def send_command(self, command):
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.critical(self, "错误", "请先打开串口连接！")
            return False
        try:
            with self.serial_lock:
                self.serial_port.write(command.encode('utf-8'))
            self.log(f"已发送指令: {command.strip()}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "发送错误", str(e))
            self.close_serial()
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

            if not self.serial_port or not self.serial_port.is_open:
                QMessageBox.critical(self, "错误", "串口未连接")
                return

            try:
                self.loop_count = max(0, int(self.loop_entry.text()))
            except ValueError:
                QMessageBox.critical(self, "错误", "无效的循环次数")
                return

            self.running_mode = "auto"
            self.is_first_command = True
            for motor in ["X", "Y", "Z", "A"]:
                self.initial_angle_base[motor] = self.current_angles.get(motor)
                self.accumulated_rotation[motor] = 0.0

            self.automation_thread = AutomationThread(self, self.automation_steps, self.loop_count, self.serial_port)
            self.automation_thread.update_status.connect(self.status_bar.showMessage)
            self.automation_thread.error_occurred.connect(self.handle_automation_error)
            self.automation_thread.finished.connect(self._on_automation_finished)
            self.automation_thread.start()
            self.log("自动化任务安全启动")

    def _on_automation_finished(self):
        if self.automation_thread is not None:
            try:
                self.automation_thread.update_status.disconnect()
                self.automation_thread.error_occurred.disconnect()
                self.automation_thread.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.automation_thread = None
        self.status_bar.showMessage("自动化运行已完成")
        self.log("自动化任务已完成")

    def handle_automation_error(self, message):
        self.stop_automation()
        QMessageBox.critical(self, "运行错误", message)
        self.log(f"错误: {message}")

    def stop_automation(self):
        if self.automation_thread and self.automation_thread.isRunning():
            self.automation_thread.safe_stop()
        self.automation_thread = None
        self.running = False
        self.log("自动化运行已停止")
        self.status_bar.showMessage("自动化运行已停止")

    def update_steps_table(self):
        scroll_pos = self.steps_table.verticalScrollBar().value()
        self.steps_table.clear()
        for step in self.automation_steps:
            self._add_step_to_table(step)
        self.steps_table.verticalScrollBar().setValue(scroll_pos)

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
        preset_name, ok = QInputDialog.getText(self, "保存手动预设", "输入预设名称:")
        if not (ok and preset_name.strip()): return
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
        self.log(f"手动预设 '{preset_name}' 已保存")

    def load_manual_preset(self):
        name = self.manual_preset_combo.currentText()
        if not name: return
        preset_data = self.presets.get(f"manual_{name}")
        if preset_data:
            for motor, params in preset_data.items():
                if motor in self.motor_widgets:
                    widgets = self.motor_widgets[motor]
                    widgets["enable"].setChecked(params.get("enable") == "E")
                    if params.get("direction") == "F":
                        widgets["direction"].buttons()[0].setChecked(True)
                    else:
                        widgets["direction"].buttons()[1].setChecked(True)
                    widgets["speed"].setText(params.get("speed", ""))
                    widgets["angle"].setText(params.get("angle", ""))
                    widgets["continuous"].setChecked(params.get("continuous", False))
            self.log(f"已加载手动预设 '{name}'")

    def save_auto_preset(self):
        preset_name, ok = QInputDialog.getText(self, "保存自动预设", "输入预设名称:")
        if not (ok and preset_name.strip()): return
        preset_data = {
            "steps": [s.copy() for s in self.automation_steps],
            "loop_count": self.loop_entry.text()
        }
        self.presets[f"auto_{preset_name}"] = preset_data
        PresetManager.save_presets(self.presets)
        self.update_preset_combos()
        self.log(f"自动预设 '{preset_name}' 已保存")

    def load_auto_preset(self):
        preset_name = self.auto_preset_combo.currentText()
        if not preset_name: return
        preset_data = self.presets.get(f"auto_{preset_name}")
        if preset_data:
            self.automation_steps = [step.copy() for step in preset_data.get("steps", [])]
            self.loop_entry.setText(str(preset_data.get("loop_count", 1)))
            self.update_steps_table()
            self.log(f"已加载自动预设 '{preset_name}'")

    def update_preset_combos(self):
        manual_presets = [k[7:] for k in self.presets if k.startswith("manual_")]
        self.manual_preset_combo.clear()
        self.manual_preset_combo.addItems(sorted(manual_presets))

        auto_presets = [k[5:] for k in self.presets if k.startswith("auto_")]
        self.auto_preset_combo.clear()
        self.auto_preset_combo.addItems(sorted(auto_presets))

    def log(self, message):
        self.log_signal.emit(message)

    def _log_impl(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.moveCursor(QTextCursor.End)

    def clear_log(self):
        self.log_text.clear()

    def closeEvent(self, event):
        # 统一的关闭清理
        self.stop_automation()
        if NIDAQMX_AVAILABLE:
            self._spectro_stop_measurement()
        self.close_serial()

        if platform.system() == 'Windows':
            windll.winmm.timeEndPeriod(1)

        event.accept()


if __name__ == "__main__":
    if os.name == 'nt':
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(':/meow.ico'))
    app.setStyleSheet(MACOS_STYLE)

    window = MotorControlApp()
    window.show()

    sys.exit(app.exec())