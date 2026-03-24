#include <Arduino.h>
#include <Wire.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

// 新增模块头文�?
#include "i2c_mux.h"
#include "ads122c04.h"
#include "protocol_packets.h"

// ============== PID 参数定义（可由上位机配置�?==============
float g_pidKp = 0.14f;            // 比例系数
float g_pidKi = 0.015f;           // 积分系数
float g_pidKd = 0.06f;            // 微分系数
float g_pidOutputMin = 1.0f;      // 最小输�?
float g_pidOutputMax = 6.0f;      // 最大输�?
#define PID_DEADBAND 0.1f
#define PID_INTEGRAL_LIMIT 25.0f  // 积分限幅

// ============== 平滑度优先参�?==============
#define PID_STARTUP_SPEED_RATIO 0.5f  // 启动速度 = 最大速度 * 0.5 (中位速度启动)
#define PID_SMOOTH_RAMP_TIME 200      // 平滑过渡时间 (ms)
#define PID_JERK_LIMIT 50.0f          // 加速度变化率限�?(RPM/s²)
#define PID_RAMP_RATE 5.0f            // RPM/周期
#define PID_INTEGRAL_ZONE 10.0f       // 积分区间
#define PID_DAMPING_ZONE 2.0f         // 阻尼区间

#define CAL_TIMEOUT 15000
#define CAL_STABLE_COUNT 15
#define CAL_INTERVAL 20

#define PID_MOVE_TIMEOUT 30000
#define PID_MOVE_STABLE_COUNT 10

#define PID_PACKET_INTERVAL 20  // 50Hz 数据包发送间�?

// ============== 角度流控�?==============
bool g_angleStreamActive = false;
unsigned long g_lastAngleSendTime = 0;
const unsigned long ANGLE_SEND_INTERVAL = 20;  // 50Hz

// ============== PID 测试模式相关定义 ==============
#define PID_TEST_MAX_SAMPLES 200    // 最大采样点�?
#define PID_TEST_SAMPLE_INTERVAL 20 // 采样间隔 (ms)

// 测试数据采集结构
struct PIDTestData {
    bool active;                    // 测试是否进行�?
    uint8_t motorIndex;             // 测试电机
    float targetAngle;              // 转动角度增量（配置值）
    float actualTargetAngle;        // 实际目标角度（计算后�?
    bool direction;                 // 转动方向: true=正转(F), false=反转(B)
    uint8_t currentRun;             // 当前轮次
    uint8_t totalRuns;              // 总轮�?
    
    // 单轮数据采集
    unsigned long runStartTime;     // 本轮开始时�?
    float initialAngle;             // 初始角度
    float samples[PID_TEST_MAX_SAMPLES];       // 角度采样
    float outputSamples[PID_TEST_MAX_SAMPLES]; // 输出采样
    uint16_t sampleCount;           // 采样计数
    unsigned long lastSampleTime;   // 上次采样时间
    
    // 边缘计算中间变量
    float maxAngle;                 // 过程中最大角�?
    float minAngle;                 // 过程中最小角�?
    int8_t lastErrorSign;           // 上次误差符号
    uint8_t zeroCrossCount;         // 过零次数
    bool hasConverged;              // 是否已收�?
    unsigned long convergenceTime;  // 收敛时刻
};

PIDTestData pidTest = {false, 0, 0, 0, 0, 0, 0, 0, {}, {}, 0, 0, 0, 0, 0, 0, false, 0};

// 评分权重配置
struct ScoreWeights {
    uint8_t convergence;   // 收敛时间权重 (默认30)
    uint8_t overshoot;     // 过冲权重 (默认25)
    uint8_t steadyError;   // 稳态误差权�?(默认15)
    uint8_t smoothness;    // 平滑度权�?(默认20)
    uint8_t oscillation;   // 振荡权重 (默认10)
};

// 权重: 收敛35, 过冲20, 稳态误�?0, 平滑�?5, 振荡10
ScoreWeights scoreWeights = {35, 20, 20, 15, 10};

// 校准状态枚�?
enum CalibrationState {
    CAL_IDLE, CAL_RUNNING, CAL_SUCCESS, CAL_TIMEOUT_ERR, CAL_SENSOR_ERR
};

// PID 控制器结�?
struct PIDController {
    float Kp, Ki, Kd;
    float integral;
    float lastError;
    float outputMin, outputMax;
    float deadband;
    unsigned long lastTime;
    float lastAcceleration;  // 用于jerk限制
    
    void reset() {
        integral = 0;
        lastError = 0;
        lastTime = 0;
        lastAcceleration = 0;
    }
};

// 校准上下文结�?
struct CalibrationContext {
    CalibrationState state;
    uint8_t motorMask;
    float targetAngle[4];
    unsigned long startTime;
    uint8_t stableCount[4];
    uint8_t sensorErrorCount[4];
    bool motorDone[4];
    PIDController pid[4];
};

CalibrationContext calCtx;

// ============== 可配�?I2C 通道 (i2c_mux.h 中声明为 extern) ==============
uint8_t g_angleChannels[4] = {0, 3, 4, 7};
uint8_t g_spectroChannel = 2;

// ============== ADS122C04 全局状�?==============
ADSConfig g_adsConfig;
unsigned long g_lastSpectroPollTime = 0;
int32_t g_lastSpectroRawCode = 0;
float g_lastSpectroVoltage = 0.0f;
uint8_t g_lastSpectroStatus = SPECTRO_STATUS_NOT_CONFIG;

// --- 引脚定义 ---
#define X_STP 13
#define X_DIR 12
#define Y_STP 14
#define Y_DIR 27
#define Z_STP 26
#define Z_DIR 25
#define A_STP 33
#define A_DIR 32
#define BOOT 0

// ============== 进样泵控制定�?==============
#define PUMP_PIN 2              // 进样泵控制引�?(GPIO2)
#define PUMP_PWM_CHANNEL 0      // LEDC PWM 通道
#define PUMP_PWM_FREQ 1000      // PWM 频率 (Hz)
#define PUMP_PWM_RESOLUTION 8   // PWM 分辨�?(8�? 0-255)

// 进样泵状�?
struct PumpState {
    bool enabled;               // 进样泵启停状�?
    uint8_t speedPercent;       // 转速百分比 (0-100)
    uint8_t pwmDuty;            // 实际PWM占空�?(0-255)
};

PumpState pumpState = {false, 0, 0};

// --- 电机参数 (TCA/MT6701 常量已移�?i2c_mux.h) ---
const float STEP_PER_DEGREE = 1.0 / (2.25/379.16);
const float STEPS_PER_REV = 360.0 * STEP_PER_DEGREE;
const float MIN_INTERVAL = 50;
const float GLOBAL_DUTY_CYCLE = 0.45;

SemaphoreHandle_t motorMutex;

struct MotorState {
    bool enabled;
    bool direction;
    bool isContinuous;
    float rpm;
    unsigned long stepInterval;
    unsigned long lastStepTime;
    bool stepState;
    long targetSteps;
    long executedSteps;
    long stepsRemaining;
    long signedSteps;
    unsigned long highTime;
    unsigned long lowTime;
    bool currentDirection;
    bool justFinished;
    unsigned long finishTime;
    bool waitingToSend;
    
    // PID 定位模式
    bool isPIDMode;
    float pidTargetAngle;       // 存储环形目标 (0~360)，用于显�?
    float pidPrecision;
    uint8_t pidStableCount;
    uint8_t pidSensorErrCount;
    unsigned long pidStartTime;
    PIDController pidCtrl;
    
    // 解环角度追踪（多圈PID�?
    float lastRawAngle;         // 上一次传感器读数 (0~360)
    float absAngle;             // 连续累积角度
    float absTargetAngle;       // 绝对目标角度
    bool absAngleValid;         // 解环是否已初始化
    
    // 二进制数据包相关
    float pidInitialAngle;
    long pidStartSteps;
    long pidStartSignedSteps;
    unsigned long lastPacketTime;
    
    // 速度斜坡控制
    float lastOutputRPM;
    
    // 重置解环角度（防溢出�?
    void resetAbsAngle(float currentRaw) {
        absAngle = 0.0f;
        lastRawAngle = currentRaw;
        absAngleValid = true;
    }
};

MotorState motors[4] = {
    {false, true, false, 0, 0, 0, false, 0, 0, 0, 0, 0, 0, true, false, 0, false, false, 0, 0.1f, 0, 0, 0, {}, 0, 0, 0, false, 0, 0, 0, 0, 0},
    {false, true, false, 0, 0, 0, false, 0, 0, 0, 0, 0, 0, true, false, 0, false, false, 0, 0.1f, 0, 0, 0, {}, 0, 0, 0, false, 0, 0, 0, 0, 0},
    {false, true, false, 0, 0, 0, false, 0, 0, 0, 0, 0, 0, true, false, 0, false, false, 0, 0.1f, 0, 0, 0, {}, 0, 0, 0, false, 0, 0, 0, 0, 0},
    {false, true, false, 0, 0, 0, false, 0, 0, 0, 0, 0, 0, true, false, 0, false, false, 0, 0.1f, 0, 0, 0, {}, 0, 0, 0, false, 0, 0, 0, 0, 0}
};

const byte motorPins[4][2] = {
    {X_STP, X_DIR}, {Y_STP, Y_DIR}, {Z_STP, Z_DIR}, {A_STP, A_DIR}
};

