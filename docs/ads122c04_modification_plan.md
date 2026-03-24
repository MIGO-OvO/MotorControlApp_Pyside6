# ADS122C04 分光信号采集改造方案

更新时间：2026-03-24

## 1. 目标

本次改造的目标不是在上位机继续直连采集硬件，而是把分光信号采集统一并入当前主控板 `lowerDevice`，形成如下链路：

- MT6701 角度采集：主控板 -> TCA9548A -> 各泵组编码器
- 分光信号采集：主控板 -> TCA9548A 指定通道 -> ADS122C04 -> 光电传感器
- 上位机：只通过串口与主控板通信，不再依赖 NI DAQ

同时新增一套可配置的 I2C 通道映射，使用户可以在上位机中自定义：

- 四个泵组角度数据分别从 TCA9548A 的哪一路读取
- 分光信号从 TCA9548A 的哪一路读取

## 2. 当前程序现状

结合当前仓库代码，现状如下：

- 上位机分光页完全依赖 `nidaqmx`
  - `src/hardware/daq_thread.py`
  - `src/ui/mixins/spectro_mixin.py`
  - `src/ui/main_window_complete.py`
  - `src/ui/mixins/settings_mixin.py`
  - `requirements.txt`
- 下位机只支持 MT6701 角度读取与串口运动控制，不支持 ADS122C04
  - `lowerDevice/src/main.cpp` 中 `angleChannels[4] = {0, 3, 4, 7}`
  - `sendAnglePacket()` 也直接写死为 `0/3/4/7`
- 串口二进制协议目前只有三类包
  - `0xAA` PID 数据包
  - `0xBB` PID 测试结果包
  - `0xCC` 角度数据包
- 上位机串口连接后会立即启动 `ANGLESTREAM_START`，当前没有“先同步硬件配置、再启动采集”的流程

结论：这次修改不是单点替换，而是“采集架构迁移”。上位机、下位机、串口协议、设置持久化都要同步改。

## 3. ADS122C04 手册中与本项目直接相关的约束

以下约束来自 `docs/TI-ADS122C04.pdf`，是本方案的设计依据：

- I2C 接口
  - ADS122C04 是 I2C 从设备，A0/A1 可组合出 16 个 7-bit 地址，接口速率支持到 1 Mbps，不做 clock stretching（手册 8.5.1.1 到 8.5.1.4，约第 35 到 36 页）。
- 指令与寄存器
  - 芯片通过 6 条命令控制：`RESET`、`START/SYNC`、`POWERDOWN`、`RDATA`、`RREG`、`WREG`
  - 仅有 4 个配置寄存器：`CONFIG0` 到 `CONFIG3`（约第 38 到 45 页）。
- 转换模式
  - 支持 `single-shot` 和 `continuous` 两种模式
  - 改变转换模式后需要重新发 `START/SYNC`
  - 数字滤波器为单周期稳定，配置切换后第一笔完成转换即可视为有效结果（约第 21、32、33 页）。
- 采样率不是任意值
  - Normal mode：`20 / 45 / 90 / 175 / 330 / 600 / 1000 SPS`
  - Turbo mode：`40 / 90 / 180 / 350 / 660 / 1200 / 2000 SPS`
  - 因此上位机现有“任意 Hz 数值输入”的方式不再合适（约第 28、43 页）。
- 单端电压采集限制
  - 如果测量的是 `AINx` 对 `AVSS` 的单端信号，必须使用 `MUX=AINx/AVSS`
  - 在单电源单端测量下，必须旁路 PGA，即 `PGA_BYPASS=1`
  - 此时增益只能使用 `1 / 2 / 4`（约第 42、49、50 页）。
- 数据格式
  - 转换结果为 24-bit 二补码
  - 可按 `voltage = raw_code / 8388608.0 * (VREF / Gain)` 转成输入电压（约第 37 页）。

对本项目最关键的含义是：

- 如果光电传感器输出是单端正电压，固件默认应按“单端测量 + PGA 旁路”设计
- 如果传感器电压可能高于 2.048 V，就不能固定使用内部 2.048 V 参考，必须改用 `AVDD` 参考或外部参考
- 上位机不应该再使用任意采样率 SpinBox 直接表达 ADS 采样率，而应改为离散档位

## 4. 推荐的总体架构

### 4.1 总体原则

- 角度与分光信号都由下位机统一采集
- 上位机只负责配置、显示、数据处理和保存
- I2C 通道映射是“全局硬件配置”，不是自动化步骤参数
- 上位机设置文件作为主配置源，串口连接成功后主动下发给下位机
- 下位机保留默认映射，保证未配置时仍可兼容现有硬件

