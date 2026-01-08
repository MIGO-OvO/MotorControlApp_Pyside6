"""PID数据处理 Mixin 模块。

该模块提供PID数据处理相关功能，包括：
- PID消息处理（开始/完成/超时/失败）
- PID二进制数据包处理
- 图表批量更新
- 测试结果处理
- 角度数据包处理

Note:
    此模块设计为 Mixin 类，需要与 QMainWindow 子类一起使用。
"""

import time
from typing import Dict, Any, Optional

from src.core.pid_analyzer import PIDStatus


class PIDDataMixin:
    """PID数据处理功能 Mixin。

    提供PID消息解析、数据包处理和图表更新功能。

    Attributes:
        pid_analyzer: PID分析器实例
        pid_analysis_chart: PID分析图表
        pid_stats_panel: PID统计面板
        pid_update_timer: PID更新定时器
    """

    def handle_pid_message(self, data: str) -> None:
        """处理 PID 定位模式文本消息（开始/完成/超时/失败）。

        Args:
            data: PID消息字符串
        """
        if data.startswith("PID_START"):
            info = data.replace("PID_START:", "")
            self.log(f"PID定位开始: {info}")

            try:
                # 格式: X,delta=360.0,dir=F,prec=0.1,absTarget=360.0
                parts = info.split(",")
                motor = parts[0].strip()
                
                params = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        params[key.strip()] = val.strip()
                
                target = float(params["absTarget"]) % 360
                precision = float(params["prec"])

                self.pid_analyzer.start_pid_move(motor, target, precision)
                self.pid_analysis_chart.clear_motor(motor)
                self.pid_stats_panel.update_status(motor, "运行中", "#2ca02c")
                self.pid_stats_panel.update_target(motor, target)

                if not self.pid_update_timer.isActive():
                    self.pid_update_timer.start()
            except Exception as e:
                self.log(f"解析 PID_START 失败: {e}")

        elif data.startswith("PID_DONE"):
            info = data.replace("PID_DONE:", "")
            self.log(f"PID定位完成: {info}")
            self.status_bar.showMessage(f"定位完成: {info}")

            try:
                # 格式: X,abs=360.0,err=0.05
                parts = info.split(",")
                motor = parts[0].strip()
                
                params = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        params[key.strip()] = val.strip()
                
                final_angle = float(params["abs"]) % 360
                final_error = float(params["err"])

                self.pid_analyzer.finish_pid_move(motor, PIDStatus.DONE, final_angle, final_error)
                self.pid_stats_panel.update_status(motor, "已完成", "#1f77b4")
                self.pid_stats_panel.update_error(motor, final_error)
                self._update_pid_history_stats()

                self._notify_automation_pid_complete(motor)

                if not self.pid_analyzer.get_active_motors():
                    self.pid_update_timer.stop()
            except Exception as e:
                self.log(f"解析 PID_DONE 失败: {e}")

        elif data.startswith("PID_TIMEOUT"):
            info = data.replace("PID_TIMEOUT:", "")
            self.log(f"PID定位超时: {info}")
            self.status_bar.showMessage(f"定位超时: {info}")

            try:
                # 格式: X,abs=360.0,err=5.0
                parts = info.split(",")
                motor = parts[0].strip()
                
                params = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        params[key.strip()] = val.strip()
                
                final_angle = float(params["abs"]) % 360
                final_error = float(params["err"])

                self.pid_analyzer.finish_pid_move(motor, PIDStatus.TIMEOUT, final_angle, final_error)
                self.pid_stats_panel.update_status(motor, "超时", "#ff7f0e")
                self._update_pid_history_stats()

                self._notify_automation_pid_complete(motor)

                if not self.pid_analyzer.get_active_motors():
                    self.pid_update_timer.stop()
            except Exception as e:
                self.log(f"解析 PID_TIMEOUT 失败: {e}")

        elif data.startswith("PID_FAIL"):
            info = data.replace("PID_FAIL:", "")
            self.log(f"PID定位失败: {info}")
            self.status_bar.showMessage(f"定位失败: {info}")

            try:
                parts = info.split("=")
                motor = parts[0].strip()
                self.pid_analyzer.finish_pid_move(motor, PIDStatus.FAILED, 0, 0)
                self.pid_stats_panel.update_status(motor, "失败", "#d62728")
                self._update_pid_history_stats()

                self._notify_automation_pid_complete(motor)

                if not self.pid_analyzer.get_active_motors():
                    self.pid_update_timer.stop()
            except Exception as e:
                self.log(f"解析 PID_FAIL 失败: {e}")

        elif data.startswith("PID_STOP"):
            self.log("PID定位已停止")
            self.pid_analyzer.stop_all()

    def _notify_automation_pid_complete(self, motor: str) -> None:
        """通知自动化线程 PID 完成。

        Args:
            motor: 完成的电机名称
        """
        try:
            if self.automation_thread and self.automation_thread.isRunning():
                self.automation_thread.notify_pid_complete(motor)
        except Exception:
            pass

    def handle_pid_packet(self, packet: dict) -> None:
        """处理 PID 二进制数据包 - 缓冲模式，由定时器批量更新图表。

        Args:
            packet: PID数据包
        """
        try:
            if getattr(self, "_closing", False):
                return

            if not hasattr(self, "pid_analyzer") or self.pid_analyzer is None:
                return

            motor = packet.get("motor", "X")

            is_new_record = self.pid_analyzer.update_from_packet(packet)

            if is_new_record:
                if hasattr(self, "pid_analysis_chart") and self.pid_analysis_chart is not None:
                    self.pid_analysis_chart.clear_motor(motor)

            if motor in self.pid_analyzer.active_records:
                record = self.pid_analyzer.active_records[motor]
                relative_time = time.time() - record.start_time
            else:
                relative_time = 0

            if hasattr(self, "_pending_pid_packets"):
                if len(self._pending_pid_packets) > 1000:
                    self._pending_pid_packets = self._pending_pid_packets[-500:]
                self._pending_pid_packets.append((motor, packet, relative_time))

            if hasattr(self, "pid_stats_panel") and self.pid_stats_panel is not None:
                self.pid_stats_panel.update_from_packet(motor, packet)
        except RuntimeError as e:
            if "deleted" in str(e).lower() or "C++ object" in str(e):
                return
            print(f"handle_pid_packet error: {e}")
        except Exception as e:
            print(f"handle_pid_packet error: {e}")

    def _batch_update_charts(self) -> None:
        """批量更新图表 - 由定时器调用，降低UI刷新频率。"""
        try:
            if getattr(self, "_closing", False):
                return

            if not hasattr(self, "_pending_pid_packets") or not self._pending_pid_packets:
                return

            packets = self._pending_pid_packets[:100]
            del self._pending_pid_packets[:len(packets)]

            if not packets:
                return

            if getattr(self, "_closing", False):
                return

            if hasattr(self, "pid_analysis_chart") and self.pid_analysis_chart is not None:
                for motor, packet, relative_time in packets:
                    if getattr(self, "_closing", False):
                        return
                    self.pid_analysis_chart.add_data_only(motor, packet, relative_time)

                if not getattr(self, "_closing", False):
                    self.pid_analysis_chart.refresh_all_curves()
        except RuntimeError as e:
            if "deleted" in str(e).lower() or "C++ object" in str(e):
                return
        except Exception as e:
            print(f"_batch_update_charts error: {e}")

    def handle_test_result_packet(self, result: dict) -> None:
        """处理 PID 测试结果二进制数据包 (0xBB)。

        Args:
            result: 包含测试结果的字典
        """
        try:
            if getattr(self, "_closing", False):
                return

            from src.core.pid_optimizer import TestResult

            test_result = TestResult(
                motor_id=result.get("motor_id", 0),
                run_index=result.get("run_index", 0),
                total_runs=result.get("total_runs", 0),
                convergence_time_ms=result.get("convergence_time_ms", 0),
                max_overshoot=result.get("max_overshoot", 0.0),
                final_error=result.get("final_error", 0.0),
                oscillation_count=result.get("oscillation_count", 0),
                smoothness_score=result.get("smoothness_score", 0),
                startup_jerk=result.get("startup_jerk", 0.0),
                total_score=result.get("total_score", 0),
            )

            if hasattr(self, "pid_optimizer") and self.pid_optimizer:
                self.pid_optimizer.on_test_result(test_result)

            if getattr(self, "_single_test_active", False):
                if not hasattr(self, "_single_test_results"):
                    self._single_test_results = []
                self._single_test_results.append(test_result)

            motor_names = ["X", "Y", "Z", "A"]
            motor = motor_names[result.get("motor_id", 0)]
            self.log(
                f"[测试结果] {motor} 轮次{result.get('run_index', 0)}: "
                f"得分={result.get('total_score', 0)}, "
                f"收敛={result.get('convergence_time_ms', 0)}ms"
            )
        except Exception as e:
            print(f"handle_test_result_packet error: {e}")

    def handle_angle_packet(self, angles: dict) -> None:
        """处理角度二进制数据包 (0xCC)。

        Args:
            angles: 包含四个电机角度的字典
        """
        try:
            if getattr(self, "_closing", False):
                return

            current_angles = {}
            for motor in ["X", "Y", "Z", "A"]:
                raw_angle = angles.get(motor, 0.0) % 360
                self.raw_angles[motor] = raw_angle
                offset = self.angle_offsets.get(motor, 0.0)
                relative_angle = (raw_angle - offset) % 360
                current_angles[motor] = relative_angle

            theoretical_deviations = {}
            theoretical_targets = {}
            realtime_deviations = {}

            for motor in ["X", "Y", "Z", "A"]:
                if motor not in self.active_motors:
                    theoretical_deviations[motor] = None
                    realtime_deviations[motor] = None
                    theoretical_targets[motor] = None
                    continue

                current = current_angles.get(motor, 0.0)

                if motor in self.pending_targets and self.pending_targets[motor] is not None:
                    realtime_dev = (current - self.pending_targets[motor]) % 360
                    realtime_dev = realtime_dev - 360 if realtime_dev > 180 else realtime_dev
                    realtime_deviations[motor] = realtime_dev
                else:
                    realtime_deviations[motor] = None

                if self.initial_angle_base.get(motor) is not None:
                    theoretical_target = (
                        self.initial_angle_base[motor] + self.accumulated_rotation[motor]
                    ) % 360
                    theoretical_targets[motor] = theoretical_target
                    theoretical_dev = (current - theoretical_target) % 360
                    if theoretical_dev > 180:
                        theoretical_dev -= 360
                    theoretical_deviations[motor] = theoretical_dev
                else:
                    theoretical_deviations[motor] = None
                    theoretical_targets[motor] = None

            if self.running_mode == "auto" and self.auto_calibration_enabled:
                for motor in self.active_motors:
                    if theoretical_deviations[motor] is not None:
                        self.theoretical_deviations[motor] = theoretical_deviations[motor]

            self.current_angles.update(current_angles)
            filtered_data = {
                "current": current_angles,
                "theoretical": {
                    k: v for k, v in theoretical_deviations.items() if k in self.active_motors
                },
                "realtime": {
                    k: v for k, v in realtime_deviations.items() if k in self.active_motors
                },
                "targets": {
                    k: v for k, v in theoretical_targets.items() if k in self.active_motors
                },
            }
            self.angle_update.emit(filtered_data)
        except Exception as e:
            print(f"handle_angle_packet error: {e}")

    def format_number(self, value: float) -> str:
        """格式化数值，去除末尾多余的零和小数点。

        Args:
            value: 要格式化的数值

        Returns:
            格式化后的字符串
        """
        s = "{:.3f}".format(value).rstrip("0").rstrip(".")
        return s