// --- 函数声明 ---
void TaskComms(void *pvParameters);
float readAngleWithRetry(uint8_t channel);
void sendAngles();
float rpmToInterval(float rpm);
void updateDutyCycleTiming(MotorState &m);
void setMotorDirection(byte dirPin, bool direction);
void parseCommand(String cmd);
void stepMotor(MotorState &m, byte stepPin, byte dirPin, int idx);
void initCalibration(uint8_t motorMask);
void stopCalibration();
void runCalibrationPID();
float computePID(PIDController &pid, float currentAngle, float targetAngle);
float computePIDWithSmoothing(PIDController &pid, float currentAngle, float targetAngle, MotorState &motor);
float normalizeAngleError(float target, float current);
void sendCalibrationStatus();
void initPIDMove(int motorIndex, float targetAngle, float precision);
void stopPIDMove(int motorIndex);
void runMotorPID();
void stopAllPIDMoves();
void sendPIDDataPacket(int motorIndex, float currentAngle, float error, float pidOutput);

// 解环角度函数
float unwrapAngle(float newRaw, float lastRaw, float currentAbs);

// 直接误差PID计算（用于多圈控制）
float computePIDDirect(PIDController &pid, float error, MotorState &motor);

// PID测试模式函数声明
void parsePIDConfig(String cmd);
void parsePIDTest(String cmd);
void initPIDTest(uint8_t motorIndex, float targetAngle, bool direction, uint8_t runs);
void startNextTestRun();
void runPIDTestSampling();
void finishTestRun();
uint8_t calculateSmoothnessScore();
uint16_t calculateStartupJerk();
uint8_t calculateTotalScore(uint16_t convTime, int16_t overshoot, int16_t finalErr, uint8_t oscCount, uint8_t smoothness);
void stopPIDTest();

// 角度流函数声�?
void sendAnglePacket();

// --- 进样泵控制函�?---
void setPumpSpeed(uint8_t speedPercent) {
    if (speedPercent > 100) speedPercent = 100;
    pumpState.speedPercent = speedPercent;
    pumpState.pwmDuty = (uint8_t)((float)speedPercent / 100.0f * 255.0f);
    if (pumpState.enabled) {
        ledcWrite(PUMP_PWM_CHANNEL, pumpState.pwmDuty);
    }
}

void setPumpEnabled(bool enabled) {
    pumpState.enabled = enabled;
    if (enabled) {
        ledcWrite(PUMP_PWM_CHANNEL, pumpState.pwmDuty);
    } else {
        ledcWrite(PUMP_PWM_CHANNEL, 0);
    }
}

// --- Setup ---
void setup() {
    pinMode(BOOT, OUTPUT);
    digitalWrite(BOOT, LOW);

    for(auto &p : motorPins) {
        pinMode(p[0], OUTPUT);
        pinMode(p[1], OUTPUT);
        digitalWrite(p[1], LOW);
    }

    // 初始化进样泵 PWM
    ledcSetup(PUMP_PWM_CHANNEL, PUMP_PWM_FREQ, PUMP_PWM_RESOLUTION);
    ledcAttachPin(PUMP_PIN, PUMP_PWM_CHANNEL);
    ledcWrite(PUMP_PWM_CHANNEL, 0);  // 初始停止

    Wire.begin(21, 22);
    Wire.setClock(100000);
    Serial.begin(115200);
    delay(100);

    // 初始化 ADS122C04 默认配置
    adsConfigDefault(g_adsConfig);

    motorMutex = xSemaphoreCreateMutex();

    Serial.printf("Global duty cycle set to: %.1f%%\n", GLOBAL_DUTY_CYCLE * 100);
    Serial.println("System Initialized. Core 1: Motors, Core 0: Comms/Sensors.");
    Serial.printf("PID Params: Kp=%.4f, Ki=%.5f, Kd=%.4f\n", g_pidKp, g_pidKi, g_pidKd);
    Serial.println("Injection pump initialized on GPIO2.");

    xTaskCreatePinnedToCore(TaskComms, "Comms", 8192, NULL, 1, NULL, 0);
}

// --- Loop (Core 1 - Motor Task) ---
void loop() {
    if (xSemaphoreTake(motorMutex, 0) == pdTRUE) {
        for(int i=0; i<4; i++) {
            stepMotor(motors[i], motorPins[i][0], motorPins[i][1], i);
        }
        xSemaphoreGive(motorMutex);
    }
    delayMicroseconds(5);
}