### 4.2 推荐的配置模型

建议把配置统一收敛为两组：

```json
{
  "i2c_mapping": {
    "angles": {
      "X": 0,
      "Y": 3,
      "Z": 4,
      "A": 7
    },
    "spectro_channel": 2
  },
  "spectrometer": {
    "ads_address": "0x40",
    "ain": "AIN0",
    "vref": "AVDD",
    "gain": 1,
    "pga_bypass": true,
    "mode": "continuous",
    "adc_rate": 90,
    "publish_rate": 50
  }
}
```

说明：

- `angles` 是四个泵组角度源的 TCA 通道
- `spectro_channel` 是 ADS122C04 所在的 TCA 通道
- `ain` 只有在 PCB 实际引出了多个 ADS 输入时才需要暴露给用户；如果硬件只接了 `AIN0`，这一项可以在固件内固定
- `adc_rate` 是 ADS 实际转换速率
- `publish_rate` 是下位机通过串口上传到上位机的频率，建议与 ADC 速率分离

## 5. 下位机固件修改方案

### 5.1 目标

下位机需要新增三类能力：

- I2C 通道映射可配置
- ADS122C04 驱动与采样状态机
- 分光数据串口协议

### 5.2 建议先做的结构拆分

当前 `lowerDevice/src/main.cpp` 已经较大，建议这次不要继续把 ADS 逻辑堆在一个文件里。推荐至少拆出：

- `lowerDevice/src/i2c_mux.h/.cpp`
- `lowerDevice/src/ads122c04.h/.cpp`
- `lowerDevice/src/protocol_packets.h`

如果本轮不想拆文件，至少也要在 `main.cpp` 内部做清晰分区，并把“角度采集”和“ADS 采集”封装成独立函数。

### 5.3 I2C 访问层

新增统一的 TCA 通道选择函数，例如：

- `bool selectTcaChannel(uint8_t channel)`
- `float readMt6701Angle(uint8_t channel)`
- `bool adsWriteRegister(uint8_t adsAddr, uint8_t reg, uint8_t value)`
- `bool adsReadRegister(uint8_t adsAddr, uint8_t reg, uint8_t* value)`
- `bool adsReadData(uint8_t adsAddr, int32_t* rawCode)`

要点：

- `selectTcaChannel()` 统一做 0 到 7 范围校验
- 可以缓存最近一次选中的通道，减少重复切换
- `readAngleWithRetry()` 改为基于新的 `selectTcaChannel()` 实现

### 5.4 角度通道改为可配置

把当前写死的：

```cpp
const uint8_t angleChannels[4] = {0, 3, 4, 7};
```

改为可变配置，例如：

```cpp
uint8_t g_angleChannels[4] = {0, 3, 4, 7};
uint8_t g_spectroChannel = 2;
```

并修改以下位置：

- `readAngleWithRetry(angleChannels[i])`
- `sendAnglePacket()` 中固定的 `0/3/4/7`
- 所有 PID、校准、实时角度流、单次取角度逻辑

这样 X/Y/Z/A 的角度源就能由上位机同步配置。

### 5.5 ADS122C04 驱动建议

建议以“单端光电电压采集”为默认模式实现，默认配置思路如下：

- 输入模式：`AINx` 对 `AVSS`
- `MUX = AINx / AVSS`
- `PGA_BYPASS = 1`
- `GAIN = 1`
- `MODE = Normal`
- `CM = Continuous`
- `VREF = AVDD` 或 `Internal 2.048V`

其中 `VREF` 的选择要看硬件：

- 若光电电压范围可能到 3.3 V，建议 `VREF = AVDD`
- 若前级电路已限制在 2.048 V 以内，可用内部参考

推荐增加一个固件配置结构：

```cpp
struct ADSConfig {
    uint8_t address;
    uint8_t mux;
    uint8_t gain;
    bool pgaBypass;
    bool turboMode;
    bool continuousMode;
    uint8_t vrefMode;
    uint16_t adcRate;
    uint16_t publishRate;
    bool enabled;
};
```

### 5.6 采样调度建议

不建议新增第二个并发 I2C 任务直接访问 `Wire`，因为当前角度读取、PID 校准和串口处理都在 `TaskComms()` 这一条链路上。更稳妥的做法是：

- 仍由 `TaskComms()` 统一调度角度和 ADS 访问
- 增加 `lastSpectroPollTime`
- 按 `publishRate` 定时读取 ADS 的最新结果并发送串口包

