"""
PID 控制质量分析器
用于采集、分析和统计 PID 控制过程数据
支持二进制数据包解析
"""

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class PIDStatus(Enum):
    """PID 运动状态"""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    TIMEOUT = "timeout"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class PIDRunRecord:
    """单次 PID 运动记录"""

    motor: str
    target_angle: float
    precision: float = 0.5
    start_time: float = 0.0
    end_time: Optional[float] = None
    # 历史数据: [(相对时间, 值)] - 使用deque限制大小防止内存泄漏
    error_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    angle_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    theo_angle_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    output_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    load_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    final_angle: Optional[float] = None
    final_error: Optional[float] = None
    status: PIDStatus = PIDStatus.IDLE

    @property
    def duration(self) -> Optional[float]:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

    @property
    def is_successful(self) -> bool:
        return self.status == PIDStatus.DONE

    @property
    def convergence_time(self) -> Optional[float]:
        if not self.error_history:
            return None
        for ts, err in self.error_history:
            if abs(err) < self.precision:
                return ts
        return None


@dataclass
class MotorPIDStats:
    """单个电机的 PID 统计数据"""

    total_runs: int = 0
    successful_runs: int = 0
    timeout_runs: int = 0
    failed_runs: int = 0
    total_convergence_time: float = 0.0
    min_convergence_time: Optional[float] = None
    max_convergence_time: Optional[float] = None
    total_final_error: float = 0.0
    max_final_error: float = 0.0
    # 误差分布统计 - 使用deque限制大小防止内存泄漏
    error_distribution: deque = field(default_factory=lambda: deque(maxlen=500))

    @property
    def success_rate(self) -> float:
        return (self.successful_runs / self.total_runs * 100) if self.total_runs > 0 else 0.0

    @property
    def avg_convergence_time(self) -> float:
        return (
            (self.total_convergence_time / self.successful_runs)
            if self.successful_runs > 0
            else 0.0
        )

    @property
    def avg_final_error(self) -> float:
        return (self.total_final_error / self.successful_runs) if self.successful_runs > 0 else 0.0