// --- Task Comms (Core 0) ---
void TaskComms(void *pvParameters) {
    String inputBuffer = "";
    inputBuffer.reserve(128);
    
    unsigned long lastCalTime = 0;
    
    calCtx.state = CAL_IDLE;
    calCtx.motorMask = 0;
    
    while(true) {
        while(Serial.available()) {
            char c = Serial.read();
            if(c == '\n') {
                inputBuffer.trim();
                if(inputBuffer.length() > 0) {
                    // ===== 新增：PID参数配置指令 =====
                    if (inputBuffer.startsWith("PIDCFG:")) {
                        parsePIDConfig(inputBuffer);
                    }
                    // ===== 新增：PID测试模式指令 =====
                    else if (inputBuffer.startsWith("PIDTEST:")) {
                        parsePIDTest(inputBuffer);
                    }
                    // ===== 新增：查询当前PID参数 =====
                    else if (inputBuffer == "PIDQUERY") {
                        Serial.printf("PIDPARAM:%.4f,%.5f,%.4f,%.1f,%.1f\n", 
                            g_pidKp, g_pidKi, g_pidKd, g_pidOutputMin, g_pidOutputMax);
                    }
                    // ===== 新增：停止测�?=====
                    else if (inputBuffer == "PIDTESTSTOP") {
                        stopPIDTest();
                    }
                    // ===== 新增：配置评分权�?=====
                    else if (inputBuffer.startsWith("PIDWEIGHTS:")) {
                        // 格式: PIDWEIGHTS:conv,ovs,err,smooth,osc
                        int colonIdx = inputBuffer.indexOf(':');
                        String params = inputBuffer.substring(colonIdx + 1);
                        
                        int c1 = params.indexOf(',');
                        int c2 = params.indexOf(',', c1+1);
                        int c3 = params.indexOf(',', c2+1);
                        int c4 = params.indexOf(',', c3+1);
                        
                        if (c1 > 0 && c2 > c1 && c3 > c2 && c4 > c3) {
                            scoreWeights.convergence = params.substring(0, c1).toInt();
                            scoreWeights.overshoot = params.substring(c1+1, c2).toInt();
                            scoreWeights.steadyError = params.substring(c2+1, c3).toInt();
                            scoreWeights.smoothness = params.substring(c3+1, c4).toInt();
                            scoreWeights.oscillation = params.substring(c4+1).toInt();
                            
                            Serial.printf("PIDWEIGHTS_OK:%d,%d,%d,%d,%d\n", 
                                scoreWeights.convergence, scoreWeights.overshoot,
                                scoreWeights.steadyError, scoreWeights.smoothness,
                                scoreWeights.oscillation);
                        } else {
                            Serial.println("PIDWEIGHTS_ERR:PARSE");
                        }
                    }
                    // ===== 进样泵控制指�?=====
                    // PUMP:ON - 启动进样�?
                    // PUMP:OFF - 停止进样�?
                    // PUMP:SPD:xx - 设置转速百分比 (0-100)
                    // PUMP:SET:xx - 设置转速并启动 (0=停止)
                    else if (inputBuffer.startsWith("PUMP:")) {
                        String pumpCmd = inputBuffer.substring(5);
                        if (pumpCmd == "ON") {
                            setPumpEnabled(true);
                            Serial.printf("PUMP_OK:ON,SPD=%d\n", pumpState.speedPercent);
                        } else if (pumpCmd == "OFF") {
                            setPumpEnabled(false);
                            Serial.printf("PUMP_OK:OFF\n");
                        } else if (pumpCmd.startsWith("SPD:")) {
                            int speed = pumpCmd.substring(4).toInt();
                            if (speed >= 0 && speed <= 100) {
                                setPumpSpeed((uint8_t)speed);
                                Serial.printf("PUMP_OK:SPD=%d\n", pumpState.speedPercent);
                            } else {
                                Serial.println("PUMP_ERR:SPD_RANGE");
                            }
                        } else if (pumpCmd.startsWith("SET:")) {
                            int speed = pumpCmd.substring(4).toInt();
                            if (speed >= 0 && speed <= 100) {
                                setPumpSpeed((uint8_t)speed);
                                setPumpEnabled(speed > 0);
                                Serial.printf("PUMP_OK:SET=%d,%s\n", speed, speed > 0 ? "ON" : "OFF");
                            } else {
                                Serial.println("PUMP_ERR:SET_RANGE");
                            }
                        } else if (pumpCmd == "STATUS") {
                            Serial.printf("PUMP_STATUS:%s,SPD=%d\n",
                                pumpState.enabled ? "ON" : "OFF", pumpState.speedPercent);
                        } else {
                            Serial.println("PUMP_ERR:UNKNOWN_CMD");
                        }
                    }
                    // ===== I2C 通道映射指令 =====
                    else if (inputBuffer.startsWith("I2CMAP:")) {
                        parseI2CMapCommand(inputBuffer);
                    }
                    else if (inputBuffer == "I2CMAP?") {
                        Serial.printf("I2CMAP_OK:X=%d,Y=%d,Z=%d,A=%d,SPEC=%d\n",
                            g_angleChannels[0], g_angleChannels[1], g_angleChannels[2], g_angleChannels[3], g_spectroChannel);
                    }
                    // ===== ADS122C04 配置与控制指令 =====
                    else if (inputBuffer.startsWith("ADSCFG:")) {
                        parseADSConfigCommand(inputBuffer, g_adsConfig);
                    }
                    else if (inputBuffer == "ADSSTART") {
                        if (!g_adsConfig.enabled) {
                            Serial.println("ADS_ERR:CONFIG");
                        } else {
                            invalidateTcaCache();
                            if (selectTcaChannel(g_adsConfig.tcaChannel)) {
                                if (adsInitAndStart(g_adsConfig)) {
                                    g_lastSpectroPollTime = millis();
                                    g_lastSpectroStatus = 0;
                                    Serial.println("ADS_OK:START");
                                } else {
                                    g_adsConfig.running = false;
                                    Serial.println("ADS_ERR:I2C");
                                }
                            } else {
                                Serial.println("ADS_ERR:I2C");
                            }
                            invalidateTcaCache();
                        }
                    }
                    else if (inputBuffer == "ADSSTOP") {
                        adsStop(g_adsConfig);
                        Serial.println("ADS_OK:STOP");
                    }
                    else if (inputBuffer == "ADSSTATUS?") {
                        Serial.printf("ADS_STATUS:%s,CH=%d,ADDR=0x%02X,DR=%d,GAIN=%d,REF=%s\n",
                            g_adsConfig.running ? "RUNNING" : "STOPPED",
                            g_adsConfig.tcaChannel, g_adsConfig.address, g_adsConfig.adcRate,
                            g_adsConfig.gain, g_adsConfig.vrefMode == ADS_VREF_AVDD ? "AVDD" : "INT");
                    }
                    // ===== 角度流控制指令 =====
                    else if (inputBuffer == "ANGLESTREAM_START") {
                        g_angleStreamActive = true;
                        g_lastAngleSendTime = millis();
                        Serial.println("ANGLESTREAM_OK");
                    }
                    else if (inputBuffer == "ANGLESTREAM_STOP") {
                        g_angleStreamActive = false;
                        Serial.println("ANGLESTREAM_STOPPED");
                    }
                    // 单次获取角度（兼容性保留，改为二进制包�?
                    else if(inputBuffer == "GETANGLE") {
                        sendAnglePacket();
                    }
                    // 旧版流控制指令（映射到新指令�?
                    else if (inputBuffer == "STREAM1") {
                        g_angleStreamActive = true;
                        g_lastAngleSendTime = millis();
                        Serial.println("ANGLESTREAM_OK");
                    } else if (inputBuffer == "STREAM0") {
                        g_angleStreamActive = false;
                        Serial.println("ANGLESTREAM_STOPPED");
                    } else if (inputBuffer == "PIDSTOP") {
                        if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                            stopAllPIDMoves();
                            xSemaphoreGive(motorMutex);
                        }
                    } else if (inputBuffer.startsWith("CAL")) {
                        if (inputBuffer == "CALSTOP") {
                            stopCalibration();
                        } else if (inputBuffer == "CALSTATUS") {
                            sendCalibrationStatus();
                        } else {
                            uint8_t mask = 0;
                            for (int i = 3; i < inputBuffer.length(); i++) {
                                char m = inputBuffer[i];
                                if (m == 'X') mask |= 0x01;
                                else if (m == 'Y') mask |= 0x02;
                                else if (m == 'Z') mask |= 0x04;
                                else if (m == 'A') mask |= 0x08;
                            }
                            if (mask > 0) {
                                if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                                    initCalibration(mask);
                                    xSemaphoreGive(motorMutex);
                                }
                            } else {
                                Serial.println("CAL_ERR:NO_MOTOR");
                            }
                        }
                    } else {
                        if (calCtx.state == CAL_RUNNING) {
                            Serial.println("BUSY:CALIBRATING");
                        } else if (pidTest.active) {
                            Serial.println("BUSY:TESTING");
                        } else {
                            if(xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                                parseCommand(inputBuffer);
                                xSemaphoreGive(motorMutex);
                            }
                        }
                    }
                }
                inputBuffer = "";
            } else {
                inputBuffer += c;
            }
        }

        // 校准PID循环
        if (calCtx.state == CAL_RUNNING) {
            if (millis() - lastCalTime >= CAL_INTERVAL) {
                runCalibrationPID();
                lastCalTime = millis();
            }
        }
        
        // 普通PID定位循环（包括测试模式，因为测试模式也使用PID定位�?
        if (calCtx.state != CAL_RUNNING) {
            if (millis() - lastCalTime >= CAL_INTERVAL) {
                runMotorPID();
                lastCalTime = millis();
            }
        }
        
        // ===== PID测试模式采样（在PID控制之后执行�?=====
        if (pidTest.active) {
            runPIDTestSampling();
        }

        // 完成信号处理
        bool needSend = false;
        if (calCtx.state != CAL_RUNNING && !pidTest.active) {
            if(xSemaphoreTake(motorMutex, 10) == pdTRUE) {
                for(int i=0; i<4; i++) {
                    if(motors[i].justFinished) {
                        motors[i].justFinished = false;
                        motors[i].waitingToSend = true;
                        motors[i].finishTime = millis();
                    }
                    if(motors[i].waitingToSend && millis() - motors[i].finishTime >= 500) {
                        motors[i].waitingToSend = false;
                        needSend = true;
                    }
                }
                xSemaphoreGive(motorMutex);
            }
        }
        
        // 角度流发送（50Hz�?
        if (g_angleStreamActive) {
            unsigned long now = millis();
            if (now - g_lastAngleSendTime >= ANGLE_SEND_INTERVAL) {
                g_lastAngleSendTime = now;
                sendAnglePacket();
            }
        }
        
        // 完成信号发送角�?
        if(needSend) {
            sendAnglePacket();
        }

        // ===== ADS122C04 分光数据轮询与发送 =====
        if (g_adsConfig.running && g_adsConfig.publishRate > 0) {
            unsigned long now = millis();
            unsigned long specInterval = 1000 / g_adsConfig.publishRate;
            if (now - g_lastSpectroPollTime >= specInterval) {
                g_lastSpectroPollTime = now;

                // 切换到 ADS 所在的 TCA 通道
                invalidateTcaCache();
                if (selectTcaChannel(g_adsConfig.tcaChannel)) {
                    int32_t rawCode = 0;
                    if (adsReadData(g_adsConfig.address, &rawCode)) {
                        float voltage = codeToVoltage(rawCode, g_adsConfig.vrefValue, (float)g_adsConfig.gain);
                        g_lastSpectroRawCode = rawCode;
                        g_lastSpectroVoltage = voltage;

                        uint8_t status = SPECTRO_STATUS_VALID;
                        // 饱和检测
                        if (rawCode >= 8388607 || rawCode <= -8388608) {
                            status |= SPECTRO_STATUS_SATURATED;
                        }
                        g_lastSpectroStatus = status;

                        // 发送 0xDD 分光数据包
                        SpectroDataPacket pkt;
                        pkt.head1 = PACKET_HEADER1;
                        pkt.head2 = HEADER2_SPECTRO;
                        pkt.timestamp_ms = now;
                        pkt.tca_channel = g_adsConfig.tcaChannel;
                        pkt.status = status;
                        pkt.raw_code = rawCode;
                        pkt.voltage = voltage;

                        // XOR 校验和 (从 head2 到 voltage)
                        uint8_t* pktData = (uint8_t*)&pkt.head2;
                        pkt.checksum = 0;
                        int checksumLen = sizeof(SpectroDataPacket) - 3; // 减去 head1, checksum, tail
                        for (int ci = 0; ci < checksumLen; ci++) {
                            pkt.checksum ^= pktData[ci];
                        }
                        pkt.tail = PACKET_TAIL;

                        Serial.write((uint8_t*)&pkt, sizeof(pkt));
                    } else {
                        g_lastSpectroStatus = SPECTRO_STATUS_I2C_ERROR;
                    }
                } else {
                    g_lastSpectroStatus = SPECTRO_STATUS_I2C_ERROR;
                }
                invalidateTcaCache(); // 恢复 TCA 缓存，下次角度读取会重新选择
            }
        }

        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
}

// ============== PID参数配置解析 ==============
void parsePIDConfig(String cmd) {
    // 格式: PIDCFG:Kp,Ki,Kd[,OutputMin,OutputMax]
    int colonIdx = cmd.indexOf(':');
    if (colonIdx == -1) {
        Serial.println("PIDCFG_ERR:FORMAT");
        return;
    }
    
    String params = cmd.substring(colonIdx + 1);
    float kp, ki, kd;
    float outMin = g_pidOutputMin;
    float outMax = g_pidOutputMax;
    
    int comma1 = params.indexOf(',');
    int comma2 = params.indexOf(',', comma1 + 1);
    int comma3 = params.indexOf(',', comma2 + 1);
    int comma4 = params.indexOf(',', comma3 + 1);
    
    if (comma1 == -1 || comma2 == -1) {
        Serial.println("PIDCFG_ERR:PARAMS");
        return;
    }
    
    kp = params.substring(0, comma1).toFloat();
    ki = params.substring(comma1 + 1, comma2).toFloat();
    
    if (comma3 != -1) {
        kd = params.substring(comma2 + 1, comma3).toFloat();
        if (comma4 != -1) {
            outMin = params.substring(comma3 + 1, comma4).toFloat();
            outMax = params.substring(comma4 + 1).toFloat();
        } else {
            outMin = params.substring(comma3 + 1).toFloat();
        }
    } else {
        kd = params.substring(comma2 + 1).toFloat();
    }
    
    // 参数范围检�?
    if (kp < 0.01f || kp > 2.0f) { Serial.println("PIDCFG_ERR:KP_RANGE"); return; }
    if (ki < 0.0f || ki > 1.0f) { Serial.println("PIDCFG_ERR:KI_RANGE"); return; }
    if (kd < 0.0f || kd > 1.0f) { Serial.println("PIDCFG_ERR:KD_RANGE"); return; }
    if (outMin < 0.1f || outMin > 5.0f) { Serial.println("PIDCFG_ERR:OUTMIN_RANGE"); return; }
    if (outMax < 1.0f || outMax > 20.0f) { Serial.println("PIDCFG_ERR:OUTMAX_RANGE"); return; }
    
    // 更新全局参数
    g_pidKp = kp;
    g_pidKi = ki;
    g_pidKd = kd;
    g_pidOutputMin = outMin;
    g_pidOutputMax = outMax;
    
    Serial.printf("PIDCFG_OK:%.4f,%.5f,%.4f,%.1f,%.1f\n", g_pidKp, g_pidKi, g_pidKd, g_pidOutputMin, g_pidOutputMax);
}

