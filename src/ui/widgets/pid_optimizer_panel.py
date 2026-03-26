"""
PID参数优化面板 - UI组件
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QDoubleValidator, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.constants import (
    BUTTON_SUCCESS, BUTTON_DANGER, BUTTON_SECONDARY, BUTTON_TERTIARY,
    COLOR_SUCCESS, COLOR_DANGER, COLOR_PRIMARY, COLOR_TEXT_SECONDARY,
)

try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class PIDOptimizerPanel(QWidget):
    """PID参数优化面板"""

    # 信号
    start_optimization = Signal(dict)  # 开始优化，传递配置
    stop_optimization = Signal()  # 停止优化
    pause_optimization = Signal()  # 暂停优化
    resume_optimization = Signal()  # 恢复优化
    apply_params = Signal(dict)  # 应用参数
    single_test = Signal(dict)  # 单次测试，传递配置
    export_data = Signal()  # 导出数据

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._is_running = False

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 主分割器：左右布局
        main_splitter = QSplitter(Qt.Horizontal)
        
        # --- 左侧控制面板 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # 1. 当前参数组
        self._create_params_group(left_layout)
        
        # 2. 优化配置组
        self._create_config_group(left_layout)
        
        # 弹簧
        left_layout.addStretch()
        
        # 3. 控制按钮组 (底部固定)
        self._create_control_group(left_layout)
        
        # 限制左侧宽度
        left_widget.setMinimumWidth(320)
        left_widget.setMaximumWidth(400)
        main_splitter.addWidget(left_widget)
        
        # --- 右侧结果面板 ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self._create_results_group(right_layout)
        
        main_splitter.addWidget(right_widget)
        
        # 设置分割比例：左侧固定，右侧伸缩
        main_splitter.setCollapsible(0, False)
        main_splitter.setStretchFactor(1, 1)
        
        layout.addWidget(main_splitter)

    def _create_params_group(self, parent_layout):
        """创建当前参数组"""
        group = QGroupBox("当前PID参数")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QGridLayout(group)
        layout.setSpacing(8)

        # Kp
        layout.addWidget(QLabel("Kp:"), 0, 0)
        self.kp_input = QDoubleSpinBox()
        self.kp_input.setRange(0.01, 2.0)
        self.kp_input.setDecimals(4)
        self.kp_input.setSingleStep(0.01)
        self.kp_input.setValue(0.14)
        self.kp_input.setToolTip("比例增益 (Proportional)\n控制响应速度，值越大响应越快但可能振荡\n推荐范围: 0.05~0.5")
        layout.addWidget(self.kp_input, 0, 1)

        # Ki
        layout.addWidget(QLabel("Ki:"), 1, 0)
        self.ki_input = QDoubleSpinBox()
        self.ki_input.setRange(0.0, 1.0)
        self.ki_input.setDecimals(5)
        self.ki_input.setSingleStep(0.001)
        self.ki_input.setValue(0.015)
        self.ki_input.setToolTip("积分增益 (Integral)\n消除稳态误差，值过大可能导致积分饱和\n推荐范围: 0.005~0.05")
        layout.addWidget(self.ki_input, 1, 1)

        # Kd
        layout.addWidget(QLabel("Kd:"), 2, 0)
        self.kd_input = QDoubleSpinBox()
        self.kd_input.setRange(0.0, 1.0)
        self.kd_input.setDecimals(4)
        self.kd_input.setSingleStep(0.01)
        self.kd_input.setValue(0.06)
        self.kd_input.setToolTip("微分增益 (Derivative)\n抑制振荡和过冲，对噪声敏感\n推荐范围: 0.02~0.15")
        layout.addWidget(self.kd_input, 2, 1)

        # 应用按钮
        self.apply_btn = QPushButton("应用参数")
        self.apply_btn.clicked.connect(self._on_apply_params)
        layout.addWidget(self.apply_btn, 3, 0, 1, 2)

        parent_layout.addWidget(group)

    def _create_config_group(self, parent_layout):
        """创建优化配置组"""
        group = QGroupBox("优化配置")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QGridLayout(group)
        layout.setSpacing(8)

        # 测试电机
        layout.addWidget(QLabel("测试电机:"), 0, 0)
        self.motor_combo = QComboBox()
        self.motor_combo.addItems(["X", "Y", "Z", "A"])
        layout.addWidget(self.motor_combo, 0, 1)

        # 测试角度
        layout.addWidget(QLabel("测试角度:"), 1, 0)
        self.angle_input = QDoubleSpinBox()
        self.angle_input.setRange(10, 180)
        self.angle_input.setValue(60)
        self.angle_input.setSuffix(" °")
        self.angle_input.setToolTip("每次测试转动的角度增量")
        layout.addWidget(self.angle_input, 1, 1)

        # 转动方向
        layout.addWidget(QLabel("转动方向:"), 2, 0)
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["正转 (F)", "反转 (B)"])
        self.direction_combo.setToolTip("测试时电机的转动方向")
        layout.addWidget(self.direction_combo, 2, 1)

        # 测试次数
        layout.addWidget(QLabel("每轮次数:"), 3, 0)
        self.runs_input = QSpinBox()
        self.runs_input.setRange(1, 20)
        self.runs_input.setValue(5)
        self.runs_input.setToolTip("每轮优化迭代中重复测试的次数\n取均值以减少随机误差")
        layout.addWidget(self.runs_input, 3, 1)

        # 最大迭代
        layout.addWidget(QLabel("最大迭代:"), 4, 0)
        self.max_iter_input = QSpinBox()
        self.max_iter_input.setRange(10, 200)
        self.max_iter_input.setValue(50)
        self.max_iter_input.setToolTip("优化搜索的最大迭代次数\n迭代越多精度越高但耗时越长")
        layout.addWidget(self.max_iter_input, 4, 1)

        # 连接信号以更新时间预估
        self.max_iter_input.valueChanged.connect(self._update_time_estimate)
        self.runs_input.valueChanged.connect(self._update_time_estimate)

        parent_layout.addWidget(group)

    def _create_control_group(self, parent_layout):
        """创建控制按钮组"""
        group = QGroupBox("操作控制")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QGridLayout(group)
        layout.setSpacing(10)

        # L1: 替换emoji为纯文本, H6: 按钮层级
        # 第一行：主要控制
        self.start_btn = QPushButton("开始优化")
        self.start_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet(BUTTON_SUCCESS)
        self.start_btn.setToolTip("开始自动优化PID参数")
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn, 0, 0, 1, 2) # 占据两列

        # 第二行：辅助控制
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setFixedHeight(34)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setStyleSheet(BUTTON_SECONDARY)
        self.pause_btn.clicked.connect(self._on_pause)
        layout.addWidget(self.pause_btn, 1, 0)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedHeight(34)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(BUTTON_DANGER)
        self.stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self.stop_btn, 1, 1)

        # 第三行：调试与应用
        self.single_test_btn = QPushButton("单次测试")
        self.single_test_btn.setFixedHeight(34)
        self.single_test_btn.setToolTip("使用当前PID参数执行一次测试")
        self.single_test_btn.clicked.connect(self._on_single_test)
        layout.addWidget(self.single_test_btn, 2, 0)

        self.apply_best_btn = QPushButton("应用最优")
        self.apply_best_btn.setFixedHeight(34)
        self.apply_best_btn.setEnabled(False)
        self.apply_best_btn.setStyleSheet(BUTTON_SECONDARY)
        self.apply_best_btn.setToolTip("将优化得到的最优参数应用到下位机")
        self.apply_best_btn.clicked.connect(self._on_apply_best)
        layout.addWidget(self.apply_best_btn, 2, 1)

        # 第四行：导出与状态
        self.export_btn = QPushButton("导出数据")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(BUTTON_TERTIARY)
        self.export_btn.clicked.connect(self._on_export)
        layout.addWidget(self.export_btn, 3, 0)

        # 时间预估标签
        self.time_estimate_label = QLabel("预计: --")
        self.time_estimate_label.setFont(QFont("Microsoft YaHei", 9))
        self.time_estimate_label.setAlignment(Qt.AlignCenter)
        self.time_estimate_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(self.time_estimate_label, 3, 1)

        parent_layout.addWidget(group)

    def _create_results_group(self, parent_layout):
        """创建结果显示组"""
        group = QGroupBox("得分曲线")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 15, 10, 10)

        if PYQTGRAPH_AVAILABLE:
            # 评分曲线
            self.score_plot = pg.PlotWidget()
            self.score_plot.setBackground("w")
            self.score_plot.showGrid(x=True, y=True, alpha=0.3)
            self.score_plot.setLabel("left", "得分")
            self.score_plot.setLabel("bottom", "迭代次数")

            self.score_curve = self.score_plot.plot(
                pen=pg.mkPen(color=COLOR_PRIMARY, width=2),
                symbol="o",
                symbolSize=5,
                symbolBrush=COLOR_PRIMARY,
            )
            self.best_score_curve = self.score_plot.plot(
                pen=pg.mkPen(color=COLOR_SUCCESS, width=2, style=Qt.DashLine)
            )
            layout.addWidget(self.score_plot)
        else:
            layout.addWidget(QLabel("图表功能需要 pyqtgraph 库"))

        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels(
            ["#", "Kp", "Ki", "Kd", "原始分", "调整分", "过冲°", "收敛ms", "RSD%"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setMinimumHeight(150)
        self.history_table.setAlternatingRowColors(True)
        layout.addWidget(self.history_table)

        parent_layout.addWidget(group)

    def _set_preset(self, params):
        """设置预设参数"""
        kp, ki, kd = params
        self.kp_input.setValue(kp)
        self.ki_input.setValue(ki)
        self.kd_input.setValue(kd)

    def _on_apply_params(self):
        """应用当前参数"""
        params = {
            "Kp": self.kp_input.value(),
            "Ki": self.ki_input.value(),
            "Kd": self.kd_input.value(),
        }
        self.apply_params.emit(params)

    def _on_start(self):
        """开始优化"""
        config = {
            "initial_params": {
                "Kp": self.kp_input.value(),
                "Ki": self.ki_input.value(),
                "Kd": self.kd_input.value(),
            },
            "test_motor": self.motor_combo.currentText(),
            "test_angle": self.angle_input.value(),
            "test_direction": "F" if self.direction_combo.currentIndex() == 0 else "B",
            "test_runs": self.runs_input.value(),
            "max_iterations": self.max_iter_input.value(),
        }

        self._set_running(True)
        self._clear_history()
        self.start_optimization.emit(config)

    def _on_pause(self):
        """暂停/恢复"""
        if self.pause_btn.text() == "暂停":
            self.pause_btn.setText("继续")
            self.pause_optimization.emit()
        else:
            self.pause_btn.setText("暂停")
            self.resume_optimization.emit()

    def _on_stop(self):
        """停止优化或单次测试"""
        # 如果是单次测试运行中
        if hasattr(self, "_single_test_running") and self._single_test_running:
            self._single_test_running = False
            self.single_test_btn.setEnabled(True)
            self.single_test_btn.setText("单次测试")
            self.stop_btn.setEnabled(False)
            self.status_label.setText("状态: 测试已停止")

        self._set_running(False)
        self.stop_optimization.emit()

    def _on_single_test(self):
        """单次测试当前参数"""
        # 防止重复点击
        if hasattr(self, "_single_test_running") and self._single_test_running:
            return

        self._single_test_running = True
        self.single_test_btn.setEnabled(False)
        self.single_test_btn.setText("测试中...")
        self.stop_btn.setEnabled(True)  # 启用停止按钮
        self.status_label.setText("状态: 单次测试进行中...")

        config = {
            "params": {
                "Kp": self.kp_input.value(),
                "Ki": self.ki_input.value(),
                "Kd": self.kd_input.value(),
            },
            "test_motor": self.motor_combo.currentText(),
            "test_angle": self.angle_input.value(),
            "test_runs": self.runs_input.value(),
            # C2修复：将方向选择传入单次测试配置
            "direction": "F" if self.direction_combo.currentIndex() == 0 else "B",
        }
        self.single_test.emit(config)

    def on_single_test_complete(self):
        """单次测试完成"""
        self._single_test_running = False
        self.single_test_btn.setEnabled(True)
        self.single_test_btn.setText("单次测试")
        self.stop_btn.setEnabled(False)  # 禁用停止按钮
        self.status_label.setText("状态: 单次测试完成")

    def on_single_test_result(self, result: dict):
        """单次测试结果更新"""
        # 更新得分显示
        score = result.get("score", 0)
        self.score_label.setText(f"当前得分: {score:.1f} | 最优得分: --")

        # 添加到历史记录
        record = {
            "index": self.history_table.rowCount(),
            "Kp": result.get("Kp", 0),
            "Ki": result.get("Ki", 0),
            "Kd": result.get("Kd", 0),
            "avg_score": score,
            "runs": result.get("runs", 1),
        }
        self.add_history_record(record)

    def _on_apply_best(self):
        """应用最优参数"""
        # 从标签解析最优参数
        text = self.best_params_label.text()
        if "Kp=" in text:
            try:
                parts = text.replace("最优参数: ", "").split(", ")
                params = {}
                for part in parts:
                    key, value = part.split("=")
                    params[key] = float(value)
                self.apply_params.emit(params)

                # 更新输入框
                self.kp_input.setValue(params.get("Kp", 0.14))
                self.ki_input.setValue(params.get("Ki", 0.015))
                self.kd_input.setValue(params.get("Kd", 0.06))
            except Exception:
                pass

    def _on_export(self):
        """导出优化数据"""
        self.export_data.emit()

    def _set_running(self, running: bool):
        """设置运行状态"""
        self._is_running = running

        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)

        # 禁用配置输入
        self.motor_combo.setEnabled(not running)
        self.angle_input.setEnabled(not running)
        self.runs_input.setEnabled(not running)
        self.max_iter_input.setEnabled(not running)

        if running:
            self.pause_btn.setText("暂停")

    def _clear_history(self):
        """清空历史"""
        self.history_table.setRowCount(0)
        self._score_history = []
        self._best_score_history = []
        self._params_history = {"Kp": [], "Ki": [], "Kd": []}
        if PYQTGRAPH_AVAILABLE:
            self.score_curve.setData([], [])
            self.best_score_curve.setData([], [])
            if hasattr(self, "kp_curve"):
                self.kp_curve.setData([], [])
                self.ki_curve.setData([], [])
                self.kd_curve.setData([], [])

    def _estimate_total_time(self) -> str:
        """预估优化总时间"""
        iterations = self.max_iter_input.value()
        runs_per_iter = self.runs_input.value()
        # 单轮测试约5秒 + 2秒间隔
        single_test_time = 7
        total_seconds = iterations * runs_per_iter * single_test_time

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"预计: {hours}h {minutes}m"
        elif minutes > 0:
            return f"预计: {minutes}m {seconds}s"
        else:
            return f"预计: {seconds}s"

    def _update_time_estimate(self):
        """更新时间预估显示"""
        self.time_estimate_label.setText(self._estimate_total_time())

    # ===== 外部调用的更新方法 =====

    @Slot(int, int, str)
    def update_progress(self, current: int, total: int, message: str):
        """更新进度（已移除进度条UI，仅保留接口兼容）"""
        pass  # 进度条已移除

    @Slot(float, float)
    def update_score(self, current_score: float, best_score: float):
        """更新得分显示"""
        # 更新曲线
        if not hasattr(self, "_score_history"):
            self._score_history = []
            self._best_score_history = []

        self._score_history.append(current_score)
        self._best_score_history.append(best_score)

        if PYQTGRAPH_AVAILABLE:
            x = list(range(len(self._score_history)))
            self.score_curve.setData(x, self._score_history)
            self.best_score_curve.setData(x, self._best_score_history)

    @Slot(dict)
    def update_best_params(self, params: dict):
        """更新最优参数（已移除标签UI，仅保留按钮启用）"""
        self.apply_best_btn.setEnabled(True)

    @Slot(dict)
    def add_history_record(self, record: dict):
        """添加历史记录"""
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)

        self.history_table.setItem(row, 0, QTableWidgetItem(str(record.get("index", row))))
        self.history_table.setItem(row, 1, QTableWidgetItem(f"{record.get('Kp', 0):.4f}"))
        self.history_table.setItem(row, 2, QTableWidgetItem(f"{record.get('Ki', 0):.5f}"))
        self.history_table.setItem(row, 3, QTableWidgetItem(f"{record.get('Kd', 0):.4f}"))
        self.history_table.setItem(row, 4, QTableWidgetItem(f"{record.get('avg_score', 0):.1f}"))

        # 调整后得分（应用惩罚后）
        adjusted = record.get("adjusted_score", record.get("avg_score", 0))
        adj_item = QTableWidgetItem(f"{adjusted:.1f}")
        # 如果调整后得分明显低于原始得分，标红
        if adjusted < record.get("avg_score", 0) * 0.8:
            adj_item.setForeground(QColor(255, 0, 0))
        self.history_table.setItem(row, 5, adj_item)

        # 过冲（超过阈值标红）
        overshoot = record.get("max_overshoot", 0)
        ovs_item = QTableWidgetItem(f"{overshoot:.2f}")
        if overshoot > 2.0:
            ovs_item.setForeground(QColor(255, 0, 0))
        elif overshoot > 1.0:
            ovs_item.setForeground(QColor(255, 165, 0))
        self.history_table.setItem(row, 6, ovs_item)

        self.history_table.setItem(
            row, 7, QTableWidgetItem(f"{record.get('avg_conv_time', 0):.0f}")
        )
        self.history_table.setItem(
            row, 8, QTableWidgetItem(f"{record.get('convergence_rsd', 0):.1f}")
        )

        # 滚动到最新行
        self.history_table.scrollToBottom()

        # 有数据后启用导出按钮
        self.export_btn.setEnabled(True)

        # 更新参数轨迹图
        if not hasattr(self, "_params_history"):
            self._params_history = {"Kp": [], "Ki": [], "Kd": []}

        self._params_history["Kp"].append(record.get("Kp", 0))
        self._params_history["Ki"].append(record.get("Ki", 0))
        self._params_history["Kd"].append(record.get("Kd", 0))

        if PYQTGRAPH_AVAILABLE and hasattr(self, "kp_curve"):
            x = list(range(len(self._params_history["Kp"])))
            self.kp_curve.setData(x, self._params_history["Kp"])
            # Ki乘以10使其在同一数量级可视化
            self.ki_curve.setData(x, [v * 10 for v in self._params_history["Ki"]])
            self.kd_curve.setData(x, self._params_history["Kd"])

    @Slot(str)
    def on_state_changed(self, state: str):
        """状态变化处理"""
        if state == "finished" or state == "idle":
            self._set_running(False)
        elif state == "paused":
            self.pause_btn.setText("继续")
        elif state == "running":
            self.pause_btn.setText("暂停")

    @Slot(dict)
    def on_optimization_finished(self, result: dict):
        """优化完成处理"""
        self._set_running(False)

        if "best_params" in result:
            self.update_best_params(result["best_params"])
