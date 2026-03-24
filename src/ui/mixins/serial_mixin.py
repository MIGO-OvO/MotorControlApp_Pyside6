"""串口通信 Mixin 模块。

该模块提供串口通信相关功能，包括：
- 串口连接管理（打开/关闭）
- 端口刷新和发现
- 指令发送

Note:
    此模块设计为 Mixin 类，需要与 QMainWindow 子类一起使用。
    使用时需确保主类具有 serial_port, serial_lock, serial_reader 等属性。
"""

import time
import threading

import serial
from serial.tools import list_ports

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from src.hardware.serial_reader import SerialReader


class SerialMixin:
    """串口通信功能 Mixin。

    提供串口连接管理和指令发送功能。

    Attributes:
        serial_port: 串口实例
        serial_lock: 串口操作锁
        serial_reader: 串口读取线程
    """

    def get_available_ports(self) -> list:
        """获取可用串口列表。

        Returns:
            排序后的可用串口列表
        """
        ports = {port.device for port in list_ports.comports()}
        fixed_ports = {"COM1", "COM2"}
        return sorted(
            fixed_ports.union(ports), key=lambda x: int(x[3:]) if x.startswith("COM") else 999
        )

    def refresh_serial_ports(self) -> None:
        """刷新串口列表。"""
        current = self.port_combo.currentText()
        current_baud = self.baud_combo.currentText()
        self.port_combo.clear()
        available_ports = self.get_available_ports()
        self.port_combo.addItems(available_ports)
        self.baud_combo.setCurrentText(current_baud)
        if current in available_ports:
            self.port_combo.setCurrentText(current)
        else:
            if available_ports:
                self.port_combo.setCurrentIndex(0)

    def toggle_serial(self) -> None:
        """切换串口连接状态。"""
        if self.serial_port and self.serial_port.is_open:
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self) -> None:
        """打开串口连接。"""
        try:
            port = self.port_combo.currentText()
            baudrate = int(self.baud_combo.currentText())
            if not port:
                raise serial.SerialException("未选择端口")

            self.serial_port = serial.Serial(
                port=port, baudrate=baudrate, timeout=1, write_timeout=1
            )
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self._closing = False
            self.serial_reader = SerialReader(self.serial_port)
            self.serial_reader.data_received.connect(
                self.handle_serial_data, Qt.ConnectionType.QueuedConnection
            )
            self.serial_reader.pid_packet_received.connect(
                self.handle_pid_packet, Qt.ConnectionType.QueuedConnection
            )
            self.serial_reader.test_result_received.connect(
                self.handle_test_result_packet, Qt.ConnectionType.QueuedConnection
            )
            self.serial_reader.angle_packet_received.connect(
                self.handle_angle_packet, Qt.ConnectionType.QueuedConnection
            )
            self.serial_reader.spectro_packet_received.connect(
                self.handle_spectro_packet, Qt.ConnectionType.QueuedConnection
            )
            self.serial_reader.start()

            if hasattr(self, "_chart_update_timer"):
                self._chart_update_timer.start()

            # 自动启动实时角度流
            try:
                # 先同步 I2C 映射配置
                self._sync_i2c_mapping()
                self.serial_port.write(b"ANGLESTREAM_START\r\n")
            except Exception:
                pass

            self.connect_btn.setText("关闭串口")
            self.log(f"串口已连接 {port}@{baudrate}")
            self.status_bar.showMessage(f"已连接 {port}@{baudrate}")
        except serial.SerialException as e:
            QMessageBox.critical(self, "串口错误", f"串口连接失败: {e}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"发生未知错误: {e}")

    def close_serial(self) -> None:
        """关闭串口连接。"""
        self._closing = True

        # 停止图表更新定时器
        try:
            if hasattr(self, "_chart_update_timer") and self._chart_update_timer.isActive():
                self._chart_update_timer.stop()
        except (RuntimeError, AttributeError):
            pass

        # 清空待处理数据包
        if hasattr(self, "_pending_pid_packets"):
            self._pending_pid_packets.clear()

        # 停止 PID 更新定时器
        try:
            if hasattr(self, "pid_update_timer") and self.pid_update_timer.isActive():
                self.pid_update_timer.stop()
        except (RuntimeError, AttributeError):
            pass

        # 发送停止角度流指令
        with self.serial_lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.write(b"ANGLESTREAM_STOP\r\n")
                    self.serial_port.flush()
                    time.sleep(0.1)
                except Exception as e:
                    if not self._closing:
                        self.log(f"发送停止角度流指令失败: {e}")

        # 断开信号连接
        reader = None
        if hasattr(self, "serial_reader") and self.serial_reader is not None:
            reader = self.serial_reader
            self.serial_reader = None

            try:
                reader.data_received.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                reader.pid_packet_received.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                reader.test_result_received.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                reader.angle_packet_received.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                reader.spectro_packet_received.disconnect()
            except (TypeError, RuntimeError):
                pass

        # 停止读取线程
        if reader is not None:
            reader.stop()

        # 关闭串口
        with self.serial_lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
                self.serial_port = None

        self.connect_btn.setText("打开串口")
        self.log("串口已关闭")
        self.status_bar.showMessage("串口已关闭")

    def _sync_i2c_mapping(self) -> None:
        """从设置中读取 I2C 通道映射并发送给下位机。"""
        try:
            from src.config.constants import DEFAULT_I2C_MAPPING
            import json, os

            mapping = dict(DEFAULT_I2C_MAPPING)
            # 尝试从 settings.json 加载
            if hasattr(self, "settings_file") and os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                saved = settings.get("i2c_mapping", {})
                if saved:
                    mapping = saved

            angles = mapping.get("angles", {"X": 0, "Y": 3, "Z": 4, "A": 7})
            spec = mapping.get("spectro_channel", 2)
            cmd = f"I2CMAP:X={angles['X']},Y={angles['Y']},Z={angles['Z']},A={angles['A']},SPEC={spec}\r\n"
            self.serial_port.write(cmd.encode("utf-8"))
            self.log(f"已同步I2C映射: {cmd.strip()}")
        except Exception as e:
            self.log(f"同步I2C映射失败: {e}")

    def send_command(self, command: str) -> bool:
        """发送串口指令。

        Args:
            command: 要发送的指令字符串

        Returns:
            发送是否成功
        """
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.critical(self, "错误", "请先打开串口连接！")
            return False
        try:
            with self.serial_lock:
                self.serial_port.write(command.encode("utf-8"))
            self.log(f"已发送指令: {command.strip()}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "发送错误", str(e))
            self.close_serial()
            return False
