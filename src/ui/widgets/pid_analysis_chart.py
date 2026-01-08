"""
PID 控制分析图表组件
2x2 布局: 位置追踪、输出曲线、误差曲线、负载曲线
"""

from collections import deque
from typing import Dict, List, Optional, Tuple

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    PlotWidget = object

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# 电机颜色配置
MOTOR_COLORS = {
    "X": "#1f77b4",  # 蓝色
    "Y": "#2ca02c",  # 绿色
    "Z": "#d62728",  # 红色
    "A": "#9467bd",  # 紫色
}

# 位置追踪线型
POSITION_STYLES = {
    "target": {"color": "#ff7f0e", "width": 2, "style": Qt.DashLine},  # 橙色虚线-目标
    "actual": {"color": "#1f77b4", "width": 2, "style": Qt.SolidLine},  # 蓝色实线-实际
    "theo": {"color": "#2ca02c", "width": 1, "style": Qt.DotLine},  # 绿色点线-理论
}


class PIDAnalysisChart(QWidget):
    """PID 控制分析图表 - 2x2 布局"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_points = 500

        # 相对角度计算所需的初始状态
        self.initial_angles: Dict[str, Optional[float]] = {
            motor: None for motor in ["X", "Y", "Z", "A"]
        }
        self.target_rotations: Dict[str, Optional[float]] = {
            motor: None for motor in ["X", "Y", "Z", "A"]
        }

        # 数据存储 (现在存储相对角度)
        self.position_data: Dict[str, deque] = {
            motor: deque(maxlen=self.max_points) for motor in ["X", "Y", "Z", "A"]
        }
        self.output_data: Dict[str, deque] = {
            motor: deque(maxlen=self.max_points) for motor in ["X", "Y", "Z", "A"]
        }
        self.error_data: Dict[str, deque] = {
            motor: deque(maxlen=self.max_points) for motor in ["X", "Y", "Z", "A"]
        }
        self.load_data: Dict[str, deque] = {
            motor: deque(maxlen=self.max_points) for motor in ["X", "Y", "Z", "A"]
        }

        # 曲线引用
        self.position_curves: Dict[str, Dict[str, object]] = {}
        self.output_curves: Dict[str, object] = {}
        self.error_curves: Dict[str, object] = {}
        self.load_curves: Dict[str, object] = {}

        self._init_ui()

    def _init_ui(self):
        """初始化 UI - 2x2 网格布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("图表功能不可用，请安装 pyqtgraph 库")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            return

        # 2x2 网格布局
        grid = QGridLayout()
        grid.setSpacing(8)

        # 1. 位置追踪图 (左上) - 使用相对角度
        position_group = QGroupBox("位置追踪 (相对转动量)")
        position_group.setFont(QFont("Microsoft YaHei", 10))
        position_layout = QVBoxLayout(position_group)
        position_layout.setContentsMargins(3, 3, 3, 3)

        self.position_plot = pg.PlotWidget()
        self._setup_plot(self.position_plot, "转动量", "°", "时间", "s")
        self.position_plot.addLegend(offset=(10, 10))

        # 为每个电机创建三条曲线 (目标、实际、理论)
        for motor in ["X", "Y", "Z", "A"]:
            self.position_curves[motor] = {}
            # 只为第一个电机添加图例
            show_legend = motor == "X"

            # 目标角度曲线
            self.position_curves[motor]["target"] = self.position_plot.plot(
                pen=pg.mkPen(
                    color=POSITION_STYLES["target"]["color"],
                    width=POSITION_STYLES["target"]["width"],
                    style=POSITION_STYLES["target"]["style"],
                ),
                name="目标" if show_legend else None,
            )
            # 实际角度曲线
            self.position_curves[motor]["actual"] = self.position_plot.plot(
                pen=pg.mkPen(color=MOTOR_COLORS[motor], width=2),
                name=f"实际({motor})" if show_legend else None,
            )
            # 理论角度曲线
            self.position_curves[motor]["theo"] = self.position_plot.plot(
                pen=pg.mkPen(
                    color=POSITION_STYLES["theo"]["color"],
                    width=POSITION_STYLES["theo"]["width"],
                    style=POSITION_STYLES["theo"]["style"],
                ),
                name="理论" if show_legend else None,
            )

        position_layout.addWidget(self.position_plot)
        grid.addWidget(position_group, 0, 0)

        # 2. 输出曲线图 (右上)
        output_group = QGroupBox("PID 输出 (RPM)")
        output_group.setFont(QFont("Microsoft YaHei", 10))
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(3, 3, 3, 3)

        self.output_plot = pg.PlotWidget()
        self._setup_plot(self.output_plot, "RPM", "", "时间", "s")

        for motor, color in MOTOR_COLORS.items():
            self.output_curves[motor] = self.output_plot.plot(
                pen=pg.mkPen(color=color, width=2), name=f"微泵 {motor}"
            )

        output_layout.addWidget(self.output_plot)
        grid.addWidget(output_group, 0, 1)

        # 3. 误差曲线图 (左下)
        error_group = QGroupBox("PID 误差")
        error_group.setFont(QFont("Microsoft YaHei", 10))
        error_layout = QVBoxLayout(error_group)
        error_layout.setContentsMargins(3, 3, 3, 3)

        self.error_plot = pg.PlotWidget()
        self._setup_plot(self.error_plot, "误差", "°", "时间", "s")

        # 添加零线
        zero_line = pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen(color="#888888", width=1, style=Qt.DashLine)
        )
        self.error_plot.addItem(zero_line)

        for motor, color in MOTOR_COLORS.items():
            self.error_curves[motor] = self.error_plot.plot(
                pen=pg.mkPen(color=color, width=2), name=f"微泵 {motor}"
            )

        error_layout.addWidget(self.error_plot)
        grid.addWidget(error_group, 1, 0)

        # 4. 负载曲线图 (右下)
        load_group = QGroupBox("负载偏差 (理论-实际)")
        load_group.setFont(QFont("Microsoft YaHei", 10))
        load_layout = QVBoxLayout(load_group)
        load_layout.setContentsMargins(3, 3, 3, 3)

        self.load_plot = pg.PlotWidget()
        self._setup_plot(self.load_plot, "偏差", "°", "时间", "s")

        # 添加零线
        zero_line2 = pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen(color="#888888", width=1, style=Qt.DashLine)
        )
        self.load_plot.addItem(zero_line2)

        for motor, color in MOTOR_COLORS.items():
            self.load_curves[motor] = self.load_plot.plot(
                pen=pg.mkPen(color=color, width=2), name=f"微泵 {motor}"
            )

        load_layout.addWidget(self.load_plot)
        grid.addWidget(load_group, 1, 1)

        layout.addLayout(grid)

    def _setup_plot(self, plot, y_label: str, y_unit: str, x_label: str, x_unit: str):
        """设置图表通用属性"""
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setLabel("left", y_label, units=y_unit)
        plot.setLabel("bottom", x_label, units=x_unit)
        plot.setMinimumHeight(150)

    def update_from_packet(self, motor: str, packet: dict, relative_time: float):
        """从数据包更新所有图表"""
        if not PYQTGRAPH_AVAILABLE:
            return

        try:
            target = packet.get("target_angle", 0)
            actual = packet.get("actual_angle", 0)
            theo = packet.get("theo_angle", 0)
            output = packet.get("pid_out", 0)
            error = packet.get("error", 0)

            # 记录初始角度（第一个数据点）
            if self.initial_angles.get(motor) is None:
                self.initial_angles[motor] = actual
                # 计算目标转动量（处理跨0°点）
                self.target_rotations[motor] = self._normalize_angle_diff(target, actual)

            initial = self.initial_angles[motor]
            target_rotation = self.target_rotations[motor]

            # 计算相对转动量（处理跨0°点）
            relative_actual = self._calc_relative_angle(actual, initial)
            relative_theo = self._calc_relative_angle(theo, initial)

            # 负载偏差
            load = self._normalize_angle_diff(theo, actual)

            # 更新数据 (存储相对角度)
            if motor in self.position_data:
                self.position_data[motor].append(
                    (relative_time, target_rotation, relative_actual, relative_theo)
                )
            if motor in self.output_data:
                self.output_data[motor].append((relative_time, output))
            if motor in self.error_data:
                self.error_data[motor].append((relative_time, error))
            if motor in self.load_data:
                self.load_data[motor].append((relative_time, load))

            # 刷新曲线
            self._refresh_position_curve(motor)
            self._refresh_output_curve(motor)
            self._refresh_error_curve(motor)
            self._refresh_load_curve(motor)
        except Exception as e:
            print(f"Chart update error: {e}")

    @staticmethod
    def _normalize_angle_diff(angle1: float, angle2: float) -> float:
        """计算两个角度的差值，处理360°跨越"""
        diff = angle1 - angle2
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        return diff

    def _calc_relative_angle(self, current: float, initial: float) -> float:
        """计算相对于初始角度的转动量，处理跨0°点

        使用累积方式处理多圈转动
        """
        return self._normalize_angle_diff(current, initial)

    def add_data_only(self, motor: str, packet: dict, relative_time: float):
        """仅添加数据到缓冲区，不刷新曲线（用于批量更新）"""
        if not PYQTGRAPH_AVAILABLE:
            return

        try:
            target = packet.get("target_angle", 0)
            actual = packet.get("actual_angle", 0)
            theo = packet.get("theo_angle", 0)
            output = packet.get("pid_out", 0)
            error = packet.get("error", 0)

            # 记录初始角度（第一个数据点）
            if self.initial_angles.get(motor) is None:
                self.initial_angles[motor] = actual
                self.target_rotations[motor] = self._normalize_angle_diff(target, actual)

            initial = self.initial_angles[motor]
            target_rotation = self.target_rotations[motor]

            # 计算相对转动量
            relative_actual = self._calc_relative_angle(actual, initial)
            relative_theo = self._calc_relative_angle(theo, initial)

            # 负载偏差
            load = self._normalize_angle_diff(theo, actual)

            # 仅添加数据，不刷新曲线
            if motor in self.position_data:
                self.position_data[motor].append(
                    (relative_time, target_rotation, relative_actual, relative_theo)
                )
            if motor in self.output_data:
                self.output_data[motor].append((relative_time, output))
            if motor in self.error_data:
                self.error_data[motor].append((relative_time, error))
            if motor in self.load_data:
                self.load_data[motor].append((relative_time, load))

            # 标记该电机有数据更新
            if not hasattr(self, "_dirty_motors"):
                self._dirty_motors = set()
            self._dirty_motors.add(motor)
        except Exception as e:
            print(f"add_data_only error: {e}")

    def refresh_all_curves(self):
        """一次性刷新有数据更新的电机曲线"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # 只刷新有数据变化的电机
        dirty_motors = getattr(self, "_dirty_motors", set())
        if not dirty_motors:
            return

        try:
            for motor in dirty_motors:
                self._refresh_position_curve(motor)
                self._refresh_output_curve(motor)
                self._refresh_error_curve(motor)
                self._refresh_load_curve(motor)
        finally:
            # 清空脏标记
            self._dirty_motors = set()

    def _refresh_position_curve(self, motor: str):
        """刷新位置追踪曲线"""
        if motor not in self.position_curves:
            return
        data = self.position_data[motor]
        if not data:
            return
        times = [d[0] for d in data]
        targets = [d[1] for d in data]
        actuals = [d[2] for d in data]
        theos = [d[3] for d in data]

        self.position_curves[motor]["target"].setData(times, targets)
        self.position_curves[motor]["actual"].setData(times, actuals)
        self.position_curves[motor]["theo"].setData(times, theos)

    def _refresh_output_curve(self, motor: str):
        """刷新输出曲线"""
        if motor not in self.output_curves:
            return
        data = self.output_data[motor]
        if data:
            times = [d[0] for d in data]
            outputs = [d[1] for d in data]
            self.output_curves[motor].setData(times, outputs)

    def _refresh_error_curve(self, motor: str):
        """刷新误差曲线"""
        if motor not in self.error_curves:
            return
        data = self.error_data[motor]
        if data:
            times = [d[0] for d in data]
            errors = [d[1] for d in data]
            self.error_curves[motor].setData(times, errors)

    def _refresh_load_curve(self, motor: str):
        """刷新负载曲线"""
        if motor not in self.load_curves:
            return
        data = self.load_data[motor]
        if data:
            times = [d[0] for d in data]
            loads = [d[1] for d in data]
            self.load_curves[motor].setData(times, loads)

    def clear_motor(self, motor: str):
        """清空单个电机数据"""
        # 重置初始角度记录
        if motor in self.initial_angles:
            self.initial_angles[motor] = None
        if motor in self.target_rotations:
            self.target_rotations[motor] = None

        if motor in self.position_data:
            self.position_data[motor].clear()
            if motor in self.position_curves:
                for curve in self.position_curves[motor].values():
                    curve.setData([], [])

        if motor in self.output_data:
            self.output_data[motor].clear()
            if motor in self.output_curves:
                self.output_curves[motor].setData([], [])

        if motor in self.error_data:
            self.error_data[motor].clear()
            if motor in self.error_curves:
                self.error_curves[motor].setData([], [])

        if motor in self.load_data:
            self.load_data[motor].clear()
            if motor in self.load_curves:
                self.load_curves[motor].setData([], [])

    def clear_all(self):
        """清空所有数据"""
        for motor in ["X", "Y", "Z", "A"]:
            self.clear_motor(motor)
        # 重置所有初始角度
        self.initial_angles = {motor: None for motor in ["X", "Y", "Z", "A"]}
        self.target_rotations = {motor: None for motor in ["X", "Y", "Z", "A"]}


class PIDStatsPanel(QWidget):
    """PID 统计面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.motor_panels: Dict[str, Dict[str, QLabel]] = {}

        for motor in ["X", "Y", "Z", "A"]:
            group = QGroupBox(f"微泵 {motor}")
            group.setFont(QFont("Microsoft YaHei", 10))
            group.setStyleSheet(
                f"""
                QGroupBox {{
                    border: 2px solid {MOTOR_COLORS[motor]};
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 5px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    color: {MOTOR_COLORS[motor]};
                }}
            """
            )

            form_layout = QVBoxLayout(group)
            form_layout.setSpacing(3)

            labels = {}

            # 状态
            status_frame = QFrame()
            status_layout = QHBoxLayout(status_frame)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_label = QLabel("状态:")
            status_label.setFont(QFont("Microsoft YaHei", 9))
            status_value = QLabel("空闲")
            status_value.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            status_value.setStyleSheet("color: #888888;")
            status_layout.addWidget(status_label)
            status_layout.addWidget(status_value)
            status_layout.addStretch()
            labels["status"] = status_value
            form_layout.addWidget(status_frame)

            # 当前误差
            error_frame = QFrame()
            error_layout = QHBoxLayout(error_frame)
            error_layout.setContentsMargins(0, 0, 0, 0)
            error_label = QLabel("误差:")
            error_label.setFont(QFont("Microsoft YaHei", 9))
            error_value = QLabel("--")
            error_value.setFont(QFont("Roboto Mono", 10))
            error_layout.addWidget(error_label)
            error_layout.addWidget(error_value)
            error_layout.addStretch()
            labels["error"] = error_value
            form_layout.addWidget(error_frame)

            # 目标角度
            target_frame = QFrame()
            target_layout = QHBoxLayout(target_frame)
            target_layout.setContentsMargins(0, 0, 0, 0)
            target_label = QLabel("目标:")
            target_label.setFont(QFont("Microsoft YaHei", 9))
            target_value = QLabel("--")
            target_value.setFont(QFont("Roboto Mono", 10))
            target_layout.addWidget(target_label)
            target_layout.addWidget(target_value)
            target_layout.addStretch()
            labels["target"] = target_value
            form_layout.addWidget(target_frame)

            # 输出RPM
            output_frame = QFrame()
            output_layout = QHBoxLayout(output_frame)
            output_layout.setContentsMargins(0, 0, 0, 0)
            output_label = QLabel("输出:")
            output_label.setFont(QFont("Microsoft YaHei", 9))
            output_value = QLabel("--")
            output_value.setFont(QFont("Roboto Mono", 10))
            output_layout.addWidget(output_label)
            output_layout.addWidget(output_value)
            output_layout.addStretch()
            labels["output"] = output_value
            form_layout.addWidget(output_frame)

            self.motor_panels[motor] = labels
            layout.addWidget(group)

    def update_status(self, motor: str, status: str, color: str = "#888888"):
        """更新状态显示"""
        if motor in self.motor_panels:
            label = self.motor_panels[motor]["status"]
            label.setText(status)
            label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def update_error(self, motor: str, error: Optional[float]):
        """更新当前误差"""
        if motor in self.motor_panels:
            label = self.motor_panels[motor]["error"]
            if error is not None:
                label.setText(f"{error:.2f}°")
                if abs(error) < 0.5:
                    color = "#2ca02c"
                elif abs(error) < 2.0:
                    color = "#ff7f0e"
                else:
                    color = "#d62728"
                label.setStyleSheet(f"color: {color};")
            else:
                label.setText("--")
                label.setStyleSheet("color: #333333;")

    def update_target(self, motor: str, target: Optional[float]):
        """更新目标角度"""
        if motor in self.motor_panels:
            label = self.motor_panels[motor]["target"]
            if target is not None:
                label.setText(f"{target:.1f}°")
            else:
                label.setText("--")

    def update_output(self, motor: str, output: Optional[float]):
        """更新输出RPM"""
        if motor in self.motor_panels:
            label = self.motor_panels[motor]["output"]
            if output is not None:
                label.setText(f"{output:.1f} RPM")
            else:
                label.setText("--")

    def update_from_packet(self, motor: str, packet: dict):
        """从数据包更新面板"""
        try:
            self.update_status(motor, "运行中", "#2ca02c")
            self.update_error(motor, packet.get("error"))
            self.update_target(motor, packet.get("target_angle"))
            self.update_output(motor, packet.get("pid_out"))
        except Exception as e:
            print(f"Stats panel update error: {e}")

    def reset_motor(self, motor: str):
        """重置单个电机显示"""
        if motor in self.motor_panels:
            self.update_status(motor, "空闲", "#888888")
            self.update_error(motor, None)
            self.update_target(motor, None)
            self.update_output(motor, None)

    def reset_all(self):
        """重置所有显示"""
        for motor in ["X", "Y", "Z", "A"]:
            self.reset_motor(motor)
