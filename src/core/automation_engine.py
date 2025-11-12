"""
自动化执行引擎
负责自动化流程的执行、暂停、恢复和停止
"""
import json
import time
import threading
import weakref
from typing import List, Dict, Any, Optional
import serial
from PySide6.QtCore import QThread, Signal


class AutomationThread(QThread):
    """自动化执行线程"""
    
    update_status = Signal(str)  # 状态更新信号
    error_occurred = Signal(str)  # 错误发生信号
    finished = Signal()  # 完成信号
    progress_updated = Signal(int)  # 进度更新信号
    
    def __init__(
        self,
        parent_ref: weakref.ref,
        steps: List[Dict[str, Any]],
        loop_count: int,
        serial_port: serial.Serial,
        serial_lock: threading.Lock
    ):
        """
        初始化自动化线程
        
        Args:
            parent_ref: 父对象弱引用
            steps: 步骤列表
            loop_count: 循环次数（0表示无限循环）
            serial_port: 串口对象
            serial_lock: 串口锁
        """
        super().__init__()
        self.parent_ref = parent_ref
        self.steps = self._deep_copy_steps(steps)
        self.loop_count = loop_count
        self.serial_port = serial_port
        self.lock = serial_lock
        
        self._running = threading.Event()
        self._running.set()
        self._paused = threading.Event()
        self._current_step = 0
        self._current_loop = 1
    
    def _deep_copy_steps(self, steps: List[Dict]) -> List[Dict]:
        """
        深拷贝步骤数据
        
        Args:
            steps: 步骤列表
            
        Returns:
            拷贝后的步骤列表
        """
        try:
            return json.loads(json.dumps(steps))
        except Exception as e:
            self.error_occurred.emit(f"步骤数据解析失败: {str(e)}")
            return []
    
    def run(self):
        """线程主循环"""
        try:
            while self._running.is_set() and self._should_continue():
                try:
                    if not self._running.is_set():
                        break
                    
                    self._execute_loop()
                    
                except serial.SerialException as e:
                    self.error_occurred.emit(f"串口通信失败: {str(e)}")
                    break
                except Exception as e:
                    self.error_occurred.emit(f"未知错误: {str(e)}")
                    break
                    
        except Exception as e:
            self.error_occurred.emit(f"线程初始化失败: {str(e)}")
        finally:
            self._cleanup_resources()
            self.finished.emit()
    
    def _should_continue(self) -> bool:
        """判断是否应该继续执行"""
        if self.loop_count == 0:
            return True
        return self._current_loop <= self.loop_count
    
    def _execute_loop(self) -> None:
        """执行单个循环"""
        loop_info = "∞" if self.loop_count == 0 else str(self.loop_count)
        self.update_status.emit(f"自动运行中 (循环 {self._current_loop}/{loop_info})...")
        self.progress_updated.emit(0)
        
        for step_idx, step in enumerate(self.steps):
            if not self._running.is_set():
                break
            
            # 处理暂停
            while self._paused.is_set():
                time.sleep(0.1)
            
            self._current_step = step_idx
            progress = int((step_idx + 1) / len(self.steps) * 100)
            self.progress_updated.emit(progress)
            
            if not self._send_step_command(step):
                break
            
            self._wait_interval(step.get("interval", 0))
        
        self._current_loop += 1
    
    def _send_step_command(self, step: Dict[str, Any]) -> bool:
        """
        发送步骤指令
        
        Args:
            step: 步骤参数
            
        Returns:
            是否发送成功
        """
        if not self._running.is_set():
            return False
        
        try:
            parent = self.parent_ref()
            if not parent or not self.serial_port:
                return False
            
            command = parent.generate_command(step)
            
            if not self._running.is_set():
                return False
            
            with self.lock:
                if not self._running.is_set():
                    return False
                
                if not self.serial_port.is_open:
                    self.error_occurred.emit("串口连接已断开")
                    return False
                
                try:
                    self.serial_port.write(command.encode('utf-8'))
                    self.serial_port.flush()
                    parent.log(f"指令已发送: {command.strip()}")
                    return True
                except (serial.SerialException, OSError) as e:
                    self.error_occurred.emit(f"指令发送失败: {str(e)}")
                    return False
                    
        except Exception as e:
            self.error_occurred.emit(f"发送指令异常: {str(e)}")
            return False
    
    def _wait_interval(self, interval_ms: int) -> None:
        """
        高精度间隔等待
        
        Args:
            interval_ms: 间隔时间（毫秒）
        """
        interval = interval_ms / 1000.0
        if interval <= 0:
            return
        
        get_time = time.perf_counter
        deadline = get_time() + interval
        error_correction = 0.0
        
        while get_time() < deadline and self._running.is_set():
            remaining = deadline - get_time() - error_correction
            
            if remaining <= 0.002:
                break
            
            # 动态睡眠策略
            if remaining > 0.01:
                sleep_time = remaining * 0.75
                sleep_time = max(sleep_time, 0.005)
                t1 = get_time()
                time.sleep(sleep_time)
                t2 = get_time()
                error_correction += (t2 - t1) - sleep_time
            else:
                while (get_time() + error_correction) < deadline:
                    if (deadline - get_time()) > 0.002:
                        time.sleep(0.001)
        
        # 最终修正
        while (get_time() + error_correction) < deadline:
            pass
        
        # 检查暂停状态
        check_pause_interval = 0.005
        while self._paused.is_set():
            t1 = get_time()
            time.sleep(check_pause_interval)
            deadline += get_time() - t1
    
    def _cleanup_resources(self) -> None:
        """清理资源"""
        try:
            with self.lock:
                if self.serial_port and self.serial_port.is_open:
                    try:
                        # 发送紧急停止指令
                        stop_cmd = b"XDFV0J0 YDFV0J0 ZDFV0J0 ADFV0J0\r\n"
                        self.serial_port.write(stop_cmd)
                        self.serial_port.flush()
                    except Exception:
                        pass
        except Exception:
            pass
    
    def safe_stop(self) -> None:
        """安全停止线程"""
        self._running.clear()
        self._paused.clear()
        
        try:
            with self.lock:
                if self.serial_port and self.serial_port.is_open:
                    try:
                        stop_cmd = b"XDFV0J0 YDFV0J0 ZDFV0J0 ADFV0J0\r\n"
                        self.serial_port.write(stop_cmd)
                        self.serial_port.flush()
                    except Exception:
                        pass
        except Exception:
            pass
        
        if self.isRunning():
            self.wait(1000)
    
    def pause(self) -> None:
        """暂停执行"""
        self._paused.set()
    
    def resume(self) -> None:
        """恢复执行"""
        self._paused.clear()

