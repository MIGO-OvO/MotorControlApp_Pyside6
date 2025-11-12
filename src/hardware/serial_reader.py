"""
串口数据读取线程
"""
import time
import serial
from PySide6.QtCore import QThread, Signal


class SerialReader(QThread):
    """串口数据读取线程"""
    
    data_received = Signal(str)  # 接收到数据信号
    
    def __init__(self, serial_port: serial.Serial):
        """
        初始化串口读取线程
        
        Args:
            serial_port: 串口对象
        """
        super().__init__()
        self.serial_port = serial_port
        self.running = True
        self.buffer = ''
    
    def run(self):
        """线程主循环"""
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        raw_data = self.serial_port.read(self.serial_port.in_waiting)
                        try:
                            data = raw_data.decode('utf-8')
                        except UnicodeDecodeError:
                            data = raw_data.decode('utf-8', errors='replace')
                        
                        self.buffer += data
                        
                        # 分割完整行
                        while '\n' in self.buffer:
                            line, self.buffer = self.buffer.split('\n', 1)
                            line = line.strip()
                            if line:
                                self.data_received.emit(line)
                                
                except Exception as e:
                    print(f"Serial read error: {str(e)}")
                    break
            
            time.sleep(0.01)  # 防止CPU占用过高
    
    def stop(self):
        """停止线程"""
        self.running = False
        if self.isRunning():
            self.wait(200)