推荐 V1 方案：

- ADS 运行在 continuous mode
- 下位机按固定周期轮询并读取最新结果
- 上位机只接收“最新值流”，不要求 100% 捕获每一个 ADC 内部转换结果

这样做的原因：

- 当前 `TaskComms()` 末尾有 `vTaskDelay(10 / portTICK_PERIOD_MS)`，天然更适合 10 到 100 Hz 的上送节奏
- 当前串口默认波特率是 115200，角度流、PID 包和分光流同时存在时，100 Hz 左右更稳妥

如果后续确实要上传 330 到 1000 SPS 的完整原始波形，再考虑第二阶段：

- 接 DRDY 中断
- 或新增专用采样任务 + 环形缓冲区
- 同时提高串口波特率到 230400 或更高

### 5.7 串口文本命令建议

为了与现有 `PUMP:`、`PIDCFG:` 风格保持一致，建议新增以下命令：

#### I2C 映射

- `I2CMAP?`
  - 查询当前映射
- `I2CMAP:X=0,Y=3,Z=4,A=7,SPEC=2`
  - 设置四路角度通道和分光通道

建议响应：

- `I2CMAP_OK:X=0,Y=3,Z=4,A=7,SPEC=2`
- `I2CMAP_ERR:CHANNEL_RANGE`
- `I2CMAP_ERR:FORMAT`

#### ADS 配置

- `ADSCFG:CH=2,ADDR=0x40,AIN=AIN0,REF=AVDD,GAIN=1,DR=90,MODE=CONT`
- `ADSSTART`
- `ADSSTOP`
- `ADSSTATUS?`

建议响应：

- `ADS_OK:CFG`
- `ADS_OK:START`
- `ADS_OK:STOP`
- `ADS_STATUS:RUNNING,CH=2,ADDR=0x40,AIN=AIN0,REF=AVDD,GAIN=1,DR=90`
- `ADS_ERR:I2C`
- `ADS_ERR:CONFIG`
- `ADS_ERR:TIMEOUT`

### 5.8 新增二进制数据包

建议新增 `0xDD` 分光采样包，保持与现有 `0xAA/0xBB/0xCC` 风格一致。

推荐结构：

```cpp
#pragma pack(push, 1)
typedef struct {
    uint8_t  head1;        // 0x55
    uint8_t  head2;        // 0xDD
    uint32_t timestamp_ms;
    uint8_t  tca_channel;
    uint8_t  status;
    int32_t  raw_code;
    float    voltage;
    uint8_t  checksum;
    uint8_t  tail;         // 0x0A
} SpectroDataPacket;
#pragma pack(pop)
```

建议 `status` 位定义：

- bit0: 新数据有效
- bit1: I2C 访问失败
- bit2: 配置未完成
- bit3: 数据饱和或越界

建议继续使用现有 XOR 校验方式，便于上位机复用解析逻辑。

### 5.9 电压换算与异常处理

固件内建议保留：

- `raw_code`
- `voltage`

电压换算建议按统一函数完成：

```cpp
float codeToVoltage(int32_t rawCode, float vref, float gain);
```

注意点：

- 二补码必须先正确符号扩展到 32-bit
- 单端测量在接近 0 V 时仍可能出现轻微负码，建议保留原始值用于诊断
- 若结果超量程，不建议静默改为 0，应通过 `status` 或文本错误明确反馈

### 5.10 断电保持

推荐两种策略：

- 主策略：上位机连接后总是下发当前映射与 ADS 配置
- 辅策略：下位机使用 ESP32 `Preferences` 存储最近一次配置，断电后可恢复默认工作状态

这样即使脱离上位机，下位机也能保持最后一次有效配置。

## 6. 上位机修改方案

### 6.1 总体原则

- 删除 NI DAQ 采集卡依赖
- 分光数据改为从串口二进制包接收
- I2C 通道映射由上位机统一管理并持久化
- 参考电压、吸光度计算、图表和 CSV 保存继续放在上位机完成

### 6.2 建议修改的主要文件