// ============== PID测试模式解析 ==============
void parsePIDTest(String cmd) {
    // 格式: PIDTEST:<Motor>,<Dir>,<Angle>,<Runs>
    // 示例: PIDTEST:X,F,60.0,5  X电机正转60°测试5�?
    int colonIdx = cmd.indexOf(':');
    if (colonIdx == -1) {
        Serial.println("PIDTEST_ERR:FORMAT");
        return;
    }
    
    String params = cmd.substring(colonIdx + 1);
    int comma1 = params.indexOf(',');
    int comma2 = params.indexOf(',', comma1 + 1);
    int comma3 = params.indexOf(',', comma2 + 1);
    
    if (comma1 == -1 || comma2 == -1 || comma3 == -1) {
        Serial.println("PIDTEST_ERR:PARAMS");
        return;
    }
    
    char motorChar = params.charAt(0);
    uint8_t motorIndex;
    if (motorChar == 'X') motorIndex = 0;
    else if (motorChar == 'Y') motorIndex = 1;
    else if (motorChar == 'Z') motorIndex = 2;
    else if (motorChar == 'A') motorIndex = 3;
    else {
        Serial.println("PIDTEST_ERR:MOTOR");
        return;
    }
    
    // 解析方向: F=正转, B=反转
    char dirChar = params.charAt(comma1 + 1);
    bool direction = (dirChar == 'F' || dirChar == 'f');
    
    float targetAngle = params.substring(comma2 + 1, comma3).toFloat();
    uint8_t runs = params.substring(comma3 + 1).toInt();
    
    if (runs < 1 || runs > 20) {
        Serial.println("PIDTEST_ERR:RUNS_RANGE");
        return;
    }
    
    // 角度必须为正（方向由 dir 决定�?
    if (targetAngle < 0) targetAngle = fabs(targetAngle);
    
    initPIDTest(motorIndex, targetAngle, direction, runs);
}

// ============== PID测试模式实现 ==============
void initPIDTest(uint8_t motorIndex, float targetAngle, bool direction, uint8_t runs) {
    pidTest.active = true;
    pidTest.motorIndex = motorIndex;
    pidTest.targetAngle = targetAngle;
    pidTest.direction = direction;
    pidTest.currentRun = 0;
    pidTest.totalRuns = runs;
    
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    Serial.printf("PIDTEST_START:%c,%c,%d\n", motorNames[motorIndex], direction ? 'F' : 'B', runs);
    
    startNextTestRun();
}

void startNextTestRun() {
    if (pidTest.currentRun >= pidTest.totalRuns) {
        // 所有测试完�?
        pidTest.active = false;
        const char motorNames[] = {'X', 'Y', 'Z', 'A'};
        Serial.printf("PIDTEST_DONE:%c\n", motorNames[pidTest.motorIndex]);
        return;
    }
    
    Serial.printf("PIDTEST_RUN:%d\n", pidTest.currentRun);
    
    // 重置采集数据
    pidTest.sampleCount = 0;
    pidTest.runStartTime = millis();
    pidTest.lastSampleTime = 0;
    pidTest.maxAngle = -999;
    pidTest.minAngle = 999;
    pidTest.lastErrorSign = 0;
    pidTest.zeroCrossCount = 0;
    pidTest.hasConverged = false;
    pidTest.convergenceTime = 0;
    
    // 读取初始角度
    pidTest.initialAngle = readAngleWithRetry(g_angleChannels[pidTest.motorIndex]);
    if (pidTest.initialAngle < 0) pidTest.initialAngle = 0;
    
    // 获取电机状态以初始�?更新解环角度
    MotorState* m = &motors[pidTest.motorIndex];
    if (!m->absAngleValid) {
        m->absAngle = 0.0f;
        m->lastRawAngle = pidTest.initialAngle;
        m->absAngleValid = true;
    } else {
        m->absAngle = unwrapAngle(pidTest.initialAngle, m->lastRawAngle, m->absAngle);
        m->lastRawAngle = pidTest.initialAngle;
    }
    
    // 根据方向计算绝对目标角度
    int sign = pidTest.direction ? +1 : -1;
    m->absTargetAngle = m->absAngle + sign * pidTest.targetAngle;
    
    // 计算环形目标（用于显示）
    float displayTarget = fmod(m->absTargetAngle, 360.0f);
    if (displayTarget < 0) displayTarget += 360.0f;
    pidTest.actualTargetAngle = displayTarget;
    
    // 启动 PID 定位
    if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
        m->isPIDMode = true;
        m->pidTargetAngle = displayTarget;
        m->pidPrecision = 0.1f;
        m->pidStableCount = 0;
        m->pidSensorErrCount = 0;
        m->pidStartTime = millis();
        m->pidInitialAngle = pidTest.initialAngle;
        m->pidStartSteps = m->executedSteps;
        m->pidStartSignedSteps = m->signedSteps;
        m->lastPacketTime = 0;
        m->lastOutputRPM = 0;
        
        m->pidCtrl.Kp = g_pidKp;
        m->pidCtrl.Ki = g_pidKi;
        m->pidCtrl.Kd = g_pidKd;
        m->pidCtrl.outputMin = g_pidOutputMin;
        m->pidCtrl.outputMax = g_pidOutputMax;
        m->pidCtrl.deadband = 0.1f;
        m->pidCtrl.reset();
        
        m->enabled = false;
        m->stepInterval = 0;
        m->isContinuous = false;
        
        xSemaphoreGive(motorMutex);
    }
    
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    Serial.printf("PID_START:%c,delta=%.1f,dir=%c,prec=0.10,absTarget=%.1f\n", 
        motorNames[pidTest.motorIndex], pidTest.targetAngle, 
        pidTest.direction ? 'F' : 'B', m->absTargetAngle);
}

void stopPIDTest() {
    if (pidTest.active) {
        pidTest.active = false;
        if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
            stopPIDMove(pidTest.motorIndex);
            xSemaphoreGive(motorMutex);
        }
        Serial.println("PIDTEST_STOPPED");
    }
}


void runPIDTestSampling() {
    if (!pidTest.active) return;
    
    MotorState* m = &motors[pidTest.motorIndex];
    unsigned long now = millis();
    
    // 检查PID是否完成
    if (!m->isPIDMode) {
        // PID完成，结束本轮测�?
        finishTestRun();
        
        // 等待一段时间后开始下一轮（连续正转，不返回�?
        delay(2000);  // 确保电机完全稳定
        pidTest.currentRun++;
        startNextTestRun();
        return;
    }
    
    // 采样
    if (now - pidTest.lastSampleTime >= PID_TEST_SAMPLE_INTERVAL) {
        if (pidTest.sampleCount < PID_TEST_MAX_SAMPLES) {
            float angle = readAngleWithRetry(g_angleChannels[pidTest.motorIndex]);
            if (angle >= 0 && angle <= 360) {
                pidTest.samples[pidTest.sampleCount] = angle;
                pidTest.outputSamples[pidTest.sampleCount] = m->lastOutputRPM;
                pidTest.sampleCount++;
                
                // 更新极�?
                if (angle > pidTest.maxAngle) pidTest.maxAngle = angle;
                if (angle < pidTest.minAngle) pidTest.minAngle = angle;
                
                // 振荡检测（误差过零�? 使用实际目标角度
                float error = normalizeAngleError(pidTest.actualTargetAngle, angle);
                int8_t errorSign = (error > 0.1f) ? 1 : ((error < -0.1f) ? -1 : 0);
                if (pidTest.lastErrorSign != 0 && errorSign != 0 && 
                    errorSign != pidTest.lastErrorSign) {
                    pidTest.zeroCrossCount++;
                }
                if (errorSign != 0) pidTest.lastErrorSign = errorSign;
                
                // 收敛检�?(死区0.1°)
                if (!pidTest.hasConverged && fabs(error) < 0.1f) {
                    pidTest.hasConverged = true;
                    pidTest.convergenceTime = now;
                }
            }
        }
        pidTest.lastSampleTime = now;
    }
}

// ============== 边缘评分计算函数 ==============
uint8_t calculateSmoothnessScore() {
    if (pidTest.sampleCount < 10) return 50;
    
    float totalJerk = 0;
    float maxJerk = 0;
    int validCount = 0;
    
    // 计算输出的二阶差分（近似加速度变化率）
    for (int i = 2; i < pidTest.sampleCount; i++) {
        float accel1 = pidTest.outputSamples[i-1] - pidTest.outputSamples[i-2];
        float accel2 = pidTest.outputSamples[i] - pidTest.outputSamples[i-1];
        float jerk = fabs(accel2 - accel1);
        
        totalJerk += jerk;
        if (jerk > maxJerk) maxJerk = jerk;
        validCount++;
    }
    
    if (validCount == 0) return 50;
    
    float avgJerk = totalJerk / validCount;
    
    // 评分：jerk越小越好
    float jerkScore = 100.0f * (1.0f - constrain(avgJerk / 3.0f, 0.0f, 1.0f));
    
    // 考虑最大jerk的惩�?
    float maxJerkPenalty = constrain(maxJerk / 8.0f, 0.0f, 0.3f);
    jerkScore *= (1.0f - maxJerkPenalty);
    
    return (uint8_t)constrain(jerkScore, 0, 100);
}

