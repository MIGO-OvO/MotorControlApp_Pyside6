"""
NIDAQmx 数据采集线程
"""

import time

from PySide6.QtCore import QThread, Signal

try:
    import nidaqmx
    from nidaqmx.constants import TerminalConfiguration

    NIDAQMX_AVAILABLE = True
except ImportError:
    NIDAQMX_AVAILABLE = False
    nidaqmx = None
    TerminalConfiguration = None


class DAQThread(QThread):
    """NIDAQmx数据采集线程"""

    data_acquired = Signal(float)  # 数据采集信号
    error_occurred = Signal(str)  # 错误信号

    def __init__(self, device_name: str, channel_name: str, sample_rate: int, parent=None):
        """
        初始化DAQ线程

        Args:
            device_name: 设备名称
            channel_name: 通道名称
            sample_rate: 采样率(Hz)
            parent: 父对象
        """
        super().__init__(parent)
        self.device_name = device_name
        self.channel_name = channel_name
        self.sample_rate = sample_rate
        self.running = False
        self.task = None
        self.start_time = time.time()

    def run(self):
        """线程主循环"""
        if not NIDAQMX_AVAILABLE:
            self.error_occurred.emit("NIDAQmx库不可用")
            return

        try:
            self.running = True
            self.task = nidaqmx.Task()
            self.task.ai_channels.add_ai_voltage_chan(
                self.channel_name, terminal_config=TerminalConfiguration.RSE
            )

            interval = 1.0 / self.sample_rate

            while self.running:
                start_time = time.time()
                voltage = self.task.read()
                self.data_acquired.emit(voltage)

                # 控制采样率
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                time.sleep(sleep_time)

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if self.task:
                self.task.close()
                self.task = None

    def stop(self):
        """停止采集"""
        self.running = False
        if self.isRunning():
            self.wait(500)