| 文件 | 现状 | 建议修改 |
| --- | --- | --- |
| `src/ui/mixins/spectro_mixin.py` | 完全依赖 `nidaqmx` 和 `DAQThread` | 改为串口驱动模式，负责 ADS 配置、开始停止、图表、参考电压、吸光度和保存 |
| `src/hardware/daq_thread.py` | NI 采集线程 | 删除，或替换为轻量的 ADS 采集会话控制类 |
| `src/ui/main_window_complete.py` | 启动时检查 `NIDAQMX_AVAILABLE`，并刷新 NI 设备 | 删除 NI 初始化逻辑，保留分光页入口 |
| `src/ui/mixins/settings_mixin.py` | 仅保存 NI 设备/通道/采样率 | 改为保存 `i2c_mapping` 和 `spectrometer` 配置 |
| `src/hardware/serial_reader.py` | 只解析 `0xAA/0xBB/0xCC` | 新增 `0xDD` 分光包解析和信号 |
| `src/ui/mixins/serial_mixin.py` | 连接串口后立即发送 `ANGLESTREAM_START` | 改为先同步配置，再启动角度流；同时连接分光包信号 |
| `src/ui/mixins/pid_data_mixin.py` 或 `spectro_mixin.py` | 未处理分光包 | 新增 `handle_spectro_packet()` |
| `src/config/constants.py` | 只有通用采样率默认值 | 增加 ADS 支持采样率列表、默认 I2C 映射、默认 ADS 地址 |
| `requirements.txt` | 依赖 `nidaqmx` | 删除 `nidaqmx`，保留 `pyqtgraph` 与 `scipy` |
| `tests/test_basic_modules.py` 等 | 无 ADS 协议测试 | 增加设置序列化、分光包解析、通道配置校验测试 |

### 6.3 光谱页 UI 改造建议

当前页面文案是“光谱仪控制”，但新硬件实际上是“分光/光电信号采集”。建议：

- 对用户可见的文案改为“分光信号”或“光电信号”
- 代码内部第一阶段可以继续沿用 `spectro_` 变量名，减少大面积重构风险

页面控件建议替换为：

- `TCA 通道`：0 到 7
- `ADS 地址`：默认 `0x40`，可编辑或下拉
- `AIN 输入`：若硬件固定只接 `AIN0`，可隐藏
- `参考源`：`AVDD` / `INT_2V048`
- `增益`：`1 / 2 / 4`
- `ADC 数据率`：ADS 支持的离散档位
- `串口上传频率`：10 到 100 Hz
- `开始采集` / `停止采集`
- `设置参考`
- `清除数据`
- `保存数据`

需要移除的旧控件：

- NI 设备下拉框
- NI 通道下拉框
- “刷新设备”按钮

### 6.4 I2C 通道映射 UI 建议

建议在 `Position` 页增加一个新的 `QGroupBox("I2C 通道映射")`，包含：

- `X 角度通道`
- `Y 角度通道`
- `Z 角度通道`
- `A 角度通道`
- `分光通道`
- `读取下位机配置`
- `应用到下位机`

设计理由：

- 角度通道与分光通道都属于“硬件布线映射”
- 放在位置监控页比放在自动化步骤配置里更合理
- 这套映射应是全局配置，不建议按步骤保存

### 6.5 串口连接流程要调整

当前 `SerialMixin.open_serial()` 连接后立即发送：

```text
ANGLESTREAM_START
```

这一逻辑要改成：

1. 打开串口
2. 建立 `SerialReader` 信号连接
3. 查询或直接下发 `I2CMAP` 与 `ADSCFG`
4. 等待下位机确认
5. 再启动 `ANGLESTREAM_START`
6. 若用户之前处于分光采集中，再决定是否自动 `ADSSTART`

这样可以避免角度流先按旧映射启动，导致 UI 显示与真实硬件不一致。

### 6.6 分光数据处理逻辑

保持“采集在下位机，算法在上位机”的分层：

- 下位机负责上报 `raw_code` 和 `voltage`
- 上位机负责：
  - 参考电压记录
  - 吸光度计算
  - 图表绘制
  - 数据保存

吸光度计算保持现有思路，但要补强边界处理：

```text
absorbance = -log10(voltage / reference_voltage)
```

边界建议：

- `reference_voltage <= 0` 时显示 `N/A`
- `voltage <= 0` 时不计算吸光度或按错误状态处理
- 上位机可增加显示滤波，但原始数据必须保留

### 6.7 CSV 保存字段建议

当前保存字段只有：

- `timestamp`
- `voltage`
- `absorbance`

建议扩展为：

- `timestamp`
- `raw_code`
- `voltage`
- `absorbance`
- `spectro_channel`
- `ads_address`
- `vref_mode`
- `gain`
- `adc_rate`
- `X_angle`
- `Y_angle`
- `Z_angle`
- `A_angle`

这样后续做实验回溯、校准和离线分析时信息足够完整。

## 7. 推荐的串口协议扩展

### 7.1 文本命令

建议新增：

