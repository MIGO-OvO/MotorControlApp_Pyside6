"""PID分析 Mixin 模块。

该模块提供PID分析页面相关功能，包括：
- PID实时分析图表和统计面板
- PID参数优化器集成
- 数据导出（报告/数据）

Note:
    部分复杂导出方法仍保留在主窗口中，待后续进一步拆分。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCharts import QChartView
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.pid_analyzer import PIDStatus
from src.core.pid_optimizer import PatternSearchOptimizer, PIDParams
from src.config.constants import BUTTON_TERTIARY, COLOR_TEXT_SECONDARY
from src.ui.widgets import (
    AnalysisChart,
    PIDAnalysisChart,
    PIDOptimizerPanel,
    PIDStatsPanel,
)


class AnalysisMixin:
    """PID分析功能 Mixin。

    提供PID实时分析、参数优化和数据导出功能。

    Attributes:
        pid_analyzer: PID分析器实例
        pid_optimizer: PID优化器实例
        pid_analysis_chart: PID分析图表
        pid_stats_panel: PID统计面板
    """

    def init_analysis_tab(self) -> None:
        """初始化PID控制分析标签页布局。"""
        layout = QVBoxLayout(self.analysis_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 使用TabWidget分隔分析和优化
        self.analysis_sub_tabs = QTabWidget()

        # ----- 子标签1: PID实时分析 -----
        analysis_widget = QWidget()
        analysis_layout = QVBoxLayout(analysis_widget)
        analysis_layout.setContentsMargins(5, 5, 5, 5)

        # PID 实时状态面板
        self.pid_stats_panel = PIDStatsPanel()
        analysis_layout.addWidget(self.pid_stats_panel, stretch=0)

        # PID 分析图表
        self.pid_analysis_chart = PIDAnalysisChart()
        analysis_layout.addWidget(self.pid_analysis_chart, stretch=3)

        # 控制按钮区域
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(10)

        button_style = BUTTON_TERTIARY

        action_buttons = [
            ("清空图表", self.clear_pid_chart),
            ("重置统计", self.reset_pid_stats),
            ("导出报告", self.export_pid_report),
            ("导出数据", self.export_pid_data),
        ]

        for btn_text, handler in action_buttons:
            btn = QPushButton(btn_text)
            btn.setStyleSheet(button_style)
            btn.clicked.connect(handler)
            control_layout.addWidget(btn)

        control_layout.addStretch(1)
        analysis_layout.addWidget(control_frame, stretch=0)

        # 历史统计面板
        history_group = QGroupBox("历史统计")
        history_group.setFont(QFont("Microsoft YaHei", 11))
        history_layout = QHBoxLayout(history_group)

        self.stats_widgets = {}
        for motor in ["X", "Y", "Z", "A"]:
            group = QGroupBox(f"微泵 {motor}")
            form = QFormLayout(group)
            form.setSpacing(4)

            labels = {
                "total_runs": QLabel("0"),
                "success_rate": QLabel("--"),
                "avg_conv_time": QLabel("--"),
                "avg_error": QLabel("--"),
            }

            for lbl in labels.values():
                lbl.setFont(QFont("Roboto Mono", 9))
                lbl.setAlignment(Qt.AlignRight)

            form.addRow("运行次数:", labels["total_runs"])
            form.addRow("成功率:", labels["success_rate"])
            form.addRow("平均收敛:", labels["avg_conv_time"])
            form.addRow("平均误差:", labels["avg_error"])

            self.stats_widgets[motor] = labels
            history_layout.addWidget(group)

        analysis_layout.addWidget(history_group, stretch=0)

        self.analysis_sub_tabs.addTab(analysis_widget, "PID实时分析")

        # ----- 子标签2: PID参数优化 -----
        self.pid_optimizer_panel = PIDOptimizerPanel()
        self._init_pid_optimizer()
        self.analysis_sub_tabs.addTab(self.pid_optimizer_panel, "PID参数优化")

        layout.addWidget(self.analysis_sub_tabs)

        # M3: 移除隐藏的旧版图表，仅保留兼容属性
        self.chart_view = None

    def _init_pid_optimizer(self):
        """初始化PID优化器"""
        self.pid_optimizer = PatternSearchOptimizer()

        # 设置串口发送回调
        self.pid_optimizer.set_send_callback(self.send_command)

        # 连接优化器信号
        self.pid_optimizer.progress_updated.connect(self.pid_optimizer_panel.update_progress)
        self.pid_optimizer.score_updated.connect(self.pid_optimizer_panel.update_score)
        self.pid_optimizer.state_changed.connect(self.pid_optimizer_panel.on_state_changed)
        self.pid_optimizer.optimization_finished.connect(self._on_optimization_finished)
        self.pid_optimizer.error_occurred.connect(lambda msg: self.log(f"优化器错误: {msg}"))

        # 连接面板信号
        self.pid_optimizer_panel.start_optimization.connect(self._start_pid_optimization)
        self.pid_optimizer_panel.stop_optimization.connect(self._stop_pid_optimization)
        self.pid_optimizer_panel.pause_optimization.connect(self.pid_optimizer.pause)
        self.pid_optimizer_panel.resume_optimization.connect(self.pid_optimizer.resume)
        self.pid_optimizer_panel.apply_params.connect(self._apply_pid_params)
        self.pid_optimizer_panel.single_test.connect(self._run_single_pid_test)
        self.pid_optimizer_panel.export_data.connect(self._export_pid_optimization_data)

        # 初始化单次测试状态
        self._single_test_active = False
        self._single_test_results = []
        self._single_test_params = {}

    def _start_pid_optimization(self, config: dict):
        """开始PID优化"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先打开串口连接")
            self.pid_optimizer_panel.on_state_changed("idle")
            return

        # 配置优化器
        self.pid_optimizer.configure(
            test_motor=config.get("test_motor", "X"),
            test_angle=config.get("test_angle", 45.0),
            test_runs=config.get("test_runs", 5),
            max_iterations=config.get("max_iterations", 50),
            initial_step=config.get("initial_step", 0.02),
            min_step=config.get("min_step", 0.005),
        )

        # 创建初始参数
        initial = config.get("initial_params", {})
        initial_params = PIDParams(
            Kp=initial.get("Kp", 0.14), Ki=initial.get("Ki", 0.015), Kd=initial.get("Kd", 0.06)
        )

        self.log(
            f"开始PID参数优化: 电机={config.get('test_motor')}, 角度={config.get('test_angle')}°"
        )
        self.pid_optimizer.start(initial_params)

    def _stop_pid_optimization(self):
        """停止PID优化和单次测试"""
        self.pid_optimizer.stop()

        if getattr(self, "_single_test_active", False):
            self._single_test_active = False
            self.send_command("PIDTESTSTOP\r\n")
            self.pid_optimizer_panel.on_single_test_complete()

        self.log("PID参数优化/测试已停止")

    def _on_optimization_finished(self, result: dict):
        """优化完成处理"""
        self.pid_optimizer_panel.on_optimization_finished(result)

        best = result.get("best_params", {})
        self.log(
            f"PID优化完成! 最优参数: Kp={best.get('Kp', 0):.4f}, Ki={best.get('Ki', 0):.5f}, Kd={best.get('Kd', 0):.4f}"
        )
        self.log(
            f"最优得分: {result.get('best_score', 0):.1f}, 迭代次数: {result.get('iterations', 0)}"
        )

        for record in self.pid_optimizer.get_history_summary():
            self.pid_optimizer_panel.add_history_record(record)

    def _apply_pid_params(self, params: dict):
        """应用PID参数到下位机"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先打开串口连接")
            return

        cmd = f"PIDCFG:{params.get('Kp', 0.14):.4f},{params.get('Ki', 0.015):.5f},{params.get('Kd', 0.06):.4f}\r\n"
        if self.send_command(cmd):
            self.log(
                f"已应用PID参数: Kp={params.get('Kp'):.4f}, Ki={params.get('Ki'):.5f}, Kd={params.get('Kd'):.4f}"
            )
            # 自动保存到配置文件
            if hasattr(self, 'save_settings'):
                self.save_settings()

    def _run_single_pid_test(self, config: dict):
        """执行单次PID测试（用于调试）"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先打开串口连接")
            self.pid_optimizer_panel.on_single_test_complete()
            return

        params = config.get("params", {})
        motor = config.get("test_motor", "X")
        angle = config.get("test_angle", 45.0)
        runs = config.get("test_runs", 1)

        self._single_test_params = params.copy()
        self._single_test_runs = runs
        self._single_test_results = []
        self._single_test_active = True

        # 先发送PID参数配置
        pid_cmd = f"PIDCFG:{params.get('Kp', 0.14):.4f},{params.get('Ki', 0.015):.5f},{params.get('Kd', 0.06):.4f}\r\n"
        self.send_command(pid_cmd)

        # 延迟发送测试指令
        def send_test():
            if self._single_test_active:
                direction = config.get("direction", "F")
                test_cmd = f"PIDTEST:{motor},{direction},{angle:.2f},{runs}\r\n"
                if self.send_command(test_cmd):
                    self.log(f"开始单次PID测试: {motor}轴 {direction} {angle}° × {runs}次")

        QTimer.singleShot(100, send_test)

    def clear_chart(self):
        if hasattr(self, "chart_view") and self.chart_view:
            chart = self.chart_view.chart()
            if chart:
                if hasattr(chart, "clear_data"):
                    chart.clear_data()
                elif hasattr(chart, "clear"):
                    chart.clear()

    def clear_pid_chart(self):
        """清空 PID 分析图表"""
        if hasattr(self, "pid_analysis_chart"):
            self.pid_analysis_chart.clear_all()
        self.log("PID图表已清空")

    def reset_pid_stats(self):
        """重置 PID 统计数据"""
        self.pid_analyzer.reset_history()

        for motor in ["X", "Y", "Z", "A"]:
            if motor in self.stats_widgets:
                self.stats_widgets[motor]["total_runs"].setText("0")
                self.stats_widgets[motor]["success_rate"].setText("--")
                self.stats_widgets[motor]["avg_conv_time"].setText("--")
                self.stats_widgets[motor]["avg_error"].setText("--")

        self.log("PID统计数据已重置")

    def _update_pid_analysis_display(self):
        """更新 PID 分析显示（定时器回调）"""
        try:
            if not hasattr(self, "pid_analyzer"):
                return

            active_motors = self.pid_analyzer.get_active_motors()
            if not active_motors:
                return

            stats_panel = getattr(self, "pid_stats_panel", None)
            for motor in active_motors:
                error_data = self.pid_analyzer.get_realtime_error_data(motor)
                if error_data and stats_panel:
                    _, current_error = error_data[-1]
                    stats_panel.update_error(motor, current_error)

                output_data = self.pid_analyzer.get_realtime_output_data(motor)
                if output_data and stats_panel:
                    _, output = output_data[-1]
                    stats_panel.update_output(motor, output)

                position_data = self.pid_analyzer.get_realtime_position_data(motor)
                if position_data and stats_panel:
                    _, target, _actual, _theo = position_data[-1]
                    stats_panel.update_target(motor, target)

            if hasattr(self, "pid_analysis_chart"):
                refresh = getattr(self.pid_analysis_chart, "refresh_all_curves", None)
                if callable(refresh):
                    refresh()
        except Exception:
            pass

    def _update_pid_history_stats(self):
        """更新 PID 历史统计显示"""
        if not hasattr(self, "stats_widgets"):
            return
        try:
            stats = self.pid_analyzer.get_motor_stats()
            for motor, data in stats.items():
                if motor in self.stats_widgets:
                    widgets = self.stats_widgets[motor]
                    widgets["total_runs"].setText(str(data["total_runs"]))
                    widgets["success_rate"].setText(f"{data['success_rate']:.1f}%")
                    widgets["avg_conv_time"].setText(f"{data['avg_convergence_time']:.0f}ms")
                    widgets["avg_error"].setText(f"{data['avg_final_error']:.3f}°")
        except Exception:
            pass