uint16_t calculateStartupJerk() {
    if (pidTest.sampleCount < 5) return 0;
    
    // 分析�?个采样点的加速度变化
    float maxStartupJerk = 0;
    for (int i = 2; i < min(5, (int)pidTest.sampleCount); i++) {
        float accel1 = pidTest.outputSamples[i-1] - pidTest.outputSamples[i-2];
        float accel2 = pidTest.outputSamples[i] - pidTest.outputSamples[i-1];
        float jerk = fabs(accel2 - accel1);
        if (jerk > maxStartupJerk) maxStartupJerk = jerk;
    }
    
    return (uint16_t)(maxStartupJerk * 100);
}

uint8_t calculateTotalScore(uint16_t convTime, int16_t overshoot, 
                            int16_t finalErr, uint8_t oscCount, 
                            uint8_t smoothness) {
    float score = 0;
    
    // 1. 收敛时间评分 (目标: <2000ms 满分, >5000ms 0�?
    float convScore;
    if (convTime < 2000) {
        convScore = 100.0f * (1.0f - (float)convTime / 2000.0f);
    } else if (convTime < 5000) {
        convScore = 50.0f * (1.0f - (float)(convTime - 2000) / 3000.0f);
    } else {
        convScore = 0;
    }
    score += convScore * scoreWeights.convergence / 100.0f;
    
    // 2. 过冲评分 (目标: 0过冲满分, >2�?�?
    float overshootDeg = fabs(overshoot) / 100.0f;
    float overshootScore;
    if (overshootDeg <= 0.05f) {
        overshootScore = 100;
    } else if (overshootDeg < 0.5f) {
        overshootScore = 100.0f - overshootDeg * 40.0f;
    } else if (overshootDeg < 2.0f) {
        overshootScore = 80.0f - (overshootDeg - 0.5f) * 53.3f;
    } else {
        overshootScore = 0;
    }
    score += overshootScore * scoreWeights.overshoot / 100.0f;
    
    // 3. 稳态误差评�?(目标: <0.1度满�? >1�?�?
    float errDeg = fabs(finalErr) / 100.0f;
    float errScore = 100.0f * (1.0f - constrain(errDeg / 1.0f, 0.0f, 1.0f));
    score += errScore * scoreWeights.steadyError / 100.0f;
    
    // 4. 平滑度评�?(直接使用)
    score += smoothness * scoreWeights.smoothness / 100.0f;
    
    // 5. 振荡评分 (目标: 0-1次满�? >5�?�?
    float oscScore;
    if (oscCount <= 1) {
        oscScore = 100;
    } else if (oscCount <= 3) {
        oscScore = 100.0f - (oscCount - 1) * 25.0f;
    } else {
        oscScore = max(0.0f, 50.0f - (oscCount - 3) * 25.0f);
    }
    score += oscScore * scoreWeights.oscillation / 100.0f;
    
    return (uint8_t)constrain(score, 0, 100);
}

void finishTestRun() {
    PIDTestResultPacket packet;
    
    packet.head1 = 0x55;
    packet.head2 = 0xBB;
    packet.motor_id = pidTest.motorIndex;
    packet.run_index = pidTest.currentRun;
    packet.total_runs = pidTest.totalRuns;
    
    // 收敛时间
    if (pidTest.hasConverged) {
        packet.convergence_time_ms = (uint16_t)(pidTest.convergenceTime - pidTest.runStartTime);
    } else {
        packet.convergence_time_ms = (uint16_t)(millis() - pidTest.runStartTime);
    }
    
    // 过冲计算 - 使用实际目标角度
    float expectedDirection = normalizeAngleError(pidTest.actualTargetAngle, pidTest.initialAngle);
    float overshoot = 0;
    
    if (expectedDirection > 0) {
        // 正向运动，检查是否超过目�?
        overshoot = normalizeAngleError(pidTest.maxAngle, pidTest.actualTargetAngle);
        if (overshoot < 0) overshoot = 0;
    } else {
        // 反向运动
        overshoot = normalizeAngleError(pidTest.actualTargetAngle, pidTest.minAngle);
        if (overshoot < 0) overshoot = 0;
    }
    packet.max_overshoot_x100 = (int16_t)(overshoot * 100);
    
    // 最终误�?- 使用实际目标角度
    float finalAngle = (pidTest.sampleCount > 0) ? pidTest.samples[pidTest.sampleCount - 1] : 0;
    float finalError = normalizeAngleError(pidTest.actualTargetAngle, finalAngle);
    packet.final_error_x100 = (int16_t)(finalError * 100);
    
    // 振荡次数
    packet.oscillation_count = pidTest.zeroCrossCount / 2;
    
    // 平滑度评�?
    packet.smoothness_score = calculateSmoothnessScore();
    
    // 启动冲击�?
    packet.startup_jerk_x100 = calculateStartupJerk();
    
    // 综合评分
    packet.total_score = calculateTotalScore(
        packet.convergence_time_ms,
        packet.max_overshoot_x100,
        packet.final_error_x100,
        packet.oscillation_count,
        packet.smoothness_score
    );
    
    // 校验�?
    uint8_t* data = (uint8_t*)&packet.motor_id;
    packet.checksum = 0;
    for (int i = 0; i < 14; i++) {
        packet.checksum ^= data[i];
    }
    packet.tail = 0x0A;
    
    // 发送二进制数据�?
    Serial.write((uint8_t*)&packet, sizeof(packet));
    
    // 同时发送文本格式便于调�?
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    Serial.printf("PIDTEST_RESULT:%c,run=%d,conv=%d,ovs=%.2f,err=%.2f,osc=%d,smooth=%d,score=%d\n",
        motorNames[pidTest.motorIndex],
        pidTest.currentRun,
        packet.convergence_time_ms,
        packet.max_overshoot_x100 / 100.0f,
        packet.final_error_x100 / 100.0f,
        packet.oscillation_count,
        packet.smoothness_score,
        packet.total_score
    );
}


// --- 辅助函数 ---
// readAngleWithRetry 现在委托�?i2c_mux.h 中的 readMt6701Angle
float readAngleWithRetry(uint8_t channel) {
    return readMt6701Angle(channel);
}

// ============== 二进制角度数据包发�?==============
void sendAnglePacket() {
    static float last_valid[4] = {0};
    AngleDataPacket packet;
    
    packet.head1 = PACKET_HEADER1;
    packet.head2 = HEADER2_ANGLE;
    
    // 读取四个电机角度 (使用可配置通道)
    packet.angles[0] = readAngleWithRetry(g_angleChannels[0]);  // X
    packet.angles[1] = readAngleWithRetry(g_angleChannels[1]);  // Y
    packet.angles[2] = readAngleWithRetry(g_angleChannels[2]);  // Z
    packet.angles[3] = readAngleWithRetry(g_angleChannels[3]);  // A
    
    // 处理无效读数
    for (int i = 0; i < 4; i++) {
        if (packet.angles[i] < 0 || packet.angles[i] > 360) {
            packet.angles[i] = last_valid[i];
        } else {
            last_valid[i] = packet.angles[i];
        }
    }
    
    // 计算校验�?(从head2开始到angles结束)
    uint8_t* data = (uint8_t*)&packet.head2;
    packet.checksum = 0;
    for (int i = 0; i < 17; i++) {  // head2(1) + angles(16) = 17
        packet.checksum ^= data[i];
    }
    packet.tail = 0x0A;
    
    Serial.write((uint8_t*)&packet, sizeof(packet));
}

// 保留旧函数名兼容性，内部调用新函�?
void sendAngles() {
    sendAnglePacket();
}

float rpmToInterval(float rpm) {
    return rpm > 0 ? 60000000.0 / (rpm * STEPS_PER_REV) : 0;
}

void updateDutyCycleTiming(MotorState &m) {
    if (m.stepInterval > 0) {
        m.highTime = m.stepInterval * GLOBAL_DUTY_CYCLE;
        m.lowTime = m.stepInterval - m.highTime;
        if (m.highTime < MIN_INTERVAL) m.highTime = MIN_INTERVAL;
        if (m.lowTime < MIN_INTERVAL) m.lowTime = MIN_INTERVAL;
    }
}

void setMotorDirection(byte dirPin, bool direction) {
    digitalWrite(dirPin, direction ? LOW : HIGH);
    delayMicroseconds(50);
}

void stepMotor(MotorState &m, byte stepPin, byte dirPin, int idx) {
    if(!m.enabled || m.stepInterval == 0) return;

    if(m.currentDirection != m.direction) {
        setMotorDirection(dirPin, m.direction);
        m.currentDirection = m.direction;
    }

    unsigned long now = micros();

    if(m.stepState) {
        if(now - m.lastStepTime >= m.highTime) {
            digitalWrite(stepPin, LOW);
            m.stepState = false;
            m.lastStepTime = now;
        }
    } else {
        if(now - m.lastStepTime >= m.lowTime) {
            digitalWrite(stepPin, HIGH);
            m.stepState = true;
            m.lastStepTime = now;
            
            m.executedSteps++;
            if (m.direction) {
                m.signedSteps++;
            } else {
                m.signedSteps--;
            }
            m.stepsRemaining--;

            if(!m.isContinuous && m.stepsRemaining <= 0) {
                m.enabled = false;
                m.stepInterval = 0;
                m.justFinished = true;
            }
        }
    }
}