- `I2CMAP?`
- `I2CMAP:X=0,Y=3,Z=4,A=7,SPEC=2`
- `ADSCFG:CH=2,ADDR=0x40,AIN=AIN0,REF=AVDD,GAIN=1,DR=90,MODE=CONT`
- `ADSSTART`
- `ADSSTOP`
- `ADSSTATUS?`

### 7.2 二进制包

保留：

- `0xAA` PID 数据
- `0xBB` PID 测试结果
- `0xCC` 角度流

新增：

- `0xDD` 分光数据流

### 7.3 上位机解析器改造点

`src/hardware/serial_reader.py` 需要同步增加：

- `HEADER2_SPECTRO = 0xDD`
- `PACKET_SIZE_SPECTRO`
- `spectro_packet_received = Signal(dict)`
- `_emit_spectro_packet()`

## 8. 推荐默认参数

在未拿到完整硬件原理图前，建议先按以下默认值实施：

### 8.1 角度通道默认值

- `X = 0`
- `Y = 3`
- `Z = 4`
- `A = 7`

保持与当前固件一致，保证兼容。

### 8.2 ADS 默认值

若光电信号是 0 到 3.3 V 单端电压，推荐：

- `MUX = AIN0 / AVSS`
- `PGA_BYPASS = 1`
- `GAIN = 1`
- `VREF = AVDD`
- `MODE = continuous`
- `ADC rate = 90 SPS`
- `publish_rate = 50 Hz`

若光电信号已被前端限制到 2.048 V 以内，可把参考改为内部 2.048 V。

## 9. 风险与待确认项

在正式开发前，建议先确认以下硬件事实，否则程序参数会写错：

- ADS122C04 的 A0/A1 实际接法，最终 I2C 地址是否默认 `0x40`
- 光电传感器输出满量程是否超过 2.048 V
- ADS 实际使用的是 `AIN0` 还是多个 AIN 输入
- ADS 的 `DRDY` 引脚是否有接到主控 GPIO
- 分光通道是否可能与某个 MT6701 共用同一 TCA 通道
- 是否需要下位机脱离上位机后也记住最近一次映射和 ADS 配置

其中最关键的是第二项：

- 若传感器电压可能高于 2.048 V，而程序仍固定内部参考，会直接导致饱和和电压计算错误

## 10. 推荐实施顺序

### 第一阶段：固件侧打基础

1. 把 MT6701 角度通道改成可配置，不再写死 `0/3/4/7`
2. 抽出 TCA 通道选择辅助函数
3. 加入 ADS122C04 寄存器配置和读数函数
4. 增加 `I2CMAP` / `ADSCFG` / `ADSSTART` / `ADSSTOP` 协议
5. 增加 `0xDD` 分光数据包

### 第二阶段：上位机接协议

1. 扩展 `SerialReader` 解析 `0xDD`
2. 修改串口连接流程，先同步配置再启流
3. 替换分光页中的 NI DAQ 控件
4. 增加 `I2C 通道映射` 配置 UI
5. 扩展设置保存与读取

### 第三阶段：数据与体验完善

1. 扩展 CSV 导出字段
2. 增加错误提示和状态栏反馈
3. 增加通道配置校验和重复提示
4. 完成 README 和用户说明更新

## 11. 验收标准

改造完成后，至少应满足以下验收项：

- 无 NI DAQ 和 `nidaqmx` 依赖时，上位机仍能正常打开并使用分光页
- 用户可以在上位机设置 X/Y/Z/A 的角度采集 TCA 通道
- 用户可以在上位机设置 ADS122C04 所在 TCA 通道
- 下位机角度流会按新映射返回正确的四路角度
- 上位机可以开始/停止 ADS 采集，实时显示电压与吸光度
- 参考电压设置、清空数据、保存 CSV 全部可用
- 重新连接串口后，上位机会自动恢复并下发保存的映射与 ADS 配置

## 12. 结论

这次修改的核心不是“把 NI 设备名改成 ADS122C04”，而是把分光采集链路从“上位机本地采集”迁移为“下位机统一采集 + 串口回传”。

从当前代码结构出发，最合理的实现路径是：

- 下位机统一管理 TCA9548A、MT6701 和 ADS122C04
- 上位机统一管理 I2C 映射和 ADS 参数
- 串口新增分光数据包与配置命令
- 保留现有吸光度计算和图表逻辑，但去掉 NI DAQ 依赖

按这个方案实施，能同时满足“取消 NIDAQ 功能”、“改为 ADS122C04 采集光电电压”、“上下位机同步修改”、“增加用户自定义 I2C 通道选择”这四个目标。
