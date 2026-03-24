#ifndef I2C_MUX_H
#define I2C_MUX_H

#include <Arduino.h>
#include <Wire.h>

// ============== TCA9548A I2C 多路复用器 ==============
#define TCA_ADDR 0x70
#define MT6701_ADDR 0x06
#define MAX_RETRIES 3

// ============== 可配置的 I2C 通道映射 ==============
extern uint8_t g_angleChannels[4];   // X, Y, Z, A 角度源的 TCA 通道
extern uint8_t g_spectroChannel;     // ADS122C04 所在的 TCA 通道

// 缓存上次选中的通道，减少重复切换
static uint8_t _lastSelectedChannel = 0xFF;

/**
 * 选择 TCA9548A 的指定通道
 * @param channel 通道号 0~7
 * @return 是否成功
 */
inline bool selectTcaChannel(uint8_t channel) {
    if (channel > 7) return false;
    if (channel == _lastSelectedChannel) return true;

    Wire.beginTransmission(TCA_ADDR);
    Wire.write(1 << channel);
    bool ok = (Wire.endTransmission(true) == 0);
    if (ok) {
        _lastSelectedChannel = channel;
    }
    return ok;
}

/**
 * 使 TCA 通道缓存失效（切换 I2C 总线速率后调用）
 */
inline void invalidateTcaCache() {
    _lastSelectedChannel = 0xFF;
}

/**
 * 通过 TCA9548A 读取 MT6701 角度（带重试）
 * @param channel TCA 通道号
 * @return 角度值 0~360，失败返回 -1
 */
inline float readMt6701Angle(uint8_t channel) {
    for (int retry = 0; retry < MAX_RETRIES; retry++) {
        // 选择通道
        if (!selectTcaChannel(channel)) {
            _lastSelectedChannel = 0xFF;
            delay(2);
            continue;
        }
        delayMicroseconds(200);

        // 读取高字节
        Wire.beginTransmission(MT6701_ADDR);
        Wire.write(0x03);
        if (Wire.endTransmission(true) != 0) { delay(2); _lastSelectedChannel = 0xFF; continue; }
        delayMicroseconds(100);

        uint16_t highByte;
        if (Wire.requestFrom((uint16_t)MT6701_ADDR, (uint8_t)1, (bool)true) == 1) {
            highByte = Wire.read();
        } else { delay(2); _lastSelectedChannel = 0xFF; continue; }

        // 读取低字节
        Wire.beginTransmission(MT6701_ADDR);
        Wire.write(0x04);
        if (Wire.endTransmission(true) != 0) { delay(2); _lastSelectedChannel = 0xFF; continue; }
        delayMicroseconds(100);

        uint16_t lowByte;
        if (Wire.requestFrom((uint16_t)MT6701_ADDR, (uint8_t)1, (bool)true) == 1) {
            lowByte = Wire.read();
        } else { delay(2); _lastSelectedChannel = 0xFF; continue; }

        if (highByte == 0xFF && lowByte == 0xFF) { delay(2); continue; }

        uint16_t raw = (highByte << 6) | (lowByte >> 2);
        float angle = (raw / 16384.0) * 360.0;
        if (angle >= 0 && angle <= 360) return angle;
    }
    return -1.0;
}

/**
 * 解析并应用 I2C 通道映射命令
 * 格式: I2CMAP:X=0,Y=3,Z=4,A=7,SPEC=2
 * @param cmd 完整命令字符串
 */
inline void parseI2CMapCommand(String cmd) {
    int colonIdx = cmd.indexOf(':');
    if (colonIdx == -1) {
        Serial.println("I2CMAP_ERR:FORMAT");
        return;
    }
    String params = cmd.substring(colonIdx + 1);

    uint8_t newAngles[4] = {g_angleChannels[0], g_angleChannels[1], g_angleChannels[2], g_angleChannels[3]};
    uint8_t newSpec = g_spectroChannel;
    bool anyError = false;

    // 解析各通道
    int startPos = 0;
    while (startPos < (int)params.length()) {
        int commaPos = params.indexOf(',', startPos);
        String token = (commaPos == -1) ? params.substring(startPos) : params.substring(startPos, commaPos);
        token.trim();

        int eqPos = token.indexOf('=');
        if (eqPos > 0) {
            String key = token.substring(0, eqPos);
            int val = token.substring(eqPos + 1).toInt();

            if (val < 0 || val > 7) { anyError = true; break; }

            if (key == "X") newAngles[0] = val;
            else if (key == "Y") newAngles[1] = val;
            else if (key == "Z") newAngles[2] = val;
            else if (key == "A") newAngles[3] = val;
            else if (key == "SPEC") newSpec = val;
        }
        if (commaPos == -1) break;
        startPos = commaPos + 1;
    }

    if (anyError) {
        Serial.println("I2CMAP_ERR:CHANNEL_RANGE");
        return;
    }

    memcpy(g_angleChannels, newAngles, 4);
    g_spectroChannel = newSpec;
    invalidateTcaCache();

    Serial.printf("I2CMAP_OK:X=%d,Y=%d,Z=%d,A=%d,SPEC=%d\n",
        g_angleChannels[0], g_angleChannels[1], g_angleChannels[2], g_angleChannels[3], g_spectroChannel);
}

#endif // I2C_MUX_H

