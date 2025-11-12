"""
指令生成器
负责根据参数生成电机控制指令
"""
from typing import Dict, Any, Set, Optional
from ..config.constants import MOTOR_NAMES, DIRECTION_MAP, COMMAND_TERMINATOR


class CommandGenerator:
    """电机控制指令生成器"""
    
    def __init__(self):
        """初始化指令生成器"""
        self.active_motors: Set[str] = set(MOTOR_NAMES)
        self.pending_targets: Dict[str, Optional[float]] = {m: None for m in MOTOR_NAMES}
        self.expected_rotation: Dict[str, float] = {m: 0.0 for m in MOTOR_NAMES}
        self.current_angles: Dict[str, float] = {m: 0.0 for m in MOTOR_NAMES}
        
        # 自动模式相关
        self.initial_angle_base: Dict[str, Optional[float]] = {m: None for m in MOTOR_NAMES}
        self.accumulated_rotation: Dict[str, float] = {m: 0.0 for m in MOTOR_NAMES}
        self.expected_angles: Dict[str, float] = {m: 0.0 for m in MOTOR_NAMES}
        self.is_first_command = True
        
        # 校准相关
        self.theoretical_deviations: Dict[str, Optional[float]] = {m: None for m in MOTOR_NAMES}
        self.calibration_enabled = False
        self.calibration_amplitude = 1.0
    
    def set_current_angles(self, angles: Dict[str, float]) -> None:
        """
        设置当前角度
        
        Args:
            angles: 角度字典
        """
        self.current_angles.update(angles)
    
    def set_calibration(self, enabled: bool, amplitude: float = 1.0) -> None:
        """
        设置校准参数
        
        Args:
            enabled: 是否启用校准
            amplitude: 校准幅值
        """
        self.calibration_enabled = enabled
        self.calibration_amplitude = amplitude
    
    def set_theoretical_deviations(self, deviations: Dict[str, Optional[float]]) -> None:
        """
        设置理论偏差
        
        Args:
            deviations: 偏差字典
        """
        self.theoretical_deviations.update(deviations)
    
    def reset_for_auto_mode(self) -> None:
        """重置自动模式状态"""
        self.is_first_command = True
        for motor in MOTOR_NAMES:
            self.initial_angle_base[motor] = self.current_angles.get(motor)
            self.accumulated_rotation[motor] = 0.0
    
    def generate_command(
        self,
        step_params: Dict[str, Any],
        mode: str = "manual"
    ) -> str:
        """
        生成电机控制指令
        
        Args:
            step_params: 步骤参数字典
            mode: 运行模式 ("manual" 或 "auto")
            
        Returns:
            生成的指令字符串
        """
        command = ""
        command_active_motors = set()
        self.pending_targets = {m: None for m in MOTOR_NAMES}
        self.expected_rotation = {m: 0 for m in MOTOR_NAMES}
        
        # 自动模式初始基准设置
        if mode == "auto" and self.is_first_command:
            for motor in self.active_motors:
                if self.current_angles[motor] is not None:
                    self.initial_angle_base[motor] = self.current_angles[motor]
                else:
                    self.initial_angle_base[motor] = None
        
        for motor in MOTOR_NAMES:
            config = step_params.get(motor, {})
            enable = config.get("enable", "D")
            
            # 如果电机未启用，跳过
            if enable != "E":
                continue
            
            command_active_motors.add(motor)
            
            direction = config.get("direction", "F")
            speed = config.get("speed", "0")
            raw_angle = config.get("angle", "0").upper()
            is_continuous = config.get("continuous", False)
            dir_factor = DIRECTION_MAP.get(direction, 1)
            
            try:
                # 持续运行模式
                if is_continuous:
                    command += f"{motor}EFV{speed}JG"
                    self.pending_targets[motor] = None
                    continue
                
                raw_rotation = float(raw_angle)
                self.expected_rotation[motor] = raw_rotation
                
                if mode == "auto":
                    # 自动模式逻辑
                    if self.initial_angle_base[motor] is None:
                        base = self.current_angles.get(motor, 0.0)
                        self.initial_angle_base[motor] = base
                    
                    raw_rotation_signed = float(raw_angle) * dir_factor
                    self.accumulated_rotation[motor] += raw_rotation_signed
                    
                    # 应用校准
                    if self.calibration_enabled:
                        compensation = (
                            (self.theoretical_deviations.get(motor) or 0.0) * 
                            self.calibration_amplitude
                        )
                        calibrated_rotation = raw_rotation_signed - compensation
                    else:
                        calibrated_rotation = raw_rotation_signed
                    
                    actual_rotation = abs(calibrated_rotation)
                    self.expected_angles[motor] = (
                        (self.initial_angle_base[motor] + self.accumulated_rotation[motor]) % 360
                    )
                    
                    # 更新方向
                    if calibrated_rotation < 0:
                        direction = "B"
                    else:
                        direction = "F"
                else:
                    # 手动模式逻辑
                    actual_rotation = float(raw_angle)
                    current = self.current_angles.get(motor, 0.0)
                    self.pending_targets[motor] = (current + actual_rotation * dir_factor) % 360
                
                # 生成指令
                command += f"{motor}E{direction}V{speed}J{actual_rotation:.3f}"
                
            except (ValueError, TypeError) as e:
                print(f"电机{motor}参数错误: {e}")
                continue
        
        # 更新活动电机
        self.active_motors = command_active_motors
        self.is_first_command = False
        
        # 添加结束符
        if command:
            return command + COMMAND_TERMINATOR
        return ""
    
    def generate_stop_command(self) -> str:
        """
        生成停止指令
        
        Returns:
            停止指令字符串
        """
        command = "".join([f"{motor}DFV0J0" for motor in MOTOR_NAMES])
        return command + COMMAND_TERMINATOR
    
    def generate_calibration_command(
        self,
        selected_motors: Set[str]
    ) -> str:
        """
        生成校准指令
        
        Args:
            selected_motors: 需要校准的电机集合
            
        Returns:
            校准指令字符串
        """
        active_commands = []
        
        for motor in MOTOR_NAMES:
            if motor not in selected_motors:
                continue
            
            current_angle = (self.current_angles.get(motor, 0.0) or 0.0) % 360
            
            # 计算最短路径归零
            if current_angle > 180:
                target_angle = 360 - current_angle
                direction = "EF"  # 正转
            else:
                target_angle = current_angle
                direction = "EB"  # 反转
            
            # 生成校准指令
            command_part = f"{motor}{direction}V5J{target_angle:.3f}"
            active_commands.append(command_part)
        
        if not active_commands:
            return ""
        
        return "".join(active_commands) + COMMAND_TERMINATOR

