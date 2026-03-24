"""
ADS122C04 分光采集会话控制 (已替换 NIDAQmx)

通过串口与下位机通信，控制 ADS122C04 的配置、启停。
实际数据由 SerialReader 解析 0xDD 包后通过信号传递。
"""

from PySide6.QtCore import QObject, Signal


class ADSSession(QObject):
    """ADS122C04 采集会话控制类

    负责向下位机发送 ADSCFG / ADSSTART / ADSSTOP 命令。
    数据接收由 SerialReader.spectro_packet_received 信号完成。
    """

    error_occurred = Signal(str)  # 错误信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """标记采集已启动"""
        self._running = True

    def stop(self):
        """标记采集已停止"""
        self._running = False