// ============== 二进制数据包发�?==============
void sendPIDDataPacket(int motorIndex, float currentAngle, float error, float pidOutput) {
    MotorState* m = &motors[motorIndex];
    PIDDataPacket packet;
    
    packet.head1 = 0x55;
    packet.head2 = 0xAA;
    packet.motor_id = motorIndex;
    packet.timestamp = micros();
    packet.target_angle = m->pidTargetAngle;
    packet.actual_angle = currentAngle;
    
    long signedDelta = m->signedSteps - m->pidStartSignedSteps;
    float degreeDelta = (float)signedDelta / STEP_PER_DEGREE;
    float theoAngle = m->pidInitialAngle + degreeDelta;
    while (theoAngle < 0) theoAngle += 360.0f;
    while (theoAngle >= 360) theoAngle -= 360.0f;
    packet.theo_angle = theoAngle;
    
    packet.pid_out = fabs(pidOutput);
    packet.error = error;
    
    uint8_t* data = (uint8_t*)&packet.motor_id;
    packet.checksum = 0;
    for (int i = 0; i < 25; i++) {
        packet.checksum ^= data[i];
    }
    packet.tail = 0x0A;
    
    Serial.write((uint8_t*)&packet, sizeof(packet));
}

void parseCommand(String cmd) {
    int motorIndex = -1;
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};

    for(int i=0; i<cmd.length(); i++){
        char c = cmd[i];
        
        if(c >= 'X' && c <= 'Z') motorIndex = c - 'X';
        else if(c == 'A') motorIndex = 3;
        else continue;
        
        if(i+2 >= cmd.length()) break;
        
        MotorState* m = &motors[motorIndex];
        bool oldEnabled = m->enabled;
        bool oldDirection = m->direction;
        
        m->enabled = (cmd[++i] == 'E');
        m->direction = (cmd[++i] == 'F');
        
        if((oldEnabled != m->enabled) || (oldDirection != m->direction)) {
            if(m->enabled) {
                setMotorDirection(motorPins[motorIndex][1], m->direction);
                m->currentDirection = m->direction;
            }
        }
        
        int searchStart = i;
        int vIndex = cmd.indexOf('V', searchStart);
        int jIndex = cmd.indexOf('J', searchStart);
        int rIndex = cmd.indexOf('R', searchStart);  // R 指令替代�?T 指令
        
        float cmdRpm = 5.0f;
        if(vIndex != -1 && vIndex < cmd.length()) {
            int endIndex = cmd.length();
            if(jIndex > vIndex) endIndex = jIndex;
            if(rIndex > vIndex && rIndex < endIndex) endIndex = rIndex;
            cmdRpm = cmd.substring(vIndex+1, endIndex).toFloat();
            if (cmdRpm <= 0) cmdRpm = 5.0f;
        }
        
        // ============== R 指令：相对增量闭�?PID ==============
        // 格式: <Motor>E<Dir>R<Delta>P<Precision>
        // �? XEFR360P0.1  X电机正转360°，精�?.1°
        if(rIndex != -1 && rIndex >= searchStart){
            int pIndex = cmd.indexOf('P', rIndex);
            float delta;  // 相对增量�?=0�?
            float precision = 0.1f;  // 默认精度
            
            if(pIndex != -1 && pIndex > rIndex) {
                delta = cmd.substring(rIndex+1, pIndex).toFloat();
                int nextMotor = cmd.length();
                for(int k = pIndex+1; k < cmd.length(); k++) {
                    char nc = cmd[k];
                    if(nc == 'X' || nc == 'Y' || nc == 'Z' || nc == 'A') { nextMotor = k; break; }
                }
                precision = cmd.substring(pIndex+1, nextMotor).toFloat();
                if(precision <= 0 || precision > 10) precision = 0.1f;
                i = pIndex;
            } else {
                int nextMotor = cmd.length();
                for(int k = rIndex+1; k < cmd.length(); k++) {
                    char nc = cmd[k];
                    if(nc == 'X' || nc == 'Y' || nc == 'Z' || nc == 'A') { nextMotor = k; break; }
                }
                delta = cmd.substring(rIndex+1, nextMotor).toFloat();
                i = rIndex;
            }
            
            // delta 必须 >= 0，方向由 F/B 决定
            if (delta < 0) delta = fabs(delta);
            
            // 读取当前传感器角�?
            float rawAngle = readAngleWithRetry(g_angleChannels[motorIndex]);
            if (rawAngle < 0) rawAngle = 0;
            
            // 初始化或更新解环角度
            if (!m->absAngleValid) {
                m->absAngle = 0.0f;
                m->lastRawAngle = rawAngle;
                m->absAngleValid = true;
            } else {
                m->absAngle = unwrapAngle(rawAngle, m->lastRawAngle, m->absAngle);
                m->lastRawAngle = rawAngle;
            }
            
            // 溢出保护：当累积角度过大时重�?
            if (fabs(m->absAngle) > 1e6f) {
                m->absAngle = 0.0f;
            }
            
            // 根据方向计算绝对目标角度
            // direction: true=正转(F), false=反转(B)
            int sign = m->direction ? +1 : -1;
            m->absTargetAngle = m->absAngle + sign * delta;
            
            // 存储环形目标用于显示
            float displayTarget = fmod(m->absTargetAngle, 360.0f);
            if (displayTarget < 0) displayTarget += 360.0f;
            m->pidTargetAngle = displayTarget;
            
            m->pidInitialAngle = rawAngle;
            m->pidStartSteps = m->executedSteps;
            m->pidStartSignedSteps = m->signedSteps;
            m->lastPacketTime = 0;
            m->lastOutputRPM = 0;
            
            m->isPIDMode = true;
            m->pidPrecision = precision;
            m->pidStableCount = 0;
            m->pidSensorErrCount = 0;
            m->pidStartTime = millis();
            
            // 使用全局可配置的PID参数
            m->pidCtrl.Kp = g_pidKp;
            m->pidCtrl.Ki = g_pidKi;
            m->pidCtrl.Kd = g_pidKd;
            m->pidCtrl.outputMin = g_pidOutputMin;
            m->pidCtrl.outputMax = g_pidOutputMax;
            m->pidCtrl.deadband = precision;
            m->pidCtrl.reset();
            
            m->enabled = false;
            m->stepInterval = 0;
            m->isContinuous = false;
            
            Serial.printf("PID_START:%c,delta=%.1f,dir=%c,prec=%.2f,absTarget=%.1f\n", 
                motorNames[motorIndex], delta, m->direction ? 'F' : 'B', precision, m->absTargetAngle);
            continue;
        }
        
        // 传统开环模�? J 指令
        if(jIndex != -1 && jIndex >= searchStart){
            m->isPIDMode = false;
            
            m->rpm = cmdRpm;
            m->stepInterval = rpmToInterval(m->rpm);
            updateDutyCycleTiming(*m);
            
            String jVal = cmd.substring(jIndex+1);
            int nextMotor = jVal.length();
            for(int k = 0; k < jVal.length(); k++) {
                char nc = jVal[k];
                if(nc == 'X' || nc == 'Y' || nc == 'Z' || nc == 'A') { nextMotor = k; break; }
            }
            jVal = jVal.substring(0, nextMotor);
            
            if(jVal.startsWith("G")) {
                m->isContinuous = true;
                m->executedSteps = 0;
            } else {
                m->isContinuous = false;
                float degrees = jVal.toFloat();
                m->targetSteps = abs(degrees * STEP_PER_DEGREE);
                m->stepsRemaining = m->targetSteps;
                m->executedSteps = 0;
            }
            
            i = jIndex;
        }
    }
}


// ============== PID 核心算法 ==============
float normalizeAngleError(float target, float current) {
    float error = target - current;
    if (error > 180.0f) error -= 360.0f;
    else if (error < -180.0f) error += 360.0f;
    return error;
}

// 解环算法：将传感�?0~360° 读数转换为连续累积角�?
float unwrapAngle(float newRaw, float lastRaw, float currentAbs) {
    float delta = newRaw - lastRaw;
    // 检�?0/360° 跨越
    if (delta > 180.0f) delta -= 360.0f;
    else if (delta < -180.0f) delta += 360.0f;
    return currentAbs + delta;
}

// 直接误差 PID 计算（用于多圈控制，不使�?normalizeAngleError�?
float computePIDDirect(PIDController &pid, float error, MotorState &motor) {
    if (fabs(error) < pid.deadband) {
        pid.integral = 0;
        motor.lastOutputRPM = 0;
        return 0;
    }
    
    unsigned long now = millis();
    float dt = (pid.lastTime > 0) ? (now - pid.lastTime) / 1000.0f : 0.02f;
    pid.lastTime = now;
    
    if (dt < 0.001f) dt = 0.001f;
    if (dt > 0.5f) dt = 0.5f;
    
    // 条件积分
    if (fabs(error) < PID_INTEGRAL_ZONE) {
        pid.integral += error * dt;
        if (pid.integral > PID_INTEGRAL_LIMIT) pid.integral = PID_INTEGRAL_LIMIT;
        if (pid.integral < -PID_INTEGRAL_LIMIT) pid.integral = -PID_INTEGRAL_LIMIT;
    } else {
        pid.integral *= 0.9f;
    }
    
    float derivative = (dt > 0) ? (error - pid.lastError) / dt : 0;
    pid.lastError = error;
    
    float output = pid.Kp * error + pid.Ki * pid.integral + pid.Kd * derivative;
    
    // 限幅
    if (output > pid.outputMax) output = pid.outputMax;
    if (output < -pid.outputMax) output = -pid.outputMax;
    
    if (output > 0 && output < pid.outputMin) output = pid.outputMin;
    if (output < 0 && output > -pid.outputMin) output = -pid.outputMin;
    
    return output;
}

