"""
日志工具
"""
from datetime import datetime
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal
from ..config.constants import LOG_TIME_FORMAT


class Logger(QObject):
    """日志记录器"""
    
    log_message = Signal(str)  # 日志消息信号
    
    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        """
        初始化日志记录器
        
        Args:
            callback: 日志回调函数
        """
        super().__init__()
        self._callback = callback
        if callback:
            self.log_message.connect(callback)
    
    def log(self, message: str, level: str = "INFO") -> None:
        """
        记录日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        timestamp = datetime.now().strftime(LOG_TIME_FORMAT)[:-3]
        formatted_msg = f"[{timestamp}] [{level}] {message}"
        self.log_message.emit(formatted_msg)
    
    def info(self, message: str) -> None:
        """记录信息日志"""
        self.log(message, "INFO")
    
    def warning(self, message: str) -> None:
        """记录警告日志"""
        self.log(message, "WARNING")
    
    def error(self, message: str) -> None:
        """记录错误日志"""
        self.log(message, "ERROR")
    
    def debug(self, message: str) -> None:
        """记录调试日志"""
        self.log(message, "DEBUG")

