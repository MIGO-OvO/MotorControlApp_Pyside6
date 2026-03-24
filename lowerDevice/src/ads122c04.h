#ifndef ADS122C04_H
#define ADS122C04_H

#include <Arduino.h>
#include <Wire.h>
#include "i2c_mux.h"

// ============== ADS122C04 命令 ==============
#define ADS_CMD_RESET       0x06
#define ADS_CMD_START_SYNC  0x08
#define ADS_CMD_POWERDOWN   0x02
#define ADS_CMD_RDATA       0x10
#define ADS_CMD_RREG(r)     (0x20 | ((r) << 2))
#define ADS_CMD_WREG(r)     (0x40 | ((r) << 2))

// ============== MUX 配置（单端） ==============
#define ADS_MUX_AIN0_AVSS  0x08  // AIN0 vs AVSS
#define ADS_MUX_AIN1_AVSS  0x09
#define ADS_MUX_AIN2_AVSS  0x0A
#define ADS_MUX_AIN3_AVSS  0x0B

// ============== VREF 配置 ==============
#define ADS_VREF_INTERNAL   0x00  // 2.048V
#define ADS_VREF_EXTERNAL   0x01
#define ADS_VREF_AVDD       0x02  // Analog supply

// ============== 采样率 (Normal mode) ==============
static const uint16_t ADS_RATES_NORMAL[] = {20, 45, 90, 175, 330, 600, 1000};
static const uint8_t  ADS_RATE_COUNT = 7;

// ============== ADS 配置结构 ==============
struct ADSConfig {
    uint8_t  address;        // I2C 地址 (默认 0x40)
    uint8_t  tcaChannel;     // TCA9548A 通道
    uint8_t  mux;            // 输入MUX (默认 AIN0/AVSS)
    uint8_t  gain;           // 增益 1/2/4
    bool     pgaBypass;      // PGA旁路
    bool     turboMode;      // Turbo模式
    bool     continuousMode; // 连续转换模式
    uint8_t  vrefMode;       // 参考源 0=INT, 2=AVDD
    uint16_t adcRate;        // ADC采样率 (SPS)
    uint16_t publishRate;    // 串口上传频率 (Hz)
    bool     enabled;        // 是否启用
    bool     running;        // 是否正在运行
    float    vrefValue;      // 参考电压值 (V)
};

// 默认配置
inline void adsConfigDefault(ADSConfig &cfg) {
    cfg.address = 0x40;
    cfg.tcaChannel = 2;
    cfg.mux = ADS_MUX_AIN0_AVSS;
    cfg.gain = 1;
    cfg.pgaBypass = true;
    cfg.turboMode = false;
    cfg.continuousMode = true;
    cfg.vrefMode = ADS_VREF_AVDD;
    cfg.adcRate = 90;
    cfg.publishRate = 50;
    cfg.enabled = false;
    cfg.running = false;
    cfg.vrefValue = 3.3f;
}

// ============== ADS I2C 操作 ==============
inline bool adsSendCommand(uint8_t addr, uint8_t cmd) {
    Wire.beginTransmission(addr);
    Wire.write(cmd);
    return (Wire.endTransmission(true) == 0);
}

inline bool adsWriteRegister(uint8_t addr, uint8_t reg, uint8_t value) {
    Wire.beginTransmission(addr);
    Wire.write(ADS_CMD_WREG(reg));
    Wire.write(value);
    return (Wire.endTransmission(true) == 0);
}

inline bool adsReadRegister(uint8_t addr, uint8_t reg, uint8_t *value) {
    Wire.beginTransmission(addr);
    Wire.write(ADS_CMD_RREG(reg));
    if (Wire.endTransmission(true) != 0) return false;
    if (Wire.requestFrom(addr, (uint8_t)1) != 1) return false;
    *value = Wire.read();
    return true;
}

inline bool adsReadData(uint8_t addr, int32_t *rawCode) {
    Wire.beginTransmission(addr);
    Wire.write(ADS_CMD_RDATA);
    if (Wire.endTransmission(true) != 0) return false;
    if (Wire.requestFrom(addr, (uint8_t)3) != 3) return false;
    uint8_t b0 = Wire.read();
    uint8_t b1 = Wire.read();
    uint8_t b2 = Wire.read();
    int32_t code = ((int32_t)b0 << 16) | ((int32_t)b1 << 8) | b2;
    // 24-bit 符号扩展
    if (code & 0x800000) code |= 0xFF000000;
    *rawCode = code;
    return true;
}

// ============== 电压换算 ==============
inline float codeToVoltage(int32_t rawCode, float vref, float gain) {
    return (float)rawCode / 8388608.0f * (vref / gain);
}

// ============== 查找最近的合法采样率 ==============
inline uint16_t adsNearestRate(uint16_t requested) {
    uint16_t best = ADS_RATES_NORMAL[0];
    uint16_t bestDiff = abs((int)requested - (int)best);
    for (uint8_t i = 1; i < ADS_RATE_COUNT; i++) {
        uint16_t diff = abs((int)requested - (int)ADS_RATES_NORMAL[i]);
        if (diff < bestDiff) { bestDiff = diff; best = ADS_RATES_NORMAL[i]; }
    }
    return best;
}

