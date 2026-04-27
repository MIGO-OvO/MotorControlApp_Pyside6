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
from src.config.constants import (
    DETECTOR_HANDSHAKE_CMD,
    DETECTOR_ID_PREFIX,
    HANDSHAKE_TIMEOUT,
    HANDSHAKE_PROBE_INTERVAL,
)


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

            self.serial_port = serial.Serial()
            self.serial_port.port = port
            self.serial_port.baudrate = baudrate
            self.serial_port.timeout = 1
            self.serial_port.write_timeout = 1
            self.serial_port.rtscts = False
            self.serial_port.dsrdtr = False
            self.serial_port.dtr = False
            self.serial_port.rts = False
            self.serial_port.open()
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            # ---------- 检测装置握手 ----------
            ok, identity = self._perform_handshake(self.serial_port)
            if not ok:
                self.serial_port.close()
                self.serial_port = None
                raise serial.SerialException(f"检测装置握手失败: {identity}")
            self.log(f"检测装置已识别: {identity}")

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
                # C1修复：同步位置监控页的stream_btn状态
                if hasattr(self, "stream_btn"):
                    self.stream_btn.blockSignals(True)
                    self.stream_btn.setChecked(True)
                    self.stream_btn.blockSignals(False)
            except Exception:
                pass

            self.connect_btn.setText("关闭串口")
            self.log(f"串口已连接 {port}@{baudrate}")
            self.status_bar.showMessage(f"已连接 {port}@{baudrate}，实时角度流已自动开启")
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
        # C1修复：关闭串口时同步重置stream_btn状态
        if hasattr(self, "stream_btn"):
            self.stream_btn.blockSignals(True)
            self.stream_btn.setChecked(False)
            self.stream_btn.blockSignals(False)
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


    @staticmethod
    def _perform_handshake(conn: serial.Serial) -> tuple:
        """向检测装置发送 HELLO? 握手并等待 DET_ID 响应。"""
        old_timeout = conn.timeout
        conn.timeout = 0.1

        # 不主动触发 ESP32 自动复位；只释放控制线并探测运行中的固件。
        try:
            conn.dtr = False
            conn.rts = False
        except (OSError, serial.SerialException, ValueError):
            pass
        time.sleep(0.05)
        conn.reset_input_buffer()

        deadline = time.time() + HANDSHAKE_TIMEOUT
        commands = (DETECTOR_HANDSHAKE_CMD, "DET?\r\n")
        next_probe = 0.0
        line = b""
        probe_count = 0
        try:
            while time.time() < deadline:
                if time.time() >= next_probe:
                    cmd = commands[probe_count % len(commands)]
                    conn.write(cmd.encode("utf-8"))
                    conn.flush()
                    probe_count += 1
                    print(f"[HANDSHAKE] probe #{probe_count} sent: {cmd.strip()}")
                    next_probe = time.time() + HANDSHAKE_PROBE_INTERVAL
                chunk = conn.read(1)
                if not chunk:
                    continue
                if chunk in (b"\n", b"\r"):
                    text = line.decode("utf-8", errors="ignore").strip()
                    if text:
                        print(f"[HANDSHAKE] line: {text!r}")
                    if text.startswith(DETECTOR_ID_PREFIX):
                        print(f"[HANDSHAKE] MATCH OK")
                        return True, text
                    line = b""
                else:
                    line += chunk
                    if len(line) > 120:
                        print(f"[HANDSHAKE] line overflow, discarding")
                        line = b""
        finally:
            conn.timeout = old_timeout
        if line:
            print(f"[HANDSHAKE] leftover: {line!r}")
        print(f"[HANDSHAKE] TIMEOUT after {probe_count} probes")
        return False, "握手超时"


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
                command = command.rstrip("\r\n") + "\r\n"
                self.serial_port.write(command.encode("utf-8"))
                self.serial_port.flush()
            self.log(f"已发送指令: {command.strip()}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "发送错误", str(e))
            self.close_serial()
            return False
