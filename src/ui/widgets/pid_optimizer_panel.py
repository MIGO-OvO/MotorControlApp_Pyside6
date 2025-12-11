"""
PID参数优化面板 - UI组件
"""
from typing import Optional, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QFrame, QSplitter, QTextEdit, QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QDoubleValidator, QColor

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class PIDOptimizerPanel(QWidget):
    """PID参数优化面板"""
    
    # 信号
    start_optimization = Signal(dict)   # 开始优化，传递配置
    stop_optimization = Signal()        # 停止优化
    pause_optimization = Signal()       # 暂停优化
    resume_optimization = Signal()      # 恢复优化
    apply_params = Signal(dict)         # 应用参数
    single_test = Signal(dict)          # 单次测试，传递配置
    export_data = Signal()              # 导出数据
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._is_running = False
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 使用垂直分割器
        main_splitter = QSplitter(Qt.Vertical)
        
        # 上半部分：配置和控制
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # 当前参数组
        self._create_params_group(top_layout)
        
        # 优化配置组
        self._create_config_group(top_layout)
        
        # 控制按钮组
        self._create_control_group(top_layout)
        
        main_splitter.addWidget(top_widget)
        
        # 下半部分：进度和历史并排显示
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用水平分割器让进度和历史并排
        h_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：优化进度
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self._create_progress_group(progress_layout)
        h_splitter.addWidget(progress_widget)
        
        # 右侧：优化历史
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        self._create_results_group(results_layout)
        h_splitter.addWidget(results_widget)
        
        h_splitter.setSizes([400, 600])  # 进度:历史 = 4:6
        bottom_layout.addWidget(h_splitter)
        
        main_splitter.addWidget(bottom_widget)
        main_splitter.setSizes([200, 500])  # 配置:进度历史 = 2:5
        
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
        layout.addWidget(self.kp_input, 0, 1)
        
        # Ki
        layout.addWidget(QLabel("Ki:"), 0, 2)
        self.ki_input = QDoubleSpinBox()
        self.ki_input.setRange(0.0, 1.0)
        self.ki_input.setDecimals(5)
        self.ki_input.setSingleStep(0.001)
        self.ki_input.setValue(0.015)
        layout.addWidget(self.ki_input, 0, 3)
        
        # Kd
        layout.addWidget(QLabel("Kd:"), 0, 4)
        self.kd_input = QDoubleSpinBox()
        self.kd_input.setRange(0.0, 1.0)
        self.kd_input.setDecimals(4)
        self.kd_input.setSingleStep(0.01)
        self.kd_input.setValue(0.06)
        layout.addWidget(self.kd_input, 0, 5)
        
        # 应用按钮
        self.apply_btn = QPushButton("应用参数")
        self.apply_btn.clicked.connect(self._on_apply_params)
        layout.addWidget(self.apply_btn, 0, 6)
        
        # 预设按钮
        preset_layout = QHBoxLayout()
        presets = [
            ("保守", 0.08, 0.010, 0.08),
            ("平衡", 0.14, 0.015, 0.06),
            ("激进", 0.20, 0.020, 0.04)
        ]
        for name, kp, ki, kd in presets:
            btn = QPushButton(name)
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda checked, p=(kp, ki, kd): self._set_preset(p))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        layout.addLayout(preset_layout, 1, 0, 1, 7)
        
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
        self.motor_combo.addItems(['X', 'Y', 'Z', 'A'])
        layout.addWidget(self.motor_combo, 0, 1)
        
        # 测试角度（每次正转的角度增量）
        layout.addWidget(QLabel("转动角度:"), 0, 2)
        self.angle_input = QDoubleSpinBox()
        self.angle_input.setRange(10, 180)
        self.angle_input.setValue(60)  # 默认60度
        self.angle_input.setSuffix(" °")
        self.angle_input.setToolTip("每次测试正转的角度增量")
        layout.addWidget(self.angle_input, 0, 3)
        
        # 每参数测试次数
        layout.addWidget(QLabel("测试次数:"), 0, 4)
        self.runs_input = QSpinBox()
        self.runs_input.setRange(1, 20)
        self.runs_input.setValue(5)
        layout.addWidget(self.runs_input, 0, 5)
        
        # 最大迭代
        layout.addWidget(QLabel("最大迭代:"), 1, 0)
        self.max_iter_input = QSpinBox()
        self.max_iter_input.setRange(10, 200)
        self.max_iter_input.setValue(50)
        layout.addWidget(self.max_iter_input, 1, 1)
        
        # 初始步长
        layout.addWidget(QLabel("初始步长:"), 1, 2)
        self.step_input = QDoubleSpinBox()
        self.step_input.setRange(0.005, 0.1)
        self.step_input.setDecimals(3)
        self.step_input.setSingleStep(0.005)
        self.step_input.setValue(0.02)
        layout.addWidget(self.step_input, 1, 3)
        
        # 最小步长
        layout.addWidget(QLabel("最小步长:"), 1, 4)
        self.min_step_input = QDoubleSpinBox()
        self.min_step_input.setRange(0.001, 0.05)
        self.min_step_input.setDecimals(3)
        self.min_step_input.setSingleStep(0.001)
        self.min_step_input.setValue(0.005)
        layout.addWidget(self.min_step_input, 1, 5)
        
        parent_layout.addWidget(group)
    
    def _create_control_group(self, parent_layout):
        """创建控制按钮组"""
        layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶ 开始优化")
        self.start_btn.setFont(QFont("Microsoft YaHei", 11))
        self.start_btn.setFixedHeight(36)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)
        
        self.single_test_btn = QPushButton("🔬 单次测试")
        self.single_test_btn.setFont(QFont("Microsoft YaHei", 11))
        self.single_test_btn.setFixedHeight(36)
        self.single_test_btn.setStyleSheet("background-color: #2196F3; color: white;")
        self.single_test_btn.clicked.connect(self._on_single_test)
        self.single_test_btn.setToolTip("使用当前参数执行单次测试，用于调试")
        layout.addWidget(self.single_test_btn)
        
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setFont(QFont("Microsoft YaHei", 11))
        self.pause_btn.setFixedHeight(36)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)
        layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFont(QFont("Microsoft YaHei", 11))
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self.stop_btn)
        
        self.apply_best_btn = QPushButton("📥 应用最优")
        self.apply_best_btn.setFont(QFont("Microsoft YaHei", 11))
        self.apply_best_btn.setFixedHeight(36)
        self.apply_best_btn.setEnabled(False)
        self.apply_best_btn.clicked.connect(self._on_apply_best)
        layout.addWidget(self.apply_best_btn)
        
        self.export_btn = QPushButton("📊 导出数据")
        self.export_btn.setFont(QFont("Microsoft YaHei", 11))
        self.export_btn.setFixedHeight(36)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        layout.addWidget(self.export_btn)
        
        parent_layout.addLayout(layout)
    
    def _create_progress_group(self, parent_layout):
        """创建进度显示组"""
        group = QGroupBox("优化进度")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QVBoxLayout(group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 状态信息
        info_layout = QHBoxLayout()
        
        self.status_label = QLabel("状态: 空闲")
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        info_layout.addWidget(self.status_label)
        
        info_layout.addStretch()
        
        self.score_label = QLabel("当前得分: -- | 最优得分: --")
        self.score_label.setFont(QFont("Microsoft YaHei", 10))
        self.score_label.setStyleSheet("color: #007AFF;")
        info_layout.addWidget(self.score_label)
        
        layout.addLayout(info_layout)
        
        # 最优参数显示
        self.best_params_label = QLabel("最优参数: --")
        self.best_params_label.setFont(QFont("Consolas", 10))
        self.best_params_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self.best_params_label)
        
        parent_layout.addWidget(group)
    
    def _create_results_group(self, parent_layout):
        """创建结果显示组"""
        group = QGroupBox("优化历史")
        group.setFont(QFont("Microsoft YaHei", 10))
        layout = QVBoxLayout(group)
        
        # 评分曲线
        if PYQTGRAPH_AVAILABLE:
            self.score_plot = pg.PlotWidget()
            self.score_plot.setBackground('w')
            self.score_plot.showGrid(x=True, y=True, alpha=0.3)
            self.score_plot.setLabel('left', '得分')
            self.score_plot.setLabel('bottom', '迭代次数')
            self.score_plot.setMinimumHeight(120)
            
            self.score_curve = self.score_plot.plot(
                pen=pg.mkPen(color='#007AFF', width=2),
                symbol='o',
                symbolSize=6,
                symbolBrush='#007AFF'
            )
            self.best_score_curve = self.score_plot.plot(
                pen=pg.mkPen(color='#4CAF50', width=2, style=Qt.DashLine)
            )
            
            layout.addWidget(self.score_plot)
        else:
            layout.addWidget(QLabel("图表功能需要 pyqtgraph 库"))
        
        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels(['#', 'Kp', 'Ki', 'Kd', '原始分', '调整分', '过冲°', '收敛ms', 'RSD%'])
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
            'Kp': self.kp_input.value(),
            'Ki': self.ki_input.value(),
            'Kd': self.kd_input.value()
        }
        self.apply_params.emit(params)
    
    def _on_start(self):
        """开始优化"""
        config = {
            'initial_params': {
                'Kp': self.kp_input.value(),
                'Ki': self.ki_input.value(),
                'Kd': self.kd_input.value()
            },
            'test_motor': self.motor_combo.currentText(),
            'test_angle': self.angle_input.value(),
            'test_runs': self.runs_input.value(),
            'max_iterations': self.max_iter_input.value(),
            'initial_step': self.step_input.value(),
            'min_step': self.min_step_input.value()
        }
        
        self._set_running(True)
        self._clear_history()
        self.start_optimization.emit(config)
    
    def _on_pause(self):
        """暂停/恢复"""
        if self.pause_btn.text() == "⏸ 暂停":
            self.pause_btn.setText("▶ 继续")
            self.pause_optimization.emit()
        else:
            self.pause_btn.setText("⏸ 暂停")
            self.resume_optimization.emit()
    
    def _on_stop(self):
        """停止优化或单次测试"""
        # 如果是单次测试运行中
        if hasattr(self, '_single_test_running') and self._single_test_running:
            self._single_test_running = False
            self.single_test_btn.setEnabled(True)
            self.single_test_btn.setText("🔬 单次测试")
            self.stop_btn.setEnabled(False)
            self.status_label.setText("状态: 测试已停止")
        
        self._set_running(False)
        self.stop_optimization.emit()
    
    def _on_single_test(self):
        """单次测试当前参数"""
        # 防止重复点击
        if hasattr(self, '_single_test_running') and self._single_test_running:
            return
        
        self._single_test_running = True
        self.single_test_btn.setEnabled(False)
        self.single_test_btn.setText("🔬 测试中...")
        self.stop_btn.setEnabled(True)  # 启用停止按钮
        self.status_label.setText("状态: 单次测试进行中...")
        
        config = {
            'params': {
                'Kp': self.kp_input.value(),
                'Ki': self.ki_input.value(),
                'Kd': self.kd_input.value()
            },
            'test_motor': self.motor_combo.currentText(),
            'test_angle': self.angle_input.value(),
            'test_runs': self.runs_input.value()
        }
        self.single_test.emit(config)
    
    def on_single_test_complete(self):
        """单次测试完成"""
        self._single_test_running = False
        self.single_test_btn.setEnabled(True)
        self.single_test_btn.setText("🔬 单次测试")
        self.stop_btn.setEnabled(False)  # 禁用停止按钮
        self.status_label.setText("状态: 单次测试完成")
    
    def on_single_test_result(self, result: dict):
        """单次测试结果更新"""
        # 更新得分显示
        score = result.get('score', 0)
        self.score_label.setText(f"当前得分: {score:.1f} | 最优得分: --")
        
        # 添加到历史记录
        record = {
            'index': self.history_table.rowCount(),
            'Kp': result.get('Kp', 0),
            'Ki': result.get('Ki', 0),
            'Kd': result.get('Kd', 0),
            'avg_score': score,
            'runs': result.get('runs', 1)
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
                self.kp_input.setValue(params.get('Kp', 0.14))
                self.ki_input.setValue(params.get('Ki', 0.015))
                self.kd_input.setValue(params.get('Kd', 0.06))
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
        self.step_input.setEnabled(not running)
        self.min_step_input.setEnabled(not running)
        
        if running:
            self.pause_btn.setText("⏸ 暂停")
    
    def _clear_history(self):
        """清空历史"""
        self.history_table.setRowCount(0)
        self._score_history = []
        self._best_score_history = []
        if PYQTGRAPH_AVAILABLE:
            self.score_curve.setData([], [])
            self.best_score_curve.setData([], [])
    
    # ===== 外部调用的更新方法 =====
    
    @Slot(int, int, str)
    def update_progress(self, current: int, total: int, message: str):
        """更新进度"""
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.status_label.setText(f"状态: {message}")
    
    @Slot(float, float)
    def update_score(self, current_score: float, best_score: float):
        """更新得分显示"""
        self.score_label.setText(f"当前得分: {current_score:.1f} | 最优得分: {best_score:.1f}")
        
        # 更新曲线
        if not hasattr(self, '_score_history'):
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
        """更新最优参数显示"""
        text = f"最优参数: Kp={params['Kp']:.4f}, Ki={params['Ki']:.5f}, Kd={params['Kd']:.4f}"
        self.best_params_label.setText(text)
        self.apply_best_btn.setEnabled(True)
    
    @Slot(dict)
    def add_history_record(self, record: dict):
        """添加历史记录"""
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        
        self.history_table.setItem(row, 0, QTableWidgetItem(str(record.get('index', row))))
        self.history_table.setItem(row, 1, QTableWidgetItem(f"{record.get('Kp', 0):.4f}"))
        self.history_table.setItem(row, 2, QTableWidgetItem(f"{record.get('Ki', 0):.5f}"))
        self.history_table.setItem(row, 3, QTableWidgetItem(f"{record.get('Kd', 0):.4f}"))
        self.history_table.setItem(row, 4, QTableWidgetItem(f"{record.get('avg_score', 0):.1f}"))
        
        # 调整后得分（应用惩罚后）
        adjusted = record.get('adjusted_score', record.get('avg_score', 0))
        adj_item = QTableWidgetItem(f"{adjusted:.1f}")
        # 如果调整后得分明显低于原始得分，标红
        if adjusted < record.get('avg_score', 0) * 0.8:
            adj_item.setForeground(QColor(255, 0, 0))
        self.history_table.setItem(row, 5, adj_item)
        
        # 过冲（超过阈值标红）
        overshoot = record.get('max_overshoot', 0)
        ovs_item = QTableWidgetItem(f"{overshoot:.2f}")
        if overshoot > 2.0:
            ovs_item.setForeground(QColor(255, 0, 0))
        elif overshoot > 1.0:
            ovs_item.setForeground(QColor(255, 165, 0))
        self.history_table.setItem(row, 6, ovs_item)
        
        self.history_table.setItem(row, 7, QTableWidgetItem(f"{record.get('avg_conv_time', 0):.0f}"))
        self.history_table.setItem(row, 8, QTableWidgetItem(f"{record.get('convergence_rsd', 0):.1f}"))
        
        # 滚动到最新行
        self.history_table.scrollToBottom()
        
        # 有数据后启用导出按钮
        self.export_btn.setEnabled(True)
    
    @Slot(str)
    def on_state_changed(self, state: str):
        """状态变化处理"""
        if state == 'finished' or state == 'idle':
            self._set_running(False)
        elif state == 'paused':
            self.pause_btn.setText("▶ 继续")
        elif state == 'running':
            self.pause_btn.setText("⏸ 暂停")
    
    @Slot(dict)
    def on_optimization_finished(self, result: dict):
        """优化完成处理"""
        self._set_running(False)
        
        if 'best_params' in result:
            self.update_best_params(result['best_params'])
        
        self.status_label.setText(
            f"状态: 优化完成! 迭代{result.get('iterations', 0)}次, "
            f"最优得分{result.get('best_score', 0):.1f}"
        )