float computePID(PIDController &pid, float currentAngle, float targetAngle) {
    float error = normalizeAngleError(targetAngle, currentAngle);
    
    if (fabs(error) < pid.deadband) {
        pid.integral = 0;
        return 0;
    }
    
    unsigned long now = millis();
    float dt = (pid.lastTime > 0) ? (now - pid.lastTime) / 1000.0f : 0.02f;
    pid.lastTime = now;
    
    if (dt < 0.001f) dt = 0.001f;
    if (dt > 0.5f) dt = 0.5f;
    
    // 条件积分
    if (fabs(error) < PID_INTEGRAL_ZONE) {
        pid.integral += error * dt;
        if (pid.integral > PID_INTEGRAL_LIMIT) pid.integral = PID_INTEGRAL_LIMIT;
        if (pid.integral < -PID_INTEGRAL_LIMIT) pid.integral = -PID_INTEGRAL_LIMIT;
    } else {
        pid.integral *= 0.9f;
    }
    
    float derivative = (dt > 0) ? (error - pid.lastError) / dt : 0;
    pid.lastError = error;
    
    float output = pid.Kp * error + pid.Ki * pid.integral + pid.Kd * derivative;
    
    // 阻尼区间
    if (fabs(error) < PID_DAMPING_ZONE) {
        float dampingFactor = 0.5f + 0.5f * (fabs(error) / PID_DAMPING_ZONE);
        output *= dampingFactor;
    }
    
    if (output > pid.outputMax) output = pid.outputMax;
    if (output < -pid.outputMax) output = -pid.outputMax;
    
    if (output > 0 && output < pid.outputMin) output = pid.outputMin;
    if (output < 0 && output > -pid.outputMin) output = -pid.outputMin;
    
    return output;
}

// ============== 平滑度优先的PID控制 ==============
// 基于距离的梯形速度曲线：加�?�?匀�?�?减�?
float computePIDWithSmoothing(PIDController &pid, float currentAngle, float targetAngle, MotorState &motor) {
    float error = normalizeAngleError(targetAngle, currentAngle);
    float absError = fabs(error);
    
    // 到达目标，停�?
    if (absError < pid.deadband) {
        pid.integral = 0;
        motor.lastOutputRPM = 0;
        pid.lastAcceleration = 0;
        return 0;
    }
    
    unsigned long now = millis();
    float dt = (pid.lastTime > 0) ? (now - pid.lastTime) / 1000.0f : 0.02f;
    pid.lastTime = now;
    
    if (dt < 0.001f) dt = 0.001f;
    if (dt > 0.5f) dt = 0.5f;
    
    // ===== 基于距离的速度规划 =====
    float currentRPM = fabs(motor.lastOutputRPM);
    float maxSpeed = pid.outputMax;
    float minSpeed = pid.outputMin;
    
    // 减速距离计算：假设减速率�?decelRate RPM/�?
    // 当前速度需要多少距离才能减到最小速度
    float decelRate = 1.5f;  // RPM/度，可调参数
    float brakeDistance = (currentRPM - minSpeed) / decelRate;
    if (brakeDistance < 0.5f) brakeDistance = 0.5f;
    
    // 目标速度计算
    float targetRPM;
    
    if (absError <= brakeDistance) {
        // 减速区：线性减速到最小速度
        // 速度 = minSpeed + (maxSpeed - minSpeed) * (error / brakeDistance)
        float speedRatio = absError / brakeDistance;
        targetRPM = minSpeed + (currentRPM - minSpeed) * speedRatio;
        
        // 确保平滑减速，不要突然降�?
        float maxDecel = decelRate * absError * dt * 50;  // 允许的最大减速量
        if (currentRPM - targetRPM > maxDecel) {
            targetRPM = currentRPM - maxDecel;
        }
    } else {
        // 加�?匀速区：使用增强PID计算目标速度
        
        // ===== 增益调度：根据误差大小动态调整增�?=====
        float effectiveKp = pid.Kp;
        float effectiveKd = pid.Kd;
        
        if (absError > 180.0f) {
            // 大误�? 激进模�?- 更快响应
            effectiveKp *= 1.2f;
            effectiveKd *= 0.8f;
        } else if (absError < 5.0f) {
            // 小误�? 保守模式 - 更稳�?
            effectiveKp *= 0.7f;
            effectiveKd *= 1.5f;
        }
        
        // 条件积分
        if (absError < PID_INTEGRAL_ZONE) {
            pid.integral += error * dt;
            pid.integral = constrain(pid.integral, -PID_INTEGRAL_LIMIT, PID_INTEGRAL_LIMIT);
        } else {
            pid.integral *= 0.95f;
        }
        
        float derivative = (dt > 0) ? (error - pid.lastError) / dt : 0;
        pid.lastError = error;
        
        // 计算原始PID输出
        float rawOutput = effectiveKp * error + pid.Ki * pid.integral + effectiveKd * derivative;
        
        // ===== 前馈控制：启动阶段基于目标距离预估速度 =====
        float feedforward = 0;
        unsigned long elapsed = now - motor.pidStartTime;
        if (elapsed < 500 && motor.pidStartTime > 0) {
            float angleToMove = fabs(normalizeAngleError(targetAngle, motor.pidInitialAngle));
            // 预估所需速度：角�?/ 期望完成时间(�? * 比例系数
            float expectedSpeed = angleToMove / 2.0f;  // 假设2秒内完成
            feedforward = constrain(expectedSpeed, 0, maxSpeed * 0.4f);
        }
        
        float totalOutput = rawOutput + feedforward;
        
        // ===== Back-calculation 积分抗饱�?=====
        float clampedOutput = constrain(totalOutput, -maxSpeed, maxSpeed);
        if (totalOutput != clampedOutput) {
            // 输出饱和时，回算并减少积分项
            float Kb = 0.5f;  // 回算增益
            pid.integral -= Kb * (totalOutput - clampedOutput) * dt;
        }
        
        targetRPM = fabs(clampedOutput);
        targetRPM = constrain(targetRPM, minSpeed, maxSpeed);
    }
    
    // ===== 启动阶段平滑 =====
    unsigned long runTime = now - motor.pidStartTime;
    if (runTime < PID_SMOOTH_RAMP_TIME) {
        float rampProgress = (float)runTime / PID_SMOOTH_RAMP_TIME;
        // S曲线
        float smoothFactor = rampProgress * rampProgress * (3.0f - 2.0f * rampProgress);
        float startSpeed = minSpeed + (maxSpeed - minSpeed) * 0.3f;  // 起始30%速度
        targetRPM = startSpeed + (targetRPM - startSpeed) * smoothFactor;
    }
    
    // ===== 速度变化率限�?=====
    float maxAccel = PID_RAMP_RATE * dt * 50;  // 最大加�?
    float maxDecel = PID_RAMP_RATE * dt * 80;  // 最大减速（允许更快减速）
    
    if (targetRPM > currentRPM + maxAccel) {
        targetRPM = currentRPM + maxAccel;
    } else if (targetRPM < currentRPM - maxDecel) {
        targetRPM = currentRPM - maxDecel;
    }
    
    // 确保在有效范围内
    if (targetRPM > 0 && targetRPM < minSpeed) {
        targetRPM = minSpeed;
    }
    targetRPM = constrain(targetRPM, 0, maxSpeed);
    
    // 记录加速度
    pid.lastAcceleration = (targetRPM - currentRPM) / dt;
    
    return (error > 0) ? targetRPM : -targetRPM;
}

// ============== 校准相关函数 ==============
void initCalibration(uint8_t motorMask) {
    calCtx.state = CAL_RUNNING;
    calCtx.motorMask = motorMask;
    calCtx.startTime = millis();
    
    for (int i = 0; i < 4; i++) {
        calCtx.targetAngle[i] = 0.0f;
        calCtx.stableCount[i] = 0;
        calCtx.sensorErrorCount[i] = 0;
        calCtx.motorDone[i] = !(motorMask & (1 << i));
        
        calCtx.pid[i].Kp = g_pidKp;
        calCtx.pid[i].Ki = g_pidKi;
        calCtx.pid[i].Kd = g_pidKd;
        calCtx.pid[i].outputMin = g_pidOutputMin;
        calCtx.pid[i].outputMax = g_pidOutputMax;
        calCtx.pid[i].deadband = PID_DEADBAND;
        calCtx.pid[i].reset();
        
        if (motorMask & (1 << i)) {
            motors[i].enabled = false;
            motors[i].stepInterval = 0;
        }
    }
    
    Serial.printf("CAL_START:mask=0x%X\n", motorMask);
}

void stopCalibration() {
    for (int i = 0; i < 4; i++) {
        if (calCtx.motorMask & (1 << i)) {
            motors[i].enabled = false;
            motors[i].stepInterval = 0;
            motors[i].isContinuous = false;
        }
    }
    calCtx.state = CAL_IDLE;
    calCtx.motorMask = 0;
    Serial.println("CAL_STOPPED");
}

void sendCalibrationStatus() {
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    String status = "CAL_STATUS:";
    
    for (int i = 0; i < 4; i++) {
        if (calCtx.motorMask & (1 << i)) {
            float angle = readAngleWithRetry(g_angleChannels[i]);
            float error = normalizeAngleError(calCtx.targetAngle[i], angle);
            status += String(motorNames[i]) + "=" + String(error, 2);
            status += calCtx.motorDone[i] ? "(OK)" : "";
            status += " ";
        }
    }
    Serial.println(status);
}

