"""
主窗口
"""

import os
import sys

# 路径设置
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import csv

# 标准库
import ctypes
import json
import math
import platform
import re
import threading
import time
import traceback
import weakref
from collections import deque
from datetime import datetime

import numpy as np
import serial

# Windows特定导入
if platform.system() == "Windows":
    from ctypes import windll

# 可选依赖
try:
    import nidaqmx
    import pyqtgraph as pg
    from nidaqmx.constants import TerminalConfiguration

    NIDAQMX_AVAILABLE = True
except ImportError:
    NIDAQMX_AVAILABLE = False
    nidaqmx = None
    pg = None

from PySide6.QtCharts import QChartView
from PySide6.QtCore import QMargins, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDoubleValidator,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# PySide6
from serial.tools import list_ports

# 导入重构后的组件
from src.config.constants import MACOS_STYLE
from src.config.settings import SettingsManager
from src.core.automation_engine import AutomationThread
from src.core.pid_analyzer import PIDAnalyzer, PIDStatus
from src.core.pid_optimizer import PatternSearchOptimizer, PIDParams, TestResult
from src.hardware.daq_thread import DAQThread
from src.hardware.serial_reader import SerialReader
from src.ui.dialogs.motor_step_config import MotorStepConfig

# 导入 Mixin 模块
from src.ui.mixins import (
    AnalysisMixin,
    AutomationMixin,
    DataExportMixin,
    ManualMixin,
    PIDDataMixin,
    PositionMixin,
    SerialMixin,
    SettingsMixin,
    SpectroMixin,
)
from src.ui.widgets import (
    AnalysisChart,
    DragDropTreeWidget,
    IOSSwitch,
    MotorCircle,
    PIDAnalysisChart,
    PIDOptimizerPanel,
    PIDStatsPanel,
)


