"""
串口通信管理器
负责串口连接、断开、数据发送和接收
"""

import threading
from typing import Callable, List, Optional

import serial
from PySide6.QtCore import QObject, Signal
from serial.tools import list_ports

from ..config.constants import COMMAND_TERMINATOR, SERIAL_TIMEOUT, WRITE_TIMEOUT
from ..hardware.serial_reader import SerialReader


class SerialManager(QObject):
    """串口通信管理器"""

    # 信号定义
    connected = Signal(str, int)  # 连接成功信号 (端口, 波特率)
    disconnected = Signal()  # 断开连接信号
    data_received = Signal(str)  # 接收到数据信号
    error_occurred = Signal(str)  # 错误发生信号

    def __init__(self):
        """初始化串口管理器"""
        super().__init__()
        self.serial_port: Optional[serial.Serial] = None
        self.serial_reader: Optional[SerialReader] = None
        self.serial_lock = threading.Lock()
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._is_connected and self.serial_port and self.serial_port.is_open

    @staticmethod
    def get_available_ports() -> List[str]:
        """
        获取可用串口列表

        Returns:
            端口名称列表
        """
        ports = {port.device for port in list_ports.comports()}
        fixed_ports = {"COM1", "COM2"}
        return sorted(
            fixed_ports.union(ports), key=lambda x: int(x[3:]) if x.startswith("COM") else 999
        )

    def connect_port(self, port: str, baudrate: int) -> bool:
        """
        连接串口

        Args:
            port: 端口名称
            baudrate: 波特率

        Returns:
            是否连接成功
        """
        if self.is_connected:
            self.error_occurred.emit("串口已连接，请先断开")
            return False

        try:
            if not port:
                raise serial.SerialException("未选择端口")

            self.serial_port = serial.Serial(
                port=port, baudrate=baudrate, timeout=SERIAL_TIMEOUT, write_timeout=WRITE_TIMEOUT
            )

            # 清空缓冲区
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            # 启动读取线程
            self.serial_reader = SerialReader(self.serial_port)
            self.serial_reader.data_received.connect(self._on_data_received)
            self.serial_reader.start()

            self._is_connected = True
            self.connected.emit(port, baudrate)
            return True

        except serial.SerialException as e:
            self.error_occurred.emit(f"串口连接失败: {str(e)}")
            return False
        except Exception as e:
            self.error_occurred.emit(f"发生未知错误: {str(e)}")
            return False

    def disconnect_port(self) -> None:
        """断开串口连接"""
        with self.serial_lock:
            # 停止读取线程
            if self.serial_reader and self.serial_reader.isRunning():
                self.serial_reader.stop()
                self.serial_reader = None

            # 关闭串口
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.close()
                except Exception as e:
                    print(f"关闭串口错误: {str(e)}")
                finally:
                    self.serial_port = None

            self._is_connected = False
            self.disconnected.emit()

    def send_command(self, command: str, add_terminator: bool = True) -> bool:
        """
        发送指令

        Args:
            command: 指令字符串
            add_terminator: 是否自动添加结束符

        Returns:
            是否发送成功
        """
        if not self.is_connected:
            self.error_occurred.emit("串口未连接")
            return False

        try:
            with self.serial_lock:
                if add_terminator and not command.endswith(COMMAND_TERMINATOR):
                    command += COMMAND_TERMINATOR

                self.serial_port.write(command.encode("utf-8"))
                self.serial_port.flush()
                return True

        except (serial.SerialException, OSError) as e:
            self.error_occurred.emit(f"指令发送失败: {str(e)}")
            self.disconnect_port()
            return False
        except Exception as e:
            self.error_occurred.emit(f"发送指令异常: {str(e)}")
            return False

    def _on_data_received(self, data: str):
        """
        内部数据接收处理

        Args:
            data: 接收到的数据
        """
        self.data_received.emit(data)

    def get_port_info(self) -> Optional[dict]:
        """
        获取当前串口信息

        Returns:
            串口信息字典，包含port和baudrate
        """
        if self.is_connected and self.serial_port:
            return {"port": self.serial_port.port, "baudrate": self.serial_port.baudrate}
        return None
