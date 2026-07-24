"""Independent health monitor page for ESP32 detector system metrics."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config.constants import (
    BUTTON_DANGER,
    BUTTON_SECONDARY,
    BUTTON_SUCCESS,
    COLOR_ACCENT_BLUE,
    COLOR_ACCENT_GREEN,
    COLOR_ACCENT_ORANGE,
    COLOR_ACCENT_RED,
    COLOR_BG_SUBTLE,
    COLOR_BORDER_LIGHT,
    COLOR_PRIMARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)
from src.core.health_monitor import HealthHistory, HealthSample

try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None  # type: ignore


class HealthMonitorMixin:
    """ESP32 health page, current-session history, and validation metrics."""

    def _health_init_vars(self) -> None:
        self.health_history = HealthHistory()
        self.health_chart_limit = 600
        self.detector_health = {}
        self.detector_diag = {}
        self.detector_ads_health = {}
        self.last_command_rtt_ms = None
        self.health_stress_state = "IDLE"
        self.health_recording_active = False
        self.health_monitor_duration_s = 300
        self.health_monitor_started_at = None
        self.health_log_dir = Path.cwd() / "health_logs"
        self.health_last_auto_csv_path = None
        self.health_monitor_timer = QTimer(self)
        self.health_monitor_timer.setSingleShot(True)
        self.health_monitor_timer.timeout.connect(lambda: self._health_finish_monitoring(auto=True))

    def init_health_monitor_tab(self) -> None:
        main_layout = QVBoxLayout(self.health_tab)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        if not PYQTGRAPH_AVAILABLE:
            self.health_dependency_label = QLabel(
                "健康监控图表不可用，缺少 pyqtgraph 库。ESP32 健康摘要仍会在左侧串口区显示。"
            )
            self.health_dependency_label.setAlignment(Qt.AlignCenter)
            self.health_dependency_label.setWordWrap(True)
            self.health_dependency_label.setFont(QFont("Microsoft YaHei", 14))
            main_layout.addWidget(self.health_dependency_label)
            return

        self._health_create_metric_group(main_layout)

        middle_splitter = QSplitter(Qt.Horizontal)
        self._health_create_control_group(middle_splitter)
        self._health_create_charts_group(middle_splitter)
        middle_splitter.setSizes([320, 820])
        main_layout.addWidget(middle_splitter, stretch=1)

        self._health_refresh_all()

    def _health_create_metric_group(self, parent_layout) -> None:
        group = QGroupBox("当前状态")
        layout = QGridLayout(group)
        layout.setSpacing(10)

        self.health_temp_value = self._health_metric_label("--", COLOR_ACCENT_ORANGE)
        self.health_heap_value = self._health_metric_label("--", COLOR_ACCENT_GREEN)
        self.health_cpu_value = self._health_metric_label("--", COLOR_PRIMARY)
        self.health_loop_gap_value = self._health_metric_label("--", COLOR_ACCENT_BLUE)
        self.health_angle_age_value = self._health_metric_label("--", COLOR_ACCENT_RED)
        self.health_rtt_value = self._health_metric_label("--", COLOR_TEXT_PRIMARY)
        self.health_stack_value = self._health_metric_label("--", COLOR_TEXT_SECONDARY, 15)
        self.health_record_count_value = self._health_metric_label("0", COLOR_TEXT_PRIMARY)
        self.health_ads_success_value = self._health_metric_label("--", COLOR_ACCENT_GREEN)
        self.health_ads_i2c_value = self._health_metric_label("--", COLOR_ACCENT_RED)
        self.health_ads_crc_value = self._health_metric_label("--", COLOR_ACCENT_RED)
        self.health_ads_duplicate_value = self._health_metric_label("--", COLOR_ACCENT_ORANGE)
        self.health_ads_transient_value = self._health_metric_label("--", COLOR_ACCENT_BLUE)
        self.health_ads_mutex_value = self._health_metric_label("--", COLOR_ACCENT_ORANGE)

        metrics = [
            ("温度", self.health_temp_value),
            ("Heap 空闲", self.health_heap_value),
            ("CPU 频率", self.health_cpu_value),
            ("Active Loop Max", self.health_loop_gap_value),
            ("角度缓存年龄", self.health_angle_age_value),
            ("串口 RTT", self.health_rtt_value),
            ("任务栈水位 L/C/S", self.health_stack_value),
            ("会话记录", self.health_record_count_value),
            ("ADS 成功", self.health_ads_success_value),
            ("ADS I2C 错误", self.health_ads_i2c_value),
            ("ADS CRC 错误", self.health_ads_crc_value),
            ("ADS 重复帧", self.health_ads_duplicate_value),
            ("ADS 瞬态丢弃", self.health_ads_transient_value),
            ("ADS Mutex 超时", self.health_ads_mutex_value),
        ]
        for index, (title, label) in enumerate(metrics):
            row = index // 4
            col = (index % 4) * 2
            title_label = QLabel(title)
            title_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
            layout.addWidget(title_label, row, col)
            layout.addWidget(label, row, col + 1)

        parent_layout.addWidget(group)

    def _health_metric_label(self, text: str, color: str, size: int = 18) -> QLabel:
        label = QLabel(text)
        label.setMinimumWidth(90)
        label.setStyleSheet(f"font-size: {size}px; font-weight: 700; color: {color};")
        return label

    def _health_create_control_group(self, parent_splitter) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        control_group = QGroupBox("记录")
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(8)

        self.health_recording_status_label = QLabel("自动记录：连接后收到健康包即写入当前会话")
        self._health_create_recording_group(control_layout)
        self._health_create_stress_group(control_layout)

        self.health_clear_btn = QPushButton("清空记录")
        self.health_clear_btn.setStyleSheet(BUTTON_DANGER)
        self.health_clear_btn.clicked.connect(self._health_clear_history)
        self.health_export_csv_btn = QPushButton("导出 CSV")
        self.health_export_csv_btn.setStyleSheet(BUTTON_SECONDARY)
        self.health_export_csv_btn.clicked.connect(self._health_export_csv)
        self.health_save_png_btn = QPushButton("保存图表 PNG")
        self.health_save_png_btn.setStyleSheet(BUTTON_SECONDARY)
        self.health_save_png_btn.clicked.connect(self._health_save_chart_png)

        for button in [
            self.health_clear_btn,
            self.health_export_csv_btn,
            self.health_save_png_btn,
        ]:
            button.setMinimumHeight(34)
            control_layout.addWidget(button)

        layout.addWidget(control_group)

        summary_group = QGroupBox("摘要")
        summary_layout = QVBoxLayout(summary_group)
        self.health_summary_label = QLabel("等待 ESP32 健康包")
        self.health_summary_label.setWordWrap(True)
        self.health_summary_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.health_latest_time_label = QLabel("最近更新：--")
        self.health_latest_time_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        summary_layout.addWidget(self.health_summary_label)
        summary_layout.addWidget(self.health_latest_time_label)
        layout.addWidget(summary_group)

        layout.addStretch(1)
        parent_splitter.addWidget(panel)

    def _health_create_recording_group(self, parent_layout) -> None:
        group = QGroupBox("健康记录")
        layout = QGridLayout(group)
        layout.setSpacing(8)

        self.health_monitor_duration_spin = QSpinBox()
        self.health_monitor_duration_spin.setRange(1, 86400)
        self.health_monitor_duration_spin.setValue(self.health_monitor_duration_s)
        self.health_monitor_duration_spin.setSuffix(" s")

        self.health_recording_status_label = QLabel("空闲：设置时长后点击开始监测")
        self.health_recording_status_label.setWordWrap(True)
        self.health_recording_status_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")

        self.health_monitor_start_btn = QPushButton("开始监测")
        self.health_monitor_start_btn.setStyleSheet(BUTTON_SUCCESS)
        self.health_monitor_start_btn.clicked.connect(self._health_start_monitoring)

        self.health_monitor_stop_btn = QPushButton("停止并保存")
        self.health_monitor_stop_btn.setStyleSheet(BUTTON_DANGER)
        self.health_monitor_stop_btn.clicked.connect(self._health_stop_monitoring)
        self.health_monitor_stop_btn.setEnabled(False)

        layout.addWidget(QLabel("监测时长"), 0, 0)
        layout.addWidget(self.health_monitor_duration_spin, 0, 1)
        layout.addWidget(self.health_recording_status_label, 1, 0, 1, 2)
        layout.addWidget(self.health_monitor_start_btn, 2, 0, 1, 2)
        layout.addWidget(self.health_monitor_stop_btn, 3, 0, 1, 2)
        parent_layout.addWidget(group)

    def _health_create_stress_group(self, parent_layout) -> None:
        group = QGroupBox("CPU 压力测试")
        layout = QGridLayout(group)
        layout.setSpacing(8)

        self.health_stress_duration_spin = QSpinBox()
        self.health_stress_duration_spin.setRange(1, 1800)
        self.health_stress_duration_spin.setValue(300)
        self.health_stress_duration_spin.setSuffix(" s")

        self.health_stress_mode_combo = QComboBox()
        self.health_stress_mode_combo.addItems(["FULL", "CPU"])
        self.health_stress_mode_combo.setCurrentText("FULL")

        self.health_stress_status_label = QLabel("IDLE")
        self.health_stress_status_label.setWordWrap(True)
        self.health_stress_status_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")

        self.health_stress_start_btn = QPushButton("启动压力测试")
        self.health_stress_start_btn.setStyleSheet(BUTTON_SUCCESS)
        self.health_stress_start_btn.clicked.connect(self._health_start_stress_test)
        self.health_stress_stop_btn = QPushButton("停止压力测试")
        self.health_stress_stop_btn.setStyleSheet(BUTTON_DANGER)
        self.health_stress_stop_btn.clicked.connect(self._health_stop_stress_test)
        self.health_stress_status_btn = QPushButton("查询状态")
        self.health_stress_status_btn.setStyleSheet(BUTTON_SECONDARY)
        self.health_stress_status_btn.clicked.connect(self._health_query_stress_test)

        layout.addWidget(QLabel("时长"), 0, 0)
        layout.addWidget(self.health_stress_duration_spin, 0, 1)
        layout.addWidget(QLabel("模式"), 1, 0)
        layout.addWidget(self.health_stress_mode_combo, 1, 1)
        layout.addWidget(self.health_stress_status_label, 2, 0, 1, 2)
        layout.addWidget(self.health_stress_start_btn, 3, 0, 1, 2)
        layout.addWidget(self.health_stress_stop_btn, 4, 0, 1, 2)
        layout.addWidget(self.health_stress_status_btn, 5, 0, 1, 2)
        parent_layout.addWidget(group)

    def _health_create_charts_group(self, parent_splitter) -> None:
        self.health_chart_area = QWidget()
        layout = QGridLayout(self.health_chart_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.health_temp_plot, self.health_temp_curve = self._health_make_plot(
            "ESP32 温度", "degC", COLOR_ACCENT_ORANGE
        )
        self.health_heap_plot, self.health_heap_curve = self._health_make_plot(
            "Heap 空闲百分比", "%", COLOR_ACCENT_GREEN
        )
        self.health_loop_gap_plot, self.health_loop_gap_curve = self._health_make_plot(
            "电机运行最大循环间隔", "us", COLOR_ACCENT_BLUE
        )
        self.health_latency_plot, self.health_angle_age_curve = self._health_make_plot(
            "角度缓存年龄 / 串口 RTT", "ms", COLOR_ACCENT_RED
        )
        self.health_rtt_curve = self.health_latency_plot.plot(
            pen=pg.mkPen(color=COLOR_PRIMARY, width=2)
        )

        layout.addWidget(self.health_temp_plot, 0, 0)
        layout.addWidget(self.health_heap_plot, 0, 1)
        layout.addWidget(self.health_loop_gap_plot, 1, 0)
        layout.addWidget(self.health_latency_plot, 1, 1)
        parent_splitter.addWidget(self.health_chart_area)

    def _health_make_plot(self, title: str, left_label: str, color: str):
        plot = pg.PlotWidget()
        plot.setTitle(title)
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setLabel("left", left_label)
        plot.setLabel("bottom", "elapsed", units="s")
        plot.setMinimumHeight(210)
        curve = plot.plot(pen=pg.mkPen(color=color, width=2))
        return plot, curve

    def handle_health_packet(self, packet: dict) -> None:
        """Handle ESP32 0xEE health packet and append a session sample."""
        if getattr(self, "_closing", False):
            return
        self.detector_health = dict(packet)
        if hasattr(self, "health_history") and self.health_recording_active:
            self.health_history.append_packet(packet, host_time=datetime.now())
        self._update_detector_health_labels()
        self._health_refresh_all()

    def _health_record_debug_value(self, key: str, value: int) -> None:
        self.detector_diag[key] = value
        if hasattr(self, "health_history") and self.health_recording_active:
            self.health_history.update_debug_value(key, value)
        self._update_detector_health_labels()
        self._health_refresh_all()

    def _health_record_ads_counters(self, counters: dict[str, int]) -> None:
        previous = dict(getattr(self, "detector_ads_health", {}))
        self.detector_ads_health = {key: int(value) for key, value in counters.items()}
        if hasattr(self, "health_history") and self.health_recording_active:
            self.health_history.update_ads_counters(self.detector_ads_health)

        warning_labels = {
            "i2c_error": "I2C 错误",
            "crc_error": "CRC 错误",
            "duplicate": "重复帧",
            "transient_drop": "瞬态丢弃",
        }
        for key, label in warning_labels.items():
            old_value = previous.get(key)
            new_value = self.detector_ads_health.get(key)
            if old_value is not None and new_value is not None and new_value > old_value:
                self.log(f"[ADS诊断] {label}: {old_value} -> {new_value}")

        if hasattr(self, "_spectro_refresh_integrity_label"):
            self._spectro_refresh_integrity_label()
        self._health_refresh_all()

    def _health_handle_stress_line(self, line: str) -> bool:
        text = line.strip()
        if text.startswith("STRESS_OK:START"):
            duration = _extract_named_int(text, "duration_s")
            mode = _extract_named_text(text, "mode") or "CPU"
            if duration is None:
                self._health_set_stress_status(f"RUNNING {mode}")
            else:
                self._health_set_stress_status(f"RUNNING {mode} duration {duration}s")
            return True
        if text == "STRESS_OK:STOP":
            self._health_set_stress_status("IDLE stopped")
            return True
        if text.startswith("STRESS_STATUS:RUNNING"):
            mode = _extract_named_text(text, "mode") or "CPU"
            duration = _extract_named_int(text, "duration_s")
            elapsed = _extract_named_int(text, "elapsed_s")
            remaining = _extract_named_int(text, "remaining_s")
            self._health_set_stress_status(
                f"RUNNING {mode} elapsed {elapsed}s, remaining {remaining}s / duration {duration}s"
            )
            return True
        if text == "STRESS_STATUS:IDLE":
            self._health_set_stress_status("IDLE")
            return True
        if text.startswith("STRESS_DONE:"):
            mode = _extract_named_text(text, "mode") or "CPU"
            duration = _extract_named_int(text, "duration_s")
            self._health_set_stress_status(f"DONE {mode} duration {duration}s")
            return True
        if text.startswith("STRESS_ERR:"):
            self._health_set_stress_status(f"ERR {text.split(':', 1)[1]}")
            return True
        return False

    def _health_set_stress_status(self, status: str) -> None:
        self.health_stress_state = status
        if hasattr(self, "health_stress_status_label"):
            self.health_stress_status_label.setText(status)

    def _health_start_monitoring(self) -> None:
        if self.health_recording_active:
            return
        self.health_monitor_duration_s = self.health_monitor_duration_spin.value()
        self.health_history.clear()
        self.health_recording_active = True
        self.health_monitor_started_at = datetime.now()
        self.health_last_auto_csv_path = None
        self.health_monitor_timer.start(self.health_monitor_duration_s * 1000)
        self._health_update_recording_controls(
            f"记录中：计划记录 {self.health_monitor_duration_s}s"
        )
        self._health_refresh_all()
        self.log(f"[健康监控] 开始记录 {self.health_monitor_duration_s}s")

    def _health_stop_monitoring(self) -> None:
        self._health_finish_monitoring(auto=False)

    def _health_finish_monitoring(self, auto: bool = False) -> None:
        if not self.health_recording_active:
            return None

        if self.health_monitor_timer.isActive():
            self.health_monitor_timer.stop()

        self.health_recording_active = False
        saved_path = None
        try:
            saved_path = self._health_auto_save_csv()
            suffix = "自动保存" if auto else "已保存"
            self._health_update_recording_controls(f"完成：{suffix}到 {saved_path}")
            self.log(f"[健康监控] CSV 已保存: {saved_path}")
        except Exception as exc:
            self._health_update_recording_controls(f"完成：保存失败：{exc}")
            QMessageBox.critical(self, "保存失败", f"健康监控 CSV 自动保存失败: {exc}")

        self._health_refresh_all()
        return saved_path

    def _health_auto_save_csv(self) -> Path:
        self.health_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        file_path = self.health_log_dir / f"health_monitor_{timestamp}.csv"
        self.health_history.export_csv(file_path)
        self.health_last_auto_csv_path = file_path
        return file_path

    def _health_update_recording_controls(self, status: str | None = None) -> None:
        if hasattr(self, "health_recording_status_label") and status is not None:
            self.health_recording_status_label.setText(status)
        if hasattr(self, "health_monitor_start_btn"):
            self.health_monitor_start_btn.setEnabled(not self.health_recording_active)
        if hasattr(self, "health_monitor_stop_btn"):
            self.health_monitor_stop_btn.setEnabled(self.health_recording_active)

    def _health_start_stress_test(self) -> None:
        duration_s = self.health_stress_duration_spin.value()
        mode = self.health_stress_mode_combo.currentText()
        if mode == "FULL":
            self.send_command(f"STRESS:START:{duration_s},FULL\r\n")
        else:
            self.send_command(f"STRESS:START:{duration_s}\r\n")

    def _health_stop_stress_test(self) -> None:
        self.send_command("STRESS:STOP\r\n")

    def _health_query_stress_test(self) -> None:
        self.send_command("STRESS:STATUS?\r\n")

    def _record_command_sent(self, command: str) -> None:
        self.command_rtt_tracker.record(command)

    def _finish_command_rtt(self, response: str, now_s=None) -> None:
        sample = self.command_rtt_tracker.finish(response, now_s=now_s)
        if sample is None:
            return
        self.last_command_rtt_ms = sample.rtt_ms
        if hasattr(self, "health_history") and self.health_recording_active:
            self.health_history.update_command_rtt(sample.rtt_ms)
        self._update_detector_health_labels()
        self._health_refresh_all()
        self.log(
            f"[串口RTT] {sample.rtt_ms:.1f} ms | "
            f"{sample.command} -> {sample.response}"
        )

    def _update_detector_health_labels(self) -> None:
        health = getattr(self, "detector_health", {})
        diag = getattr(self, "detector_diag", {})

        if hasattr(self, "detector_health_label"):
            if health:
                temp = health.get("temp_c")
                temp_text = f"{temp:.1f}°C" if temp is not None else "--"
                heap_pct = health.get("heap_free_pct")
                heap_text = f"{heap_pct:.1f}%" if heap_pct is not None else "--"
                self.detector_health_label.setText(
                    f"ESP32: {health.get('cpu_freq_mhz', '--')}MHz "
                    f"{temp_text} Heap {heap_text} "
                    f"Tasks {health.get('task_count', '--')}"
                )
            else:
                self.detector_health_label.setText("ESP32: --")

        if hasattr(self, "detector_stack_label"):
            if health:
                self.detector_stack_label.setText(
                    "任务栈: "
                    f"L {health.get('loop_stack_hwm', '--')} / "
                    f"C {health.get('comms_stack_hwm', '--')} / "
                    f"S {health.get('sensors_stack_hwm', '--')}"
                )
            else:
                self.detector_stack_label.setText("任务栈: --")

        if hasattr(self, "detector_diag_label"):
            loop_gap = diag.get("loop_gap_active_max_us")
            angle_age = diag.get("angle_age_ms")
            loop_text = f"{loop_gap}us" if loop_gap is not None else "--"
            age_text = f"{angle_age}ms" if angle_age is not None else "--"
            self.detector_diag_label.setText(
                f"验证: LoopGap {loop_text} | AngleAge {age_text}"
            )

        if hasattr(self, "command_rtt_label"):
            if self.last_command_rtt_ms is None:
                self.command_rtt_label.setText("RTT: --")
            else:
                self.command_rtt_label.setText(f"RTT: {self.last_command_rtt_ms:.1f} ms")

    def _health_refresh_all(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, "health_temp_value"):
            return
        latest = self.health_history.latest if hasattr(self, "health_history") else None
        self._health_update_metrics(latest)
        self._health_refresh_charts()

    def _health_update_metrics(self, sample: HealthSample | None) -> None:
        health = getattr(self, "detector_health", {})
        diag = getattr(self, "detector_diag", {})
        ads = getattr(self, "detector_ads_health", {})

        self.health_temp_value.setText(_format_unit(health.get("temp_c"), "°C", 1))
        self.health_heap_value.setText(_format_unit(health.get("heap_free_pct"), "%", 1))
        self.health_cpu_value.setText(_format_unit(health.get("cpu_freq_mhz"), "MHz", 0))
        self.health_loop_gap_value.setText(
            _format_unit(diag.get("loop_gap_active_max_us"), "us", 0)
        )
        self.health_angle_age_value.setText(_format_unit(diag.get("angle_age_ms"), "ms", 0))
        self.health_rtt_value.setText(_format_unit(self.last_command_rtt_ms, "ms", 1))
        self.health_ads_success_value.setText(_format_count(ads.get("success")))
        self.health_ads_i2c_value.setText(_format_count(ads.get("i2c_error")))
        self.health_ads_crc_value.setText(_format_count(ads.get("crc_error")))
        self.health_ads_duplicate_value.setText(_format_count(ads.get("duplicate")))
        self.health_ads_transient_value.setText(_format_count(ads.get("transient_drop")))
        self.health_ads_mutex_value.setText(_format_count(ads.get("mutex_timeout")))

        if health:
            self.health_stack_value.setText(
                f"{health.get('loop_stack_hwm', '--')}/"
                f"{health.get('comms_stack_hwm', '--')}/"
                f"{health.get('sensors_stack_hwm', '--')}"
            )
            self.health_summary_label.setText(
                f"Uptime {health.get('uptime_s', '--')} s | "
                f"Heap {health.get('heap_free', '--')}/{health.get('heap_total', '--')} | "
                f"Tasks {health.get('task_count', '--')} | "
                f"ADS CRC {ads.get('crc_error', '--')} "
                f"Dup {ads.get('duplicate', '--')} "
                f"Drop {ads.get('transient_drop', '--')}"
            )
        else:
            self.health_stack_value.setText("--")
            self.health_summary_label.setText("等待 ESP32 健康包")

        count = len(self.health_history.samples) if hasattr(self, "health_history") else 0
        self.health_record_count_value.setText(str(count))
        if sample is None:
            self.health_latest_time_label.setText("最近更新：--")
        else:
            self.health_latest_time_label.setText(
                f"最近更新：{sample.host_time.strftime('%H:%M:%S')}"
            )

    def _health_refresh_charts(self) -> None:
        samples = list(self.health_history.chart_samples(self.health_chart_limit))
        xs = [sample.elapsed_s for sample in samples]
        self.health_temp_curve.setData(xs, [_nan_none(sample.temp_c) for sample in samples])
        self.health_heap_curve.setData(xs, [_nan_none(sample.heap_free_pct) for sample in samples])
        self.health_loop_gap_curve.setData(
            xs, [_nan_none(sample.loop_gap_active_max_us) for sample in samples]
        )
        self.health_angle_age_curve.setData(xs, [_nan_none(sample.angle_age_ms) for sample in samples])
        self.health_rtt_curve.setData(xs, [_nan_none(sample.command_rtt_ms) for sample in samples])

    def _health_clear_history(self) -> None:
        if self.health_recording_active:
            QMessageBox.warning(self, "监测进行中", "请先停止当前健康监测，再清空记录。")
            return
        self.health_history.clear()
        self._health_refresh_all()
        self.log("[健康监控] 当前会话记录已清空")

    def _health_export_csv(self) -> None:
        default_name = datetime.now().strftime("health_%Y%m%d_%H%M%S.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出健康监控 CSV",
            default_name,
            "CSV 文件 (*.csv)",
        )
        if not file_path:
            return
        try:
            self.health_history.export_csv(file_path)
            self.log(f"[健康监控] CSV 已保存: {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"保存健康监控 CSV 失败: {exc}")

    def _health_save_chart_png(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, "health_chart_area"):
            QMessageBox.warning(self, "保存失败", "缺少 pyqtgraph，无法保存图表。")
            return
        default_name = datetime.now().strftime("health_charts_%Y%m%d_%H%M%S.png")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存健康监控图表",
            default_name,
            "PNG 图片 (*.png)",
        )
        if not file_path:
            return
        pixmap = self.health_chart_area.grab()
        if pixmap.save(file_path, "PNG"):
            self.log(f"[健康监控] 图表 PNG 已保存: {file_path}")
        else:
            QMessageBox.critical(self, "保存失败", "保存健康监控图表 PNG 失败。")


def _format_unit(value, unit: str, digits: int) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.{digits}f} {unit}"
    return f"{value} {unit}"


def _format_count(value) -> str:
    return "--" if value is None else str(int(value))


def _nan_none(value):
    if value is None:
        return float("nan")
    return value


def _extract_named_int(text: str, key: str):
    prefix = f"{key}="
    for part in text.replace(":", ",", 1).split(","):
        if part.startswith(prefix):
            try:
                return int(part[len(prefix) :])
            except ValueError:
                return None
    return None


def _extract_named_text(text: str, key: str):
    prefix = f"{key}="
    for part in text.replace(":", ",", 1).split(","):
        if part.startswith(prefix):
            return part[len(prefix) :]
    return None
