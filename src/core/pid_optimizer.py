"""
PID参数优化器 - 贝叶斯优化算法 + 非线性惩罚机制

特点:
1. 使用高斯过程回归建模参数-得分关系
2. 采集函数(EI)平衡探索与利用
3. 非线性惩罚：超调超过阈值时得分断崖式下跌
4. 样本效率高，通常20-30次迭代即可收敛
"""
import time
import struct
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple
from enum import Enum
import numpy as np

from PySide6.QtCore import QObject, Signal, QTimer

# 尝试导入贝叶斯优化库
try:
    from skopt import Optimizer
    from skopt.space import Real
    from skopt.learning import GaussianProcessRegressor
    from skopt.learning.gaussian_process.kernels import Matern
    SKOPT_AVAILABLE = True
except ImportError:
    SKOPT_AVAILABLE = False
    print("警告: scikit-optimize 未安装，将使用模式搜索算法")


class OptimizerState(Enum):
    """优化器状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_RESULT = "waiting_result"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class PIDParams:
    """PID参数"""
    Kp: float = 0.14
    Ki: float = 0.015
    Kd: float = 0.06
    output_min: float = 1.0
    output_max: float = 8.0
    
    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.Kp, self.Ki, self.Kd)
    
    def to_array(self) -> np.ndarray:
        return np.array([self.Kp, self.Ki, self.Kd])
    
    @classmethod
    def from_array(cls, arr: np.ndarray, output_min: float = 1.0, output_max: float = 8.0):
        return cls(Kp=float(arr[0]), Ki=float(arr[1]), Kd=float(arr[2]), 
                   output_min=output_min, output_max=output_max)
    
    def to_command(self) -> str:
        """生成下位机配置指令"""
        return f"PIDCFG:{self.Kp:.4f},{self.Ki:.5f},{self.Kd:.4f},{self.output_min:.1f},{self.output_max:.1f}\r\n"
    
    def copy(self) -> 'PIDParams':
        return PIDParams(self.Kp, self.Ki, self.Kd, self.output_min, self.output_max)


@dataclass
class TestResult:
    """单轮测试结果（从下位机接收）"""
    motor_id: int = 0
    run_index: int = 0
    total_runs: int = 0
    convergence_time_ms: int = 0
    max_overshoot: float = 0.0      # 度
    final_error: float = 0.0        # 度
    oscillation_count: int = 0
    smoothness_score: int = 0       # 0-100
    startup_jerk: float = 0.0
    total_score: int = 0            # 0-100 (下位机计算)


@dataclass
class OptimizationRecord:
    """优化记录"""
    params: PIDParams
    test_results: List[TestResult] = field(default_factory=list)
    avg_score: float = 0.0
    adjusted_score: float = 0.0     # 应用惩罚后的得分
    convergence_rsd: float = 0.0
    max_overshoot: float = 0.0      # 最大过冲
    timestamp: float = 0.0
    
    def calculate_avg_score(self):
        if self.test_results:
            self.avg_score = sum(r.total_score for r in self.test_results) / len(self.test_results)
    
    def calculate_convergence_rsd(self) -> float:
        """计算收敛时间的相对标准偏差"""
        if len(self.test_results) < 2:
            self.convergence_rsd = 0.0
            return 0.0
        
        conv_times = [r.convergence_time_ms for r in self.test_results]
        mean = sum(conv_times) / len(conv_times)
        if mean == 0:
            self.convergence_rsd = 0.0
            return 0.0
        
        variance = sum((t - mean) ** 2 for t in conv_times) / len(conv_times)
        std = variance ** 0.5
        self.convergence_rsd = (std / mean) * 100.0
        return self.convergence_rsd
    
    def calculate_max_overshoot(self) -> float:
        """计算所有测试中的最大过冲"""
        if self.test_results:
            self.max_overshoot = max(abs(r.max_overshoot) for r in self.test_results)
        return self.max_overshoot


class NonlinearPenalty:
    """
    非线性惩罚计算器
    
    惩罚策略:
    - 过冲 < 0.5°: 无惩罚
    - 过冲 0.5° - 1.0°: 轻微惩罚 (线性)
    - 过冲 1.0° - 2.0°: 中等惩罚 (二次)
    - 过冲 > 2.0°: 断崖式惩罚 (指数)
    """
    
    # 过冲阈值
    OVERSHOOT_SAFE = 0.5        # 安全阈值
    OVERSHOOT_WARNING = 1.0     # 警告阈值
    OVERSHOOT_CRITICAL = 2.0    # 临界阈值
    
    # 振荡惩罚
    OSCILLATION_THRESHOLD = 3   # 振荡次数阈值
    
    # RSD惩罚
    RSD_THRESHOLD = 30.0        # RSD阈值 (%)
    
    @classmethod
    def calculate_penalty(cls, record: OptimizationRecord) -> float:
        """
        计算综合惩罚系数 (0-1, 1表示无惩罚)
        
        Returns:
            惩罚后的得分乘数
        """
        penalty = 1.0
        
        # 1. 过冲惩罚 (最重要)
        max_ovs = record.max_overshoot
        if max_ovs > cls.OVERSHOOT_CRITICAL:
            # 断崖式惩罚: 指数衰减
            excess = max_ovs - cls.OVERSHOOT_CRITICAL
            penalty *= math.exp(-excess * 2.0)  # 每超过1度，得分降为原来的13.5%
        elif max_ovs > cls.OVERSHOOT_WARNING:
            # 二次惩罚
            excess = (max_ovs - cls.OVERSHOOT_WARNING) / (cls.OVERSHOOT_CRITICAL - cls.OVERSHOOT_WARNING)
            penalty *= (1.0 - 0.5 * excess * excess)  # 最多降50%
        elif max_ovs > cls.OVERSHOOT_SAFE:
            # 线性惩罚
            excess = (max_ovs - cls.OVERSHOOT_SAFE) / (cls.OVERSHOOT_WARNING - cls.OVERSHOOT_SAFE)
            penalty *= (1.0 - 0.1 * excess)  # 最多降10%
        
        # 2. 振荡惩罚
        if record.test_results:
            avg_osc = sum(r.oscillation_count for r in record.test_results) / len(record.test_results)
            if avg_osc > cls.OSCILLATION_THRESHOLD:
                excess = avg_osc - cls.OSCILLATION_THRESHOLD
                penalty *= max(0.5, 1.0 - 0.1 * excess)  # 每多振荡1次，降10%，最多降50%
        
        # 3. RSD惩罚 (一致性)
        if record.convergence_rsd > cls.RSD_THRESHOLD:
            excess = (record.convergence_rsd - cls.RSD_THRESHOLD) / 100.0
            penalty *= max(0.7, 1.0 - excess)  # 最多降30%
        
        return max(0.01, penalty)  # 最低保留1%
    
    @classmethod
    def apply_penalty(cls, record: OptimizationRecord) -> float:
        """应用惩罚并返回调整后的得分"""
        record.calculate_avg_score()
        record.calculate_convergence_rsd()
        record.calculate_max_overshoot()
        
        penalty = cls.calculate_penalty(record)
        record.adjusted_score = record.avg_score * penalty
        
        return record.adjusted_score


class BayesianPIDOptimizer(QObject):
    """
    贝叶斯PID优化器
    
    使用高斯过程回归 + Expected Improvement采集函数
    """
    
    # 信号
    progress_updated = Signal(int, int, str)
    params_updated = Signal(dict)
    result_received = Signal(dict)
    optimization_finished = Signal(dict)
    score_updated = Signal(float, float)
    state_changed = Signal(str)
    error_occurred = Signal(str)
    
    # 参数边界
    PARAM_BOUNDS = {
        'Kp': (0.05, 0.5),
        'Ki': (0.001, 0.1),
        'Kd': (0.01, 0.2)
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 优化配置
        self.max_iterations = 25        # 贝叶斯优化通常需要更少迭代
        self.n_initial_points = 5       # 初始随机采样点数
        self.test_runs_per_param = 5    # 每组参数测试次数
        self.test_angle = 45.0
        self.test_motor = 'X'
        
        # 状态
        self.state = OptimizerState.IDLE
        self._stop_requested = False
        self._pause_requested = False
        
        # 优化数据
        self.current_params: Optional[PIDParams] = None
        self.best_params: Optional[PIDParams] = None
        self.best_score: float = 0.0
        self.current_iteration: int = 0
        
        # 贝叶斯优化器
        self._optimizer: Optional[Optimizer] = None
        self._X_observed: List[List[float]] = []  # 已观测的参数
        self._y_observed: List[float] = []        # 已观测的得分（负值，因为skopt最小化）
        
        # 历史记录
        self.history: List[OptimizationRecord] = []
        self.pending_results: List[TestResult] = []
        
        # 串口回调
        self._send_command: Optional[Callable[[str], bool]] = None
        
        # 超时定时器
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._result_timeout = 90000  # 90秒超时（考虑2s间隔）
    
    def set_send_callback(self, callback: Callable[[str], bool]):
        self._send_command = callback
    
    def configure(self, **kwargs):
        """配置优化参数"""
        if 'max_iterations' in kwargs:
            self.max_iterations = kwargs['max_iterations']
        if 'n_initial_points' in kwargs:
            self.n_initial_points = kwargs['n_initial_points']
        if 'test_runs' in kwargs:
            self.test_runs_per_param = kwargs['test_runs']
        if 'test_angle' in kwargs:
            self.test_angle = kwargs['test_angle']
        if 'test_motor' in kwargs:
            self.test_motor = kwargs['test_motor']
    
    def _init_optimizer(self):
        """初始化贝叶斯优化器"""
        if not SKOPT_AVAILABLE:
            return False
        
        # 定义搜索空间
        space = [
            Real(self.PARAM_BOUNDS['Kp'][0], self.PARAM_BOUNDS['Kp'][1], name='Kp'),
            Real(self.PARAM_BOUNDS['Ki'][0], self.PARAM_BOUNDS['Ki'][1], name='Ki'),
            Real(self.PARAM_BOUNDS['Kd'][0], self.PARAM_BOUNDS['Kd'][1], name='Kd'),
        ]
        
        # 创建优化器
        self._optimizer = Optimizer(
            dimensions=space,
            base_estimator=GaussianProcessRegressor(
                kernel=Matern(nu=2.5),
                normalize_y=True,
                noise="gaussian",
                n_restarts_optimizer=2
            ),
            n_initial_points=self.n_initial_points,
            acq_func="EI",  # Expected Improvement
            acq_optimizer="auto",
            random_state=42
        )
        
        self._X_observed = []
        self._y_observed = []
        
        return True
    
    def start(self, initial_params: Optional[PIDParams] = None):
        """开始优化"""
        if self.state == OptimizerState.RUNNING:
            return
        
        if not self._send_command:
            self.error_occurred.emit("未设置串口发送回调")
            return
        
        self._stop_requested = False
        self._pause_requested = False
        
        # 初始化贝叶斯优化器
        if SKOPT_AVAILABLE:
            if not self._init_optimizer():
                self.error_occurred.emit("初始化贝叶斯优化器失败")
                return
        
        # 初始化参数
        if initial_params:
            self.current_params = initial_params.copy()
        else:
            self.current_params = PIDParams()
        
        self.best_params = self.current_params.copy()
        self.best_score = 0.0
        self.current_iteration = 0
        self.history.clear()
        
        self._set_state(OptimizerState.RUNNING)
        self.progress_updated.emit(0, self.max_iterations, "开始贝叶斯优化...")
        
        # 获取第一个采样点
        self._get_next_point()
    
    def _get_next_point(self):
        """获取下一个采样点"""
        if self._stop_requested:
            return
        
        if SKOPT_AVAILABLE and self._optimizer:
            # 使用贝叶斯优化获取下一个点
            next_point = self._optimizer.ask()
            self.current_params = PIDParams(
                Kp=float(next_point[0]),
                Ki=float(next_point[1]),
                Kd=float(next_point[2])
            )
        else:
            # 回退到随机搜索
            self.current_params = PIDParams(
                Kp=np.random.uniform(*self.PARAM_BOUNDS['Kp']),
                Ki=np.random.uniform(*self.PARAM_BOUNDS['Ki']),
                Kd=np.random.uniform(*self.PARAM_BOUNDS['Kd'])
            )
        
        self._evaluate_current_params()
    
    def stop(self):
        """停止优化"""
        self._stop_requested = True
        self._timeout_timer.stop()
        
        if self._send_command:
            self._send_command("PIDTESTSTOP\r\n")
        
        self._set_state(OptimizerState.IDLE)
        self.progress_updated.emit(self.current_iteration, self.max_iterations, "优化已停止")
    
    def pause(self):
        self._pause_requested = True
        self._set_state(OptimizerState.PAUSED)
    
    def resume(self):
        if self.state == OptimizerState.PAUSED:
            self._pause_requested = False
            self._set_state(OptimizerState.RUNNING)
            self._continue_optimization()
    
    def _set_state(self, state: OptimizerState):
        self.state = state
        self.state_changed.emit(state.value)
    
    def _evaluate_current_params(self):
        """评估当前参数"""
        if self._stop_requested:
            return
        
        self.pending_results.clear()
        
        cmd = self.current_params.to_command()
        if not self._send_command(cmd):
            self.error_occurred.emit("发送PID参数失败")
            self.stop()
            return
        
        QTimer.singleShot(200, self._start_test)
    
    def _start_test(self):
        if self._stop_requested:
            return
        
        motor_idx = self.test_motor
        cmd = f"PIDTEST:{motor_idx},{self.test_angle:.1f},{self.test_runs_per_param}\r\n"
        
        if not self._send_command(cmd):
            self.error_occurred.emit("发送测试指令失败")
            self.stop()
            return
        
        self._set_state(OptimizerState.WAITING_RESULT)
        self.params_updated.emit({
            'Kp': self.current_params.Kp,
            'Ki': self.current_params.Ki,
            'Kd': self.current_params.Kd,
            'iteration': self.current_iteration
        })
        
        self._timeout_timer.start(self._result_timeout)
    
    def on_test_result(self, result: TestResult):
        """接收测试结果"""
        if self.state != OptimizerState.WAITING_RESULT:
            return
        
        self.pending_results.append(result)
        self.result_received.emit({
            'run_index': result.run_index,
            'total_runs': result.total_runs,
            'score': result.total_score,
            'convergence_time': result.convergence_time_ms,
            'overshoot': result.max_overshoot,
            'smoothness': result.smoothness_score
        })
        
        if len(self.pending_results) >= self.test_runs_per_param:
            self._timeout_timer.stop()
            self._on_evaluation_complete()
    
    def on_test_done(self):
        if self.state == OptimizerState.WAITING_RESULT:
            self._timeout_timer.stop()
            self._on_evaluation_complete()
    
    def _on_timeout(self):
        self.error_occurred.emit("测试超时")
        if self.pending_results:
            self._on_evaluation_complete()
        else:
            self._continue_optimization()
    
    def _on_evaluation_complete(self):
        """评估完成，应用惩罚并更新模型"""
        if not self.pending_results:
            self._continue_optimization()
            return
        
        # 创建记录
        record = OptimizationRecord(
            params=self.current_params.copy(),
            test_results=self.pending_results.copy(),
            timestamp=time.time()
        )
        
        # 应用非线性惩罚
        adjusted_score = NonlinearPenalty.apply_penalty(record)
        self.history.append(record)
        
        # 更新贝叶斯优化器
        if SKOPT_AVAILABLE and self._optimizer:
            x = [self.current_params.Kp, self.current_params.Ki, self.current_params.Kd]
            y = -adjusted_score  # 负值，因为skopt最小化
            self._optimizer.tell(x, y)
            self._X_observed.append(x)
            self._y_observed.append(y)
        
        self.score_updated.emit(adjusted_score, self.best_score)
        
        # 更新最优参数
        if adjusted_score > self.best_score:
            self.best_score = adjusted_score
            self.best_params = self.current_params.copy()
            
            penalty_info = ""
            if record.max_overshoot > NonlinearPenalty.OVERSHOOT_SAFE:
                penalty_info = f" (过冲惩罚: {record.max_overshoot:.2f}°)"
            
            self.progress_updated.emit(
                self.current_iteration,
                self.max_iterations,
                f"发现更优参数! 得分: {adjusted_score:.1f}{penalty_info}"
            )
        
        self._set_state(OptimizerState.RUNNING)
        self._continue_optimization()
    
    def _continue_optimization(self):
        """继续优化"""
        if self._stop_requested:
            return
        
        if self._pause_requested:
            return
        
        self.current_iteration += 1
        
        if self.current_iteration >= self.max_iterations:
            self._finish_optimization()
            return
        
        # 获取下一个采样点
        self.progress_updated.emit(
            self.current_iteration,
            self.max_iterations,
            f"贝叶斯采样 {self.current_iteration}/{self.max_iterations}"
        )
        
        self._get_next_point()
    
    def _finish_optimization(self):
        self._set_state(OptimizerState.FINISHED)
        
        result = {
            'best_params': {
                'Kp': self.best_params.Kp,
                'Ki': self.best_params.Ki,
                'Kd': self.best_params.Kd,
                'output_min': self.best_params.output_min,
                'output_max': self.best_params.output_max
            },
            'best_score': self.best_score,
            'iterations': self.current_iteration,
            'history_count': len(self.history)
        }
        
        self.progress_updated.emit(
            self.current_iteration,
            self.max_iterations,
            f"优化完成! 最优得分: {self.best_score:.1f}"
        )
        
        self.optimization_finished.emit(result)
    
    def apply_best_params(self) -> bool:
        if not self.best_params or not self._send_command:
            return False
        return self._send_command(self.best_params.to_command())
    
    def get_history_summary(self) -> List[Dict]:
        """获取历史记录摘要"""
        summary = []
        for i, record in enumerate(self.history):
            avg_conv_time = 0
            if record.test_results:
                avg_conv_time = sum(r.convergence_time_ms for r in record.test_results) / len(record.test_results)
            
            summary.append({
                'index': i,
                'Kp': record.params.Kp,
                'Ki': record.params.Ki,
                'Kd': record.params.Kd,
                'avg_score': record.avg_score,
                'adjusted_score': record.adjusted_score,
                'max_overshoot': record.max_overshoot,
                'avg_conv_time': avg_conv_time,
                'convergence_rsd': record.convergence_rsd,
                'runs': len(record.test_results)
            })
        return summary


# 保持向后兼容的别名
PatternSearchOptimizer = BayesianPIDOptimizer


def parse_test_result_packet(data: bytes) -> Optional[TestResult]:
    """解析测试结果二进制数据包"""
    if len(data) < 18:
        return None
    
    if data[0] != 0x55 or data[1] != 0xBB:
        return None
    
    try:
        result = TestResult()
        result.motor_id = data[2]
        result.run_index = data[3]
        result.total_runs = data[4]
        result.convergence_time_ms = struct.unpack('<H', data[5:7])[0]
        result.max_overshoot = struct.unpack('<h', data[7:9])[0] / 100.0
        result.final_error = struct.unpack('<h', data[9:11])[0] / 100.0
        result.oscillation_count = data[11]
        result.smoothness_score = data[12]
        result.startup_jerk = struct.unpack('<H', data[13:15])[0] / 100.0
        result.total_score = data[15]
        
        checksum = 0
        for i in range(2, 16):
            checksum ^= data[i]
        
        if checksum != data[16]:
            return None
        
        if data[17] != 0x0A:
            return None
        
        return result
    except Exception:
        return None


def parse_test_result_text(line: str) -> Optional[TestResult]:
    """解析测试结果文本格式"""
    if not line.startswith("PIDTEST_RESULT:"):
        return None
    
    try:
        parts = line[15:].split(',')
        result = TestResult()
        
        motor_char = parts[0]
        result.motor_id = {'X': 0, 'Y': 1, 'Z': 2, 'A': 3}.get(motor_char, 0)
        
        for part in parts[1:]:
            key, value = part.split('=')
            if key == 'run':
                result.run_index = int(value)
            elif key == 'conv':
                result.convergence_time_ms = int(value)
            elif key == 'ovs':
                result.max_overshoot = float(value)
            elif key == 'err':
                result.final_error = float(value)
            elif key == 'osc':
                result.oscillation_count = int(value)
            elif key == 'smooth':
                result.smoothness_score = int(value)
            elif key == 'score':
                result.total_score = int(value)
        
        return result
    except Exception:
        return None