void runCalibrationPID() {
    if (calCtx.state != CAL_RUNNING) return;
    
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    bool allDone = true;
    unsigned long now = millis();
    
    if (now - calCtx.startTime > CAL_TIMEOUT) {
        Serial.print("CAL_FAIL:TIMEOUT,done=");
        for (int i = 0; i < 4; i++) {
            if (calCtx.motorMask & (1 << i)) {
                Serial.print(motorNames[i]);
                Serial.print(calCtx.motorDone[i] ? "1" : "0");
            }
        }
        Serial.println();
        stopCalibration();
        calCtx.state = CAL_TIMEOUT_ERR;
        return;
    }
    
    for (int i = 0; i < 4; i++) {
        if (!(calCtx.motorMask & (1 << i)) || calCtx.motorDone[i]) continue;
        
        allDone = false;
        float currentAngle = readAngleWithRetry(g_angleChannels[i]);
        
        if (currentAngle < 0 || currentAngle > 360) {
            calCtx.sensorErrorCount[i]++;
            if (calCtx.sensorErrorCount[i] > 10) {
                Serial.printf("CAL_FAIL:%c=SENSOR_ERR\n", motorNames[i]);
                calCtx.motorDone[i] = true;
                motors[i].enabled = false;
                motors[i].stepInterval = 0;
            }
            continue;
        }
        calCtx.sensorErrorCount[i] = 0;
        
        float pidOutput = computePID(calCtx.pid[i], currentAngle, calCtx.targetAngle[i]);
        float error = normalizeAngleError(calCtx.targetAngle[i], currentAngle);
        
        if (fabs(error) < PID_DEADBAND) {
            calCtx.stableCount[i]++;
            motors[i].enabled = false;
            motors[i].stepInterval = 0;
            
            if (calCtx.stableCount[i] >= CAL_STABLE_COUNT) {
                calCtx.motorDone[i] = true;
                Serial.printf("CAL_DONE:%c=%.2f\n", motorNames[i], currentAngle);
            }
        } else {
            calCtx.stableCount[i] = 0;
            
            if (xSemaphoreTake(motorMutex, 10) == pdTRUE) {
                motors[i].direction = (pidOutput > 0);
                float rpm = fabs(pidOutput);
                motors[i].rpm = rpm;
                motors[i].stepInterval = rpmToInterval(rpm);
                updateDutyCycleTiming(motors[i]);
                motors[i].isContinuous = true;
                motors[i].enabled = true;
                xSemaphoreGive(motorMutex);
            }
        }
    }
    
    if (allDone) {
        calCtx.state = CAL_SUCCESS;
        Serial.println("CAL_COMPLETE:ALL_DONE");
        stopCalibration();
    }
}


// ============== PID 定位模式实现 ==============
void initPIDMove(int motorIndex, float targetAngle, float precision) {
    if (motorIndex < 0 || motorIndex > 3) return;
    
    MotorState* m = &motors[motorIndex];
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    
    m->enabled = false;
    m->stepInterval = 0;
    m->isContinuous = false;
    
    float initAngle = readAngleWithRetry(g_angleChannels[motorIndex]);
    if (initAngle < 0) initAngle = 0;
    m->pidInitialAngle = initAngle;
    m->pidStartSteps = m->executedSteps;
    m->pidStartSignedSteps = m->signedSteps;
    m->lastPacketTime = 0;
    m->lastOutputRPM = 0;
    
    // 初始化解环角度（用于显示和内部跟踪）
    if (!m->absAngleValid) {
        m->absAngle = 0.0f;
        m->lastRawAngle = initAngle;
        m->absAngleValid = true;
    } else {
        m->absAngle = unwrapAngle(initAngle, m->lastRawAngle, m->absAngle);
        m->lastRawAngle = initAngle;
    }
    
    // 计算绝对目标：targetAngle 是环形目标，计算最短路径的绝对目标
    float shortestDelta = targetAngle - fmod(fabs(m->absAngle), 360.0f);
    if (m->absAngle < 0) {
        float wrappedCurrent = 360.0f - fmod(fabs(m->absAngle), 360.0f);
        if (wrappedCurrent >= 360.0f) wrappedCurrent = 0.0f;
        shortestDelta = targetAngle - wrappedCurrent;
    }
    if (shortestDelta > 180.0f) shortestDelta -= 360.0f;
    else if (shortestDelta < -180.0f) shortestDelta += 360.0f;
    m->absTargetAngle = m->absAngle + shortestDelta;
    
    m->isPIDMode = true;
    m->pidTargetAngle = targetAngle;  // 环形目标用于显示
    m->pidPrecision = precision;
    m->pidStableCount = 0;
    m->pidSensorErrCount = 0;
    m->pidStartTime = millis();
    
    // 使用全局可配置的PID参数
    m->pidCtrl.Kp = g_pidKp;
    m->pidCtrl.Ki = g_pidKi;
    m->pidCtrl.Kd = g_pidKd;
    m->pidCtrl.outputMin = g_pidOutputMin;
    m->pidCtrl.outputMax = g_pidOutputMax;
    m->pidCtrl.deadband = precision;
    m->pidCtrl.reset();
    
    Serial.printf("PID_START:%c,delta=%.1f,dir=F,prec=%.2f,absTarget=%.1f\n", 
        motorNames[motorIndex], fabs(shortestDelta), precision, m->absTargetAngle);
}

void stopPIDMove(int motorIndex) {
    if (motorIndex < 0 || motorIndex > 3) return;
    MotorState* m = &motors[motorIndex];
    m->isPIDMode = false;
    m->enabled = false;
    m->stepInterval = 0;
    m->isContinuous = false;
}

void stopAllPIDMoves() {
    for (int i = 0; i < 4; i++) stopPIDMove(i);
    Serial.println("PID_STOP:ALL");
}

void runMotorPID() {
    const char motorNames[] = {'X', 'Y', 'Z', 'A'};
    unsigned long now = millis();
    
    bool anyPIDActive = false;
    for (int i = 0; i < 4; i++) {
        if (motors[i].isPIDMode) { anyPIDActive = true; break; }
    }
    if (!anyPIDActive) return;
    
    for (int i = 0; i < 4; i++) {
        MotorState* m = &motors[i];
        if (!m->isPIDMode) continue;
        
        // 读取当前传感器角�?
        float rawAngle = readAngleWithRetry(g_angleChannels[i]);
        
        // 传感器错误检�?
        if (rawAngle < 0 || rawAngle > 360) {
            m->pidSensorErrCount++;
            if (m->pidSensorErrCount > 10) {
                Serial.printf("PID_FAIL:%c=SENSOR_ERR\n", motorNames[i]);
                if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                    m->isPIDMode = false;
                    m->enabled = false;
                    m->stepInterval = 0;
                    xSemaphoreGive(motorMutex);
                }
            }
            continue;
        }
        m->pidSensorErrCount = 0;
        
        // ===== 解环角度更新 =====
        m->absAngle = unwrapAngle(rawAngle, m->lastRawAngle, m->absAngle);
        m->lastRawAngle = rawAngle;
        
        // ===== 使用绝对角度计算误差（支持多圈）=====
        float error = m->absTargetAngle - m->absAngle;
        
        // 用于 UI 显示的环形角�?
        float displayAngle = fmod(m->absAngle, 360.0f);
        if (displayAngle < 0) displayAngle += 360.0f;
        
        // 超时检�?
        if (now - m->pidStartTime > PID_MOVE_TIMEOUT) {
            sendPIDDataPacket(i, displayAngle, error, 0);
            Serial.printf("PID_TIMEOUT:%c,abs=%.2f,err=%.2f\n", motorNames[i], m->absAngle, error);
            if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                m->isPIDMode = false;
                m->enabled = false;
                m->stepInterval = 0;
                m->isContinuous = false;
                xSemaphoreGive(motorMutex);
            }
            continue;
        }
        
        // 过冲检�?
        static float lastError[4] = {0, 0, 0, 0};
        bool overshootDetected = false;
        if (lastError[i] != 0) {
            if ((lastError[i] > 0.5f && error < -0.1f) || (lastError[i] < -0.5f && error > 0.1f)) {
                overshootDetected = true;
                m->pidStableCount = 0;
            }
        }
        lastError[i] = error;
        
        // 完成判定：基于绝对误�?
        if (fabs(error) < m->pidPrecision && !overshootDetected) {
            m->pidStableCount++;
            
            if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                m->enabled = false;
                m->stepInterval = 0;
                xSemaphoreGive(motorMutex);
            }
            
            if (now - m->lastPacketTime >= PID_PACKET_INTERVAL) {
                sendPIDDataPacket(i, displayAngle, error, 0);
                m->lastPacketTime = now;
            }
            
            if (m->pidStableCount >= PID_MOVE_STABLE_COUNT) {
                sendPIDDataPacket(i, displayAngle, error, 0);
                Serial.printf("PID_DONE:%c,abs=%.2f,err=%.2f\n", motorNames[i], m->absAngle, error);
                m->isPIDMode = false;
                lastError[i] = 0;
            }
        } else {
            m->pidStableCount = 0;
            
            // ===== 直接误差 PID 计算（不使用 normalize�?====
            float pidOutput = computePIDDirect(m->pidCtrl, error, *m);
            
            if (now - m->lastPacketTime >= PID_PACKET_INTERVAL) {
                sendPIDDataPacket(i, displayAngle, error, pidOutput);
                m->lastPacketTime = now;
            }
            
            if (xSemaphoreTake(motorMutex, portMAX_DELAY) == pdTRUE) {
                m->direction = (pidOutput > 0);
                
                float targetRPM = fabs(pidOutput);
                if (targetRPM < g_pidOutputMin) targetRPM = g_pidOutputMin;
                if (targetRPM > g_pidOutputMax) targetRPM = g_pidOutputMax;
                
                m->lastOutputRPM = targetRPM;
                m->rpm = targetRPM;
                m->stepInterval = rpmToInterval(targetRPM);
                updateDutyCycleTiming(*m);
                
                m->isContinuous = true;
                m->enabled = true;
                
                setMotorDirection(motorPins[i][1], m->direction);
                m->currentDirection = m->direction;
                
                xSemaphoreGive(motorMutex);
            }
        }
    }
}
