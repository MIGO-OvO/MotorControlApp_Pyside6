"""
串口数据读取线程 - 支持文本和二进制混合协议

支持的二进制数据包类型:
- 0x55 0xAA: PID数据包 (29字节)
- 0x55 0xBB: PID测试结果包 (18字节)
- 0x55 0xCC: 角度数据包 (20字节)
"""

import struct
import time
from typing import Optional

import serial
from PySide6.QtCore import QThread, Signal


class SerialReader(QThread):
    """串口数据读取线程，支持文本行和多种二进制数据包"""

    data_received = Signal(str)  # 文本数据信号
    pid_packet_received = Signal(dict)  # PID二进制数据包信号 (0xAA)
    test_result_received = Signal(dict)  # PID测试结果信号 (0xBB)
    angle_packet_received = Signal(dict)  # 角度数据包信号 (0xCC)

    # 通用常量
    HEADER1 = 0x55
    TAIL = 0x0A

    # 数据包类型和大小
    HEADER2_PID = 0xAA  # PID数据包
    HEADER2_TEST = 0xBB  # 测试结果包
    HEADER2_ANGLE = 0xCC  # 角度数据包

    PACKET_SIZE_PID = 29  # PID数据包大小
    PACKET_SIZE_TEST = 18  # 测试结果包大小
    PACKET_SIZE_ANGLE = 20  # 角度数据包大小

    def __init__(self, serial_port: serial.Serial):
        super().__init__()
        self.serial_port = serial_port
        self.running = True
        self.binary_buffer = bytearray()
        self.text_buffer = ""

    def run(self):
        """线程主循环"""
        while self.running:
            try:
                if not self.running:  # 双重检查
                    break

                if self.serial_port and self.serial_port.is_open:
                    try:
                        if self.serial_port.in_waiting > 0:
                            raw_data = self.serial_port.read(self.serial_port.in_waiting)
                            if self.running:  # 读取后再次检查
                                self._process_data(raw_data)
                    except serial.SerialException as e:
                        if self.running:
                            print(f"Serial error: {str(e)}")
                        break
                    except Exception as e:
                        if self.running:
                            print(f"Serial read error: {str(e)}")

                # 检查运行标志后再睡眠
                if self.running:
                    time.sleep(0.005)
            except Exception as e:
                if self.running:
                    print(f"Serial thread error: {str(e)}")
                break

    def _process_data(self, raw_data: bytes):
        """处理接收到的数据，区分文本和二进制"""
        self.binary_buffer.extend(raw_data)

        while len(self.binary_buffer) > 0:
            # 查找二进制帧头
            header_info = self._find_header()

            if header_info is None:
                # 没有找到帧头，全部作为文本处理
                self._process_as_text(bytes(self.binary_buffer))
                self.binary_buffer.clear()
                break

            header_pos, packet_type, packet_size = header_info

            if header_pos > 0:
                # 帧头前有数据，作为文本处理
                self._process_as_text(bytes(self.binary_buffer[:header_pos]))
                del self.binary_buffer[:header_pos]

            # 检查是否有足够的数据
            if len(self.binary_buffer) < packet_size:
                break  # 数据不完整，等待更多数据

            # 尝试提取并验证数据包
            packet_data = bytes(self.binary_buffer[:packet_size])
            if self._validate_packet(packet_data, packet_type, packet_size):
                self._emit_packet(packet_data, packet_type)
                del self.binary_buffer[:packet_size]
            else:
                # 校验失败，跳过这个帧头字节，继续查找下一个
                del self.binary_buffer[:1]

    def _find_header(self) -> Optional[tuple]:
        """
        查找帧头位置并识别数据包类型

        Returns:
            tuple: (位置, 包类型, 包大小) 或 None
        """
        for i in range(len(self.binary_buffer) - 1):
            if self.binary_buffer[i] == self.HEADER1:
                header2 = self.binary_buffer[i + 1]
                if header2 == self.HEADER2_PID:
                    return (i, self.HEADER2_PID, self.PACKET_SIZE_PID)
                elif header2 == self.HEADER2_TEST:
                    return (i, self.HEADER2_TEST, self.PACKET_SIZE_TEST)
                elif header2 == self.HEADER2_ANGLE:
                    return (i, self.HEADER2_ANGLE, self.PACKET_SIZE_ANGLE)
        return None

    def _validate_packet(self, data: bytes, packet_type: int, packet_size: int) -> bool:
        """验证数据包完整性"""
        if len(data) < packet_size:
            return False
        if data[0] != self.HEADER1 or data[1] != packet_type:
            return False
        if data[packet_size - 1] != self.TAIL:
            return False

        # 根据包类型计算校验和
        if packet_type == self.HEADER2_PID:
            # PID包: motor_id(1) + timestamp(4) + 5*float(20) = 25 bytes
            checksum = 0
            for i in range(2, 27):
                checksum ^= data[i]
            return checksum == data[27]

        elif packet_type == self.HEADER2_TEST:
            # 测试结果包: 从motor_id到total_score = 14 bytes
            checksum = 0
            for i in range(2, 16):
                checksum ^= data[i]
            return checksum == data[16]

        elif packet_type == self.HEADER2_ANGLE:
            # 角度包: head2(1) + angles(16) = 17 bytes
            checksum = 0
            for i in range(1, 18):
                checksum ^= data[i]
            return checksum == data[18]

        return False

    def _emit_packet(self, data: bytes, packet_type: int):
        """解析并发送数据包"""
        try:
            if packet_type == self.HEADER2_PID:
                self._emit_pid_packet(data)
            elif packet_type == self.HEADER2_TEST:
                self._emit_test_result_packet(data)
            elif packet_type == self.HEADER2_ANGLE:
                self._emit_angle_packet(data)
        except Exception as e:
            print(f"Packet parse error: {e}")

    def _emit_pid_packet(self, data: bytes):
        """解析并发送PID数据包"""
        motor_id = data[2]
        motor_names = ["X", "Y", "Z", "A"]

        packet = {
            "motor": motor_names[motor_id] if motor_id < 4 else "X",
            "motor_id": motor_id,
            "timestamp": struct.unpack("<I", data[3:7])[0],
            "target_angle": struct.unpack("<f", data[7:11])[0],
            "actual_angle": struct.unpack("<f", data[11:15])[0],
            "theo_angle": struct.unpack("<f", data[15:19])[0],
            "pid_out": struct.unpack("<f", data[19:23])[0],
            "error": struct.unpack("<f", data[23:27])[0],
        }
        self.pid_packet_received.emit(packet)

    def _emit_test_result_packet(self, data: bytes):
        """解析并发送PID测试结果数据包"""
        motor_id = data[2]
        motor_names = ["X", "Y", "Z", "A"]

        result = {
            "motor": motor_names[motor_id] if motor_id < 4 else "X",
            "motor_id": motor_id,
            "run_index": data[3],
            "total_runs": data[4],
            "convergence_time_ms": struct.unpack("<H", data[5:7])[0],
            "max_overshoot": struct.unpack("<h", data[7:9])[0] / 100.0,
            "final_error": struct.unpack("<h", data[9:11])[0] / 100.0,
            "oscillation_count": data[11],
            "smoothness_score": data[12],
            "startup_jerk": struct.unpack("<H", data[13:15])[0] / 100.0,
            "total_score": data[15],
        }
        self.test_result_received.emit(result)

    def _emit_angle_packet(self, data: bytes):
        """解析并发送角度数据包"""
        angles = struct.unpack("<4f", data[2:18])

        packet = {
            "X": angles[0],
            "Y": angles[1],
            "Z": angles[2],
            "A": angles[3],
        }
        self.angle_packet_received.emit(packet)

    def _process_as_text(self, data: bytes):
        """将数据作为文本处理"""
        try:
            text = data.decode("utf-8", errors="replace")
        except:
            text = data.decode("latin-1", errors="replace")

        # 添加到文本缓冲区
        self.text_buffer += text

        # 按行分割并发送完整行
        while "\n" in self.text_buffer:
            line, self.text_buffer = self.text_buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.data_received.emit(line)

    def stop(self):
        """停止线程"""
        self.running = False
        # 清空缓冲区，防止处理残留数据
        self.binary_buffer.clear()
        self.text_buffer = ""
        if self.isRunning():
            # 等待线程自然退出，避免使用 terminate() 导致 COM 错误
            self.wait(2000)
