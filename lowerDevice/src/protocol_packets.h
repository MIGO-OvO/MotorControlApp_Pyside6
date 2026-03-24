#ifndef PROTOCOL_PACKETS_H
#define PROTOCOL_PACKETS_H

#include <Arduino.h>

// ============== 二进制协议常量 ==============
#define PACKET_HEADER1      0x55
#define PACKET_TAIL         0x0A

#define HEADER2_PID         0xAA  // PID 数据包
#define HEADER2_TEST        0xBB  // PID 测试结果包
#define HEADER2_ANGLE       0xCC  // 角度数据包
#define HEADER2_SPECTRO     0xDD  // 分光数据包

// ============== 数据包结构定义 ==============
#pragma pack(push, 1)

// 普通PID数据包 (0xAA) - 29字节
typedef struct {
    uint8_t  head1;         // 0x55
    uint8_t  head2;         // 0xAA
    uint8_t  motor_id;      // 电机ID: 0=X, 1=Y, 2=Z, 3=A
    uint32_t timestamp;     // 时间戳 (micros)
    float    target_angle;  // 目标角度
    float    actual_angle;  // 实际角度 (MT6701)
    float    theo_angle;    // 理论角度 (步数推算)
    float    pid_out;       // PID输出值 (RPM)
    float    error;         // 当前误差
    uint8_t  checksum;      // 校验和
    uint8_t  tail;          // 0x0A
} PIDDataPacket;

// PID测试结果数据包 (0xBB) - 18字节
typedef struct {
    uint8_t  head1;              // 0x55
    uint8_t  head2;              // 0xBB
    uint8_t  motor_id;           // 电机ID
    uint8_t  run_index;          // 第几轮测试 (0-based)
    uint8_t  total_runs;         // 总测试轮数
    uint16_t convergence_time_ms;// 收敛时间 (ms)
    int16_t  max_overshoot_x100; // 最大过冲 (度*100, 有符号)
    int16_t  final_error_x100;   // 最终误差 (度*100, 有符号)
    uint8_t  oscillation_count;  // 振荡次数
    uint8_t  smoothness_score;   // 平滑度评分 (0-100)
    uint16_t startup_jerk_x100;  // 启动冲击度 (*100)
    uint8_t  total_score;        // 综合评分 (0-100)
    uint8_t  checksum;           // 校验和
    uint8_t  tail;               // 0x0A
} PIDTestResultPacket;

// 角度数据包 (0xCC) - 20字节
typedef struct {
    uint8_t  head1;         // 0x55
    uint8_t  head2;         // 0xCC
    float    angles[4];     // X, Y, Z, A 角度 (4 * 4 = 16字节)
    uint8_t  checksum;      // 校验和
    uint8_t  tail;          // 0x0A
} AngleDataPacket;          // 共20字节

// 分光数据包 (0xDD) - 18字节
// status 位定义:
//   bit0: 新数据有效
//   bit1: I2C 访问失败
//   bit2: 配置未完成
//   bit3: 数据饱和或越界
typedef struct {
    uint8_t  head1;         // 0x55
    uint8_t  head2;         // 0xDD
    uint32_t timestamp_ms;  // 时间戳 (millis)
    uint8_t  tca_channel;   // TCA 通道号
    uint8_t  status;        // 状态位
    int32_t  raw_code;      // 24-bit 原始码 (符号扩展到 32-bit)
    float    voltage;       // 换算后的电压 (V)
    uint8_t  checksum;      // XOR 校验和
    uint8_t  tail;          // 0x0A
} SpectroDataPacket;        // 共18字节

static_assert(sizeof(SpectroDataPacket) == 18, "SpectroDataPacket must be 18 bytes");

#pragma pack(pop)

// ============== 分光包状态位 ==============
#define SPECTRO_STATUS_VALID        0x01
#define SPECTRO_STATUS_I2C_ERROR    0x02
#define SPECTRO_STATUS_NOT_CONFIG   0x04
#define SPECTRO_STATUS_SATURATED    0x08

// ============== 分光包大小 ==============
#define PACKET_SIZE_PID     29
#define PACKET_SIZE_TEST    18
#define PACKET_SIZE_ANGLE   20
#define PACKET_SIZE_SPECTRO sizeof(SpectroDataPacket)

#endif // PROTOCOL_PACKETS_H