class PIDAnalyzer:
    """PID 控制质量分析器"""

    # 显示用数据缓冲区大小（用于UI图表，保持较小以确保性能）
    DISPLAY_BUFFER_SIZE = 500
    # 导出用数据缓冲区大小（用于数据导出，可以较大）
    EXPORT_BUFFER_SIZE = 20000

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.active_records: Dict[str, PIDRunRecord] = {}
        self.history: Dict[str, deque] = {
            motor: deque(maxlen=max_history) for motor in ["X", "Y", "Z", "A"]
        }
        self.stats: Dict[str, MotorPIDStats] = {
            motor: MotorPIDStats() for motor in ["X", "Y", "Z", "A"]
        }

        # 实时数据 - 显示用（小缓冲区，用于UI图表）
        self.realtime_error: Dict[str, deque] = {
            motor: deque(maxlen=self.DISPLAY_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.realtime_output: Dict[str, deque] = {
            motor: deque(maxlen=self.DISPLAY_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.realtime_position: Dict[str, deque] = {
            motor: deque(maxlen=self.DISPLAY_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.realtime_load: Dict[str, deque] = {
            motor: deque(maxlen=self.DISPLAY_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }

        # 导出用数据（大缓冲区，用于数据导出）
        self.export_error: Dict[str, deque] = {
            motor: deque(maxlen=self.EXPORT_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.export_output: Dict[str, deque] = {
            motor: deque(maxlen=self.EXPORT_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.export_position: Dict[str, deque] = {
            motor: deque(maxlen=self.EXPORT_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }
        self.export_load: Dict[str, deque] = {
            motor: deque(maxlen=self.EXPORT_BUFFER_SIZE) for motor in ["X", "Y", "Z", "A"]
        }

    def start_pid_move(self, motor: str, target: float, precision: float = 0.5) -> None:
        """记录 PID 运动开始"""
        record = PIDRunRecord(
            motor=motor,
            target_angle=target,
            precision=precision,
            start_time=time.time(),
            status=PIDStatus.RUNNING,
        )
        self.active_records[motor] = record
        # 清空该电机的实时数据（显示用）
        self.realtime_error[motor].clear()
        self.realtime_output[motor].clear()
        self.realtime_position[motor].clear()
        self.realtime_load[motor].clear()
        # 清空该电机的导出数据
        self.export_error[motor].clear()
        self.export_output[motor].clear()
        self.export_position[motor].clear()
        self.export_load[motor].clear()

    def update_pid_status(
        self, motor: str, current_angle: float, error: float, rpm: Optional[float] = None
    ) -> None:
        """兼容旧版文本协议的更新方法"""
        if motor not in self.active_records:
            return

        record = self.active_records[motor]
        if record.status != PIDStatus.RUNNING:
            return

        relative_time = time.time() - record.start_time

        # 记录到历史
        record.error_history.append((relative_time, error))
        record.angle_history.append((relative_time, current_angle))
        if rpm is not None:
            record.output_history.append((relative_time, rpm))

        # 更新实时数据
        self.realtime_error[motor].append((relative_time, error))
        if rpm is not None:
            self.realtime_output[motor].append((relative_time, rpm))

    def update_from_packet(self, packet: dict) -> bool:
        """从二进制数据包更新数据

        Returns:
            bool: True 如果是新创建的记录（需要清空图表），False 如果是已有记录
        """
        motor = packet.get("motor", "X")
        is_new_record = False
        if motor not in self.active_records:
            # 如果没有活动记录，自动创建一个
            self.start_pid_move(motor, packet.get("target_angle", 0), 0.5)
            is_new_record = True

        record = self.active_records[motor]
        if record.status != PIDStatus.RUNNING:
            return is_new_record

        relative_time = time.time() - record.start_time

        target = packet.get("target_angle", 0)
        actual = packet.get("actual_angle", 0)
        theo = packet.get("theo_angle", 0)
        output = packet.get("pid_out", 0)
        error = packet.get("error", 0)

        # 计算负载偏差 = 理论角度 - 实际角度 (处理360°跨越)
        load = self._normalize_angle_diff(theo, actual)

        # 记录到历史（PIDRunRecord内部）
        record.error_history.append((relative_time, error))
        record.angle_history.append((relative_time, actual))
        record.theo_angle_history.append((relative_time, theo))
        record.output_history.append((relative_time, output))
        record.load_history.append((relative_time, load))

        # 更新实时数据（显示用，小缓冲区）
        self.realtime_error[motor].append((relative_time, error))
        self.realtime_output[motor].append((relative_time, output))
        # 位置追踪: (时间, 目标, 实际, 理论)
        self.realtime_position[motor].append((relative_time, target, actual, theo))
        self.realtime_load[motor].append((relative_time, load))

        # 更新导出数据（大缓冲区，用于数据导出）
        self.export_error[motor].append((relative_time, error))
        self.export_output[motor].append((relative_time, output))
        self.export_position[motor].append((relative_time, target, actual, theo))
        self.export_load[motor].append((relative_time, load))

        return is_new_record

    @staticmethod
    def _normalize_angle_diff(angle1: float, angle2: float) -> float:
        """计算两个角度的差值，处理360°跨越"""
        diff = angle1 - angle2
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        return diff

    def finish_pid_move(
        self, motor: str, status: PIDStatus, final_angle: float, final_error: float
    ) -> Optional[PIDRunRecord]:
        """完成 PID 运动"""
        if motor not in self.active_records:
            return None

        record = self.active_records.pop(motor)
        record.end_time = time.time()
        record.status = status
        record.final_angle = final_angle
        record.final_error = final_error

        self.history[motor].append(record)
        self._update_stats(motor, record)

        return record

    def stop_pid_move(self, motor: str) -> None:
        """停止 PID 运动"""
        if motor in self.active_records:
            record = self.active_records.pop(motor)
            record.status = PIDStatus.STOPPED
            record.end_time = time.time()

    def stop_all(self) -> None:
        """停止所有 PID 运动"""
        for motor in list(self.active_records.keys()):
            self.stop_pid_move(motor)

    def _update_stats(self, motor: str, record: PIDRunRecord) -> None:
        """更新统计数据"""
        stats = self.stats[motor]
        stats.total_runs += 1

        if record.status == PIDStatus.DONE:
            stats.successful_runs += 1

            conv_time = record.convergence_time
            if conv_time is not None:
                stats.total_convergence_time += conv_time
                if stats.min_convergence_time is None or conv_time < stats.min_convergence_time:
                    stats.min_convergence_time = conv_time
                if stats.max_convergence_time is None or conv_time > stats.max_convergence_time:
                    stats.max_convergence_time = conv_time

            if record.final_error is not None:
                abs_error = abs(record.final_error)
                stats.total_final_error += abs_error
                stats.error_distribution.append(abs_error)
                if abs_error > stats.max_final_error:
                    stats.max_final_error = abs_error

        elif record.status == PIDStatus.TIMEOUT:
            stats.timeout_runs += 1
        elif record.status == PIDStatus.FAILED:
            stats.failed_runs += 1

    def get_motor_status(self, motor: str) -> PIDStatus:
        """获取电机当前 PID 状态"""
        if motor in self.active_records:
            return self.active_records[motor].status
        return PIDStatus.IDLE

    def get_active_motors(self) -> List[str]:
        """获取当前活动的电机列表"""
        return [m for m, r in self.active_records.items() if r.status == PIDStatus.RUNNING]

    def get_realtime_error_data(self, motor: str) -> List[Tuple[float, float]]:
        return list(self.realtime_error[motor])

    def get_realtime_output_data(self, motor: str) -> List[Tuple[float, float]]:
        return list(self.realtime_output[motor])

    def get_realtime_position_data(self, motor: str) -> List[Tuple[float, float, float, float]]:
        """返回 [(时间, 目标角度, 实际角度, 理论角度)]"""
        return list(self.realtime_position[motor])

    def get_realtime_load_data(self, motor: str) -> List[Tuple[float, float]]:
        return list(self.realtime_load[motor])

    # ===== 导出数据获取方法（大缓冲区） =====

    def get_export_error_data(self, motor: str) -> List[Tuple[float, float]]:
        """获取导出用误差数据（最多20000个点）"""
        return list(self.export_error[motor])

    def get_export_output_data(self, motor: str) -> List[Tuple[float, float]]:
        """获取导出用输出数据（最多20000个点）"""
        return list(self.export_output[motor])

    def get_export_position_data(self, motor: str) -> List[Tuple[float, float, float, float]]:
        """获取导出用位置数据（最多20000个点）
        返回 [(时间, 目标角度, 实际角度, 理论角度)]
        """
        return list(self.export_position[motor])

    def get_export_load_data(self, motor: str) -> List[Tuple[float, float]]:
        """获取导出用负载数据（最多20000个点）"""
        return list(self.export_load[motor])

    def get_error_distribution(self, motor: str) -> List[float]:
        """获取误差分布数据（用于直方图）"""
        return list(self.stats[motor].error_distribution)

    def get_all_error_distribution(self) -> List[float]:
        """获取所有电机的误差分布"""
        all_errors = []
        for motor in ["X", "Y", "Z", "A"]:
            all_errors.extend(self.stats[motor].error_distribution)
        return all_errors

    def get_stats_summary(self, motor: str) -> Dict:
        """获取统计摘要"""
        stats = self.stats[motor]
        return {
            "total_runs": stats.total_runs,
            "success_rate": f"{stats.success_rate:.1f}%",
            "avg_convergence_time": f"{stats.avg_convergence_time:.2f}s",
            "min_convergence_time": (
                f"{stats.min_convergence_time:.2f}s" if stats.min_convergence_time else "N/A"
            ),
            "max_convergence_time": (
                f"{stats.max_convergence_time:.2f}s" if stats.max_convergence_time else "N/A"
            ),
            "avg_final_error": f"{stats.avg_final_error:.2f}°",
            "max_final_error": f"{stats.max_final_error:.2f}°",
            "timeout_count": stats.timeout_runs,
            "fail_count": stats.failed_runs,
        }

    def get_motor_stats(self) -> Dict[str, Dict[str, float]]:
        """获取面板显示用的电机统计数据。"""
        data: Dict[str, Dict[str, float]] = {}
        for motor, stats in self.stats.items():
            data[motor] = {
                "total_runs": stats.total_runs,
                "success_rate": stats.success_rate,
                "avg_convergence_time": stats.avg_convergence_time * 1000.0,
                "avg_final_error": stats.avg_final_error,
            }
        return data

    def clear_realtime_data(self, motor: Optional[str] = None) -> None:
        """清空实时数据（显示用）"""
        motors = [motor] if motor else ["X", "Y", "Z", "A"]
        for m in motors:
            self.realtime_error[m].clear()
            self.realtime_output[m].clear()
            self.realtime_position[m].clear()
            self.realtime_load[m].clear()

    def clear_export_data(self, motor: Optional[str] = None) -> None:
        """清空导出数据"""
        motors = [motor] if motor else ["X", "Y", "Z", "A"]
        for m in motors:
            self.export_error[m].clear()
            self.export_output[m].clear()
            self.export_position[m].clear()
            self.export_load[m].clear()

    def clear_history(self, motor: Optional[str] = None) -> None:
        """清空历史记录"""
        motors = [motor] if motor else ["X", "Y", "Z", "A"]
        for m in motors:
            self.history[m].clear()
            self.stats[m] = MotorPIDStats()

    def reset(self) -> None:
        """完全重置分析器"""
        self.active_records.clear()
        self.clear_realtime_data()
        self.clear_export_data()
        self.clear_history()