// ============== 采样率 -> DR 位域映射 ==============
inline uint8_t adsRateToDRBits(uint16_t rate) {
    for (uint8_t i = 0; i < ADS_RATE_COUNT; i++) {
        if (ADS_RATES_NORMAL[i] == rate) return i;
    }
    return 2; // 默认 90 SPS
}

// ============== 增益 -> GAIN 位域映射 ==============
inline uint8_t adsGainToBits(uint8_t gain) {
    if (gain == 2) return 1;
    if (gain == 4) return 2;
    return 0; // gain = 1
}

/**
 * 配置 ADS122C04 并启动转换
 * 调用前必须已切换到正确的 TCA 通道
 */
inline bool adsInitAndStart(ADSConfig &cfg) {
    // 复位
    if (!adsSendCommand(cfg.address, ADS_CMD_RESET)) return false;
    delay(1);

    // CONFIG0: MUX[7:4] | GAIN[3:1] | PGA_BYPASS[0]
    uint8_t reg0 = (cfg.mux << 4) | (adsGainToBits(cfg.gain) << 1) | (cfg.pgaBypass ? 1 : 0);
    if (!adsWriteRegister(cfg.address, 0, reg0)) return false;

    // CONFIG1: DR[7:5] | MODE[4] | CM[3] | VREF[2:1] | TS[0]
    uint8_t drBits = adsRateToDRBits(cfg.adcRate);
    uint8_t reg1 = (drBits << 5)
                  | (cfg.turboMode ? 0x10 : 0x00)
                  | (cfg.continuousMode ? 0x08 : 0x00)
                  | ((cfg.vrefMode & 0x03) << 1);
    if (!adsWriteRegister(cfg.address, 1, reg1)) return false;

    // CONFIG2 & CONFIG3: 保持默认 (DRDY on DRDY pin, CRC disabled, etc.)
    if (!adsWriteRegister(cfg.address, 2, 0x00)) return false;
    if (!adsWriteRegister(cfg.address, 3, 0x00)) return false;

    // 设置参考电压值
    if (cfg.vrefMode == ADS_VREF_AVDD) {
        cfg.vrefValue = 3.3f;
    } else {
        cfg.vrefValue = 2.048f;
    }

    // 启动转换
    if (!adsSendCommand(cfg.address, ADS_CMD_START_SYNC)) return false;

    cfg.running = true;
    return true;
}

/**
 * 停止 ADS122C04 转换
 */
inline bool adsStop(ADSConfig &cfg) {
    if (!selectTcaChannel(cfg.tcaChannel)) return false;
    adsSendCommand(cfg.address, ADS_CMD_POWERDOWN);
    cfg.running = false;
    return true;
}

/**
 * 解析 ADSCFG 命令
 * 格式: ADSCFG:CH=2,ADDR=0x40,AIN=AIN0,REF=AVDD,GAIN=1,DR=90,MODE=CONT
 */
inline void parseADSConfigCommand(String cmd, ADSConfig &cfg) {
    int colonIdx = cmd.indexOf(':');
    if (colonIdx == -1) { Serial.println("ADS_ERR:CONFIG"); return; }
    String params = cmd.substring(colonIdx + 1);

    int startPos = 0;
    while (startPos < (int)params.length()) {
        int commaPos = params.indexOf(',', startPos);
        String token = (commaPos == -1) ? params.substring(startPos) : params.substring(startPos, commaPos);
        token.trim();
        int eqPos = token.indexOf('=');
        if (eqPos > 0) {
            String key = token.substring(0, eqPos);
            String val = token.substring(eqPos + 1);

            if (key == "CH")         cfg.tcaChannel = val.toInt();
            else if (key == "ADDR")  cfg.address = strtol(val.c_str(), NULL, 16);
            else if (key == "AIN") {
                if (val == "AIN0") cfg.mux = ADS_MUX_AIN0_AVSS;
                else if (val == "AIN1") cfg.mux = ADS_MUX_AIN1_AVSS;
                else if (val == "AIN2") cfg.mux = ADS_MUX_AIN2_AVSS;
                else if (val == "AIN3") cfg.mux = ADS_MUX_AIN3_AVSS;
            }
            else if (key == "REF") {
                if (val == "AVDD") cfg.vrefMode = ADS_VREF_AVDD;
                else if (val == "INT") cfg.vrefMode = ADS_VREF_INTERNAL;
            }
            else if (key == "GAIN") {
                uint8_t g = val.toInt();
                if (g == 1 || g == 2 || g == 4) cfg.gain = g;
            }
            else if (key == "DR")    cfg.adcRate = adsNearestRate(val.toInt());
            else if (key == "MODE") {
                cfg.continuousMode = (val == "CONT");
            }
            else if (key == "PR")    cfg.publishRate = constrain(val.toInt(), 1, 200);
        }
        if (commaPos == -1) break;
        startPos = commaPos + 1;
    }

    cfg.enabled = true;

    Serial.printf("ADS_OK:CFG,CH=%d,ADDR=0x%02X,DR=%d,GAIN=%d,REF=%s,MODE=%s,PR=%d\n",
        cfg.tcaChannel, cfg.address, cfg.adcRate, cfg.gain,
        cfg.vrefMode == ADS_VREF_AVDD ? "AVDD" : "INT",
        cfg.continuousMode ? "CONT" : "SINGLE",
        cfg.publishRate);
}

#endif // ADS122C04_H