class MotorControlApp(
    SpectroMixin, PositionMixin, AnalysisMixin, AutomationMixin, ManualMixin,
    SerialMixin, DataExportMixin, SettingsMixin, PIDDataMixin, QMainWindow
):
    """
    主窗口类 - 使用 Mixin 模式组织功能模块

    继承结构:
    - SpectroMixin: 光谱仪控制功能
    - PositionMixin: 位置监控和零点标定功能
    - AnalysisMixin: PID分析功能
    - AutomationMixin: 自动化控制功能
    - ManualMixin: 手动控制功能
    - SerialMixin: 串口通信功能
    - DataExportMixin: 数据导出功能
    - SettingsMixin: 设置管理功能
    - PIDDataMixin: PID数据处理功能
    - QMainWindow: Qt主窗口基类
    """


    log_signal = Signal(str)
    angle_update = Signal(dict)

    def __init__(self):
        super().__init__()

        # 设置文件路径
        self.settings_file = "data/settings.json"

        # 初始化设置管理器
        self.settings_manager = SettingsManager(self.settings_file)
        self.settings_manager.load()

        # 初始化光谱仪相关变量
        if not NIDAQMX_AVAILABLE:
            QMessageBox.critical(
                self,
                "依赖库缺失",
                "未找到 nidaqmx 或 pyqtgraph 库。\n请运行 'pip install nidaqmx pyqtgraph scipy' 进行安装。\n光谱仪功能将不可用。",
            )

        self._spectro_init_vars()

        # 初始化基础属性
        # 日志信号连接
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
        
        from src.core.preset_manager import PresetManager as PM

        self._preset_manager = PM()
        self.presets = self._preset_manager.presets
        self.automation_thread = None
        self.log_signal.connect(self._log_impl)
        self.init_ui()
        self.update_preset_combos()
        self.setStyleSheet(MACOS_STYLE)
        self.setMinimumSize(1280, 960)
        self.resize(1280, 960)
        try:
            self.setWindowIcon(QIcon("resources/icons/meow.ico"))
        except:
            pass
        self.angle_update.connect(self.update_angles)
        self.expected_changes = {}  # 记录每个电机理论转动角度
        self.last_angles = {}  # 记录上一次接收到的角度
        self.current_angles = {"X": 0, "Y": 0, "Z": 0, "A": 0}  # 添加当前角度记录
        self.angle_offsets = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}  # 零点偏移量
        self.raw_angles = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}  # 原始物理角度
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
        self.calibration_amplitude = 0.5  # 保留兼容性
        self.pid_precision = 0.5  # PID 精确控制目标阈值（度）
        self.calibration_in_progress = False  # PID 校准进行中标志

        # PID 分析器和定时器
        self.pid_analyzer = PIDAnalyzer(max_history=100)
        self.pid_update_timer = QTimer()
        self.pid_update_timer.timeout.connect(self._update_pid_analysis_display)
        self.pid_update_timer.setInterval(200)  # 200ms 更新一次显示

        # 关闭标志和数据包缓冲
        self._closing = False  # 关闭标志，防止信号处理
        self._pending_pid_packets = []  # PID数据包缓冲
        self._chart_update_timer = QTimer()
        self._chart_update_timer.timeout.connect(self._batch_update_charts)
        self._chart_update_timer.setInterval(50)  # 20Hz 批量更新图表

        # 加载用户设置
        self.load_settings()

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
        control_group = QGroupBox("泵送控制")
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

        # ================= 微泵状态 =================
        self.motor_status_group = QGroupBox("泵体状态")
        self.motor_status_group.setFont(QFont("Microsoft YaHei", 13))
        motor_status_layout = QVBoxLayout(self.motor_status_group)

        self.position_btn = QPushButton("转子监控")
        self.position_btn.setCheckable(True)
        self.analysis_btn = QPushButton("运行分析")
        self.analysis_btn.setCheckable(True)

        for btn in [self.position_btn, self.analysis_btn]:
            btn.setFont(QFont("Microsoft YaHei", 13))
            btn.setFixedHeight(40)
            motor_status_layout.addWidget(btn)

        self.nav_layout.addWidget(self.motor_status_group)

        # ================= 光谱仪控制 =================
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
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
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

        # ================= 自动校准开关 =================
        self.add_auto_calibration_switch()

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
        self.spectro_btn.clicked.connect(lambda: self.switch_tab(4))  

        self.connect_btn.clicked.connect(self.toggle_serial)
        refresh_btn.clicked.connect(self.refresh_serial_ports)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 初始刷新光谱仪设备
        if NIDAQMX_AVAILABLE:
            self._spectro_refresh_devices()



    def add_auto_calibration_switch(self):
        """在左侧导航栏添加 PID 精确控制开关和目标阈值输入"""
        auto_cal_group = QGroupBox("PID精确控制")
        auto_cal_group.setFont(QFont("Microsoft YaHei", 13))
        auto_cal_layout = QVBoxLayout(auto_cal_group)
        # 开关布局
        switch_frame = QFrame()
        hbox = QHBoxLayout(switch_frame)
        auto_cal_label = QLabel("PID模式:")
        self.auto_cal_switch = IOSSwitch()
        hbox.addWidget(auto_cal_label)
        hbox.addWidget(self.auto_cal_switch)
        auto_cal_layout.addWidget(switch_frame)
        # 目标阈值输入框
        amplitude_frame = QFrame()
        hbox_amp = QHBoxLayout(amplitude_frame)
        amp_label = QLabel("目标阈值：")
        self.calibration_amp_input = QLineEdit()
        self.calibration_amp_input.setFixedWidth(80)
        self.calibration_amp_input.setText("0.5")
        self.calibration_amp_input.setValidator(
            QDoubleValidator(0.05, 2.0, 2)
        )  # 限制输入范围0.1-5度
        # 添加单位标签
        unit_label = QLabel("°")
        hbox_amp.addWidget(amp_label)
        hbox_amp.addWidget(self.calibration_amp_input)
        hbox_amp.addWidget(unit_label)
        auto_cal_layout.addWidget(amplitude_frame)
        # 信号连接
        self.auto_cal_switch.stateChanged.connect(self.toggle_auto_calibration)
        self.calibration_amp_input.textChanged.connect(self.update_pid_precision)
        self.nav_layout.insertWidget(3, auto_cal_group)

    def update_pid_precision(self):
        """更新 PID 目标阈值"""
        try:
            value = float(self.calibration_amp_input.text())
            if 0.05 <= value <= 2.0:
                self.pid_precision = value
                self.calibration_amplitude = value
            else:
                raise ValueError("超出范围")
        except ValueError:
            self.log("目标阈值无效，已重置为0.5°")
            self.calibration_amp_input.setText("0.5")
            self.pid_precision = 0.5
            self.calibration_amplitude = 0.5

    def toggle_auto_calibration(self, state):
        self.auto_calibration_enabled = state
        mode = "PID精确控制" if state else "传统开环"
        self.log(f"已切换至{mode}模式")

    def switch_tab(self, index):
        self.tab_widget.setCurrentIndex(index)
        # 更新导航按钮的选中状态
        buttons = [
            self.manual_btn,
            self.auto_btn,
            self.position_btn,
            self.analysis_btn,
            self.spectro_btn,
        ]
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)

    def update_angles(self, data):
        """更新角度显示"""
        try:
            if getattr(self, "_closing", False):
                return

            # 更新所有电机的圆形动画和角度标签
            for motor in ["X", "Y", "Z", "A"]:
                current_angle = data["current"].get(motor, 0)
                self.motors[motor].set_angle(current_angle % 360)
                self.angle_labels[motor].setText(f"{current_angle:.3f}°")

            # 节流：每100ms更新一次图表
            current_time = time.time()
            if not hasattr(self, "_last_chart_update_time"):
                self._last_chart_update_time = 0

            if current_time - self._last_chart_update_time >= 0.1:
                self._last_chart_update_time = current_time
                try:
                    self.chart_view.chart().update_data(data)
                except Exception:
                    pass
        except Exception as e:
            print(f"角度更新异常: {str(e)}")

    def _create_centered_item(self, text):
        """创建居中显示的表格项"""
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def handle_serial_data(self, data: str):
        """
        处理串口文本数据

        Args:
            data: 接收到的文本数据行
        """
        # PID测试相关消息处理
        if data.startswith("PIDTEST_"):
            self._handle_pid_test_message(data)
            return

        # PID配置确认
        if data.startswith("PIDCFG_"):
            self.log(f"PID配置: {data}")
            return

        # PID参数查询响应
        if data.startswith("PIDPARAM:"):
            self.log(f"当前PID参数: {data}")
            return

        # 角度流控制响应
        if data.startswith("ANGLESTREAM_"):
            self.log(f"角度流: {data}")
            return

        # 校准相关消息
        if data.startswith("CAL"):
            self.handle_calibration_message(data)
            return

        # PID定位模式消息
        if data.startswith("PID_"):
            self.handle_pid_message(data)
            return

        # 下位机忙碌状态
        if data.startswith("BUSY"):
            self.log(f"下位机: {data}")
            return

        # 流模式状态（兼容旧版）
        if data.startswith("STREAM"):
            self.log(f"流模式: {data}")
            return

        # 电机状态消息（调试用）
        if data.startswith("Motor"):
            self.log(f"电机: {data}")
            return

        # 其他消息记录
        self.log(f"接收: {data}")

    def _handle_pid_test_message(self, data: str):
        """
        处理PID测试相关的文本消息

        Args:
            data: PID测试消息
        """
        if data.startswith("PIDTEST_START:"):
            # 测试开始
            self.log(f"[PID测试] 开始: {data}")

        elif data.startswith("PIDTEST_RUN:"):
            # 测试轮次
            run_index = data.split(":")[1] if ":" in data else "?"
            self.log(f"[PID测试] 执行轮次 {run_index}")

        elif data.startswith("PIDTEST_RESULT:"):
            # 文本格式测试结果（作为备份，主要使用二进制包）
            self.log(f"[PID测试] 结果: {data}")

        elif data.startswith("PIDTEST_DONE:"):
            # 测试完成
            motor = data.split(":")[1] if ":" in data else "?"
            self.log(f"[PID测试] 完成: 电机 {motor}")

            # 通知优化器测试完成
            if hasattr(self, "pid_optimizer") and self.pid_optimizer:
                self.pid_optimizer.on_test_done()

            # 单次测试完成
            if getattr(self, "_single_test_active", False):
                self._single_test_active = False
                self.pid_optimizer_panel.on_single_test_complete()

        elif data.startswith("PIDTEST_STOPPED"):
            # 测试被停止
            self.log("[PID测试] 已停止")

            # 如果单次测试被停止
            if getattr(self, "_single_test_active", False):
                self._single_test_active = False
                self.pid_optimizer_panel.on_single_test_complete()

        elif data.startswith("PIDTEST_ERR:"):
            # 测试错误
            error = data.split(":")[1] if ":" in data else "未知错误"
            self.log(f"[PID测试] 错误: {error}")

    def update_stats_panel(self, data):
        """更新统计面板（兼容旧版调用）- 已优化，不再直接更新图表"""
        # 图表更新已移至节流机制，此处不再调用
        pass

    def _set_stat_na(self, motor):
        """设置未启用电机的统计显示"""
        labels = self.stats_widgets[motor]
        for key in labels.keys():
            labels[key].setText("--")
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
        for label_key in labels.keys():
            labels[label_key].setStyleSheet(f"color: {color};")

    def set_size_policy(self, h_policy, v_policy):
        """通用尺寸策略设置方法"""
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QGroupBox, QFrame)):
                widget.setSizePolicy(
                    QSizePolicy(h_policy, v_policy, QSizePolicy.ControlType.DefaultType)
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
        if hasattr(self, "steps_table"):
            total_width = self.steps_table.width()
            column_count = self.steps_table.columnCount()
            if column_count > 0:
                ratio = [0.1, 0.15, 0.6, 0.15]
                for i in range(column_count):
                    self.steps_table.setColumnWidth(i, int(total_width * ratio[i]))

    def _add_step_to_table(self, step: dict) -> None:
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
            params_str = " | ".join(params_desc) if params_desc else "所有微泵脱机"
            interval_ms = step.get("interval", 0)
            name = step.get("name", f"步骤 {idx}")

            # 创建表格项
            item = QTreeWidgetItem([str(idx), name, params_str, f"{interval_ms / 1000.0:.1f}"])
            item.setData(0, Qt.UserRole, step)

            # 确保属性设置
            for i in range(self.steps_table.columnCount()):
                item.setTextAlignment(i, Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)  # 禁止作为拖放目标

            self.steps_table.addTopLevelItem(item)

        except Exception as e:
            self.log(f"步骤添加错误: {str(e)}")

    def generate_command(self, step_params):
        """生成带校准的指令（优化版：支持 PID 闭环模式）"""
        command = ""
        command_active_motors = set()
        self.pending_targets = {m: None for m in ["X", "Y", "Z", "A"]}
        self.expected_rotation = {m: 0 for m in ["X", "Y", "Z", "A"]}
        direction_map = {"F": 1, "B": -1}

        # 自动模式初始基准设置 (逻辑保持不变)
        if self.running_mode == "auto" and self.is_first_command:
            for motor in self.active_motors:
                if self.current_angles[motor] is not None:
                    self.initial_angle_base[motor] = self.current_angles[motor]
                else:
                    self.initial_angle_base[motor] = None

        for motor in ["X", "Y", "Z", "A"]:
            config = step_params.get(motor, {})
            enable = config.get("enable", "D")

            # 核心修改：如果电机未启用，则直接跳过，不生成任何指令
            if enable != "E":
                continue

            # 如果程序执行到这里，说明电机已启用
            command_active_motors.add(motor)

            direction = config.get("direction", "F")
            speed = config.get("speed", "0")
            raw_angle = config.get("angle", "0").upper()
            is_continuous = config.get("continuous", False)
            dir_factor = direction_map[direction]

            try:
                # 连续转动模式：始终使用传统开环指令
                if is_continuous:
                    command += f"{motor}E{direction}V{speed}JG"
                    self.pending_targets[motor] = None
                    continue

                raw_rotation = float(raw_angle)
                self.expected_rotation[motor] = raw_rotation

                # ===== PID 精确控制模式 =====
                # 条件：自动校准开启 且 非连续模式
                if self.auto_calibration_enabled and not is_continuous:
                    precision = getattr(self, "pid_precision", 0.1)

                    # 累积旋转量用于上位机跟踪（可选）
                    if self.running_mode == "auto":
                        if self.initial_angle_base[motor] is None:
                            current = self.current_angles.get(motor, 0.0)
                            self.initial_angle_base[motor] = current
                        self.accumulated_rotation[motor] += raw_rotation * dir_factor
                        self.expected_angles[motor] = (
                            self.initial_angle_base[motor] + self.accumulated_rotation[motor]
                        ) % 360
                    else:
                        current = self.current_angles.get(motor, 0.0)
                        self.pending_targets[motor] = (current + raw_rotation * dir_factor) % 360

                    # 生成 R 指令: XEFR360P0.1 (相对增量，方向由 F/B 决定)
                    command += f"{motor}E{direction}R{raw_rotation:.1f}P{precision}"

                    continue

                # ===== 传统开环模式 =====
                if self.running_mode == "auto":
                    if self.initial_angle_base[motor] is None:
                        base = self.current_angles.get(motor, 0.0)
                        self.initial_angle_base[motor] = base

                    raw_rotation_signed = float(raw_angle) * dir_factor
                    self.accumulated_rotation[motor] += raw_rotation_signed

                    # 传统自动校准补偿（当 PID 模式关闭时）
                    calibrated_rotation = raw_rotation_signed

                    actual_rotation = abs(calibrated_rotation)
                    self.expected_angles[motor] = (
                        self.initial_angle_base[motor] + self.accumulated_rotation[motor]
                    ) % 360

                else:  # 手动模式
                    actual_rotation = float(raw_angle)
                    current = self.current_angles.get(motor, 0.0)
                    self.pending_targets[motor] = (current + actual_rotation * dir_factor) % 360

                # 将当前启用电机的指令拼接到总指令字符串中
                command += f"{motor}E{direction}V{speed}J{actual_rotation:.3f}"

            except (ValueError, TypeError):
                self.log(f"电机{motor}参数错误，已跳过: 速度='{speed}', 角度='{raw_angle}'")
                # 如果参数解析错误，则记录日志并跳过此电机，不影响其他电机
                continue

        # 更新活动电机状态，并附加结束符
        self.active_motors = command_active_motors
        self.is_first_command = False

        # 只有在至少一个电机被启用时才添加回车换行符
        if command:
            return command + "\r\n"
        return ""  # 如果没有启用的电机，则返回空字符串，不发送任何指令

    def log(self, message):
        self.log_signal.emit(message)

    def _log_impl(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.moveCursor(QTextCursor.End)

    def clear_log(self):
        self.log_text.clear()

    def closeEvent(self, event):
        # 设置关闭标志，阻止所有信号处理
        self._closing = True

        # 保存设置
        try:
            self.save_settings()
        except Exception:
            pass

        # 停止所有定时器
        try:
            if hasattr(self, "_chart_update_timer"):
                self._chart_update_timer.stop()
            if hasattr(self, "pid_update_timer"):
                self.pid_update_timer.stop()
            if hasattr(self, "resize_timer"):
                self.resize_timer.stop()
            if hasattr(self, "spectro_timer"):
                self.spectro_timer.stop()
        except (RuntimeError, AttributeError):
            pass

        # 清空数据缓冲区
        if hasattr(self, "_pending_pid_packets"):
            self._pending_pid_packets.clear()

        # 统一的关闭清理
        try:
            self.stop_automation()
        except Exception:
            pass

        if NIDAQMX_AVAILABLE:
            try:
                self._spectro_stop_measurement()
            except Exception:
                pass

        try:
            self.close_serial()
        except Exception:
            pass

        if platform.system() == "Windows":
            try:
                windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        event.accept()

    # ============= 零点标定功能已迁移至 PositionMixin =============
    # ============= 微泵备注功能已迁移至 PositionMixin =============
