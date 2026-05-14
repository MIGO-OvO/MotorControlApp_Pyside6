# MotorControlApp_Pyside6 — 环境现场监测系统控制程序

## OVERVIEW

基于 PySide6 的 Windows 桌面工具，用于独立控制 ESP32 检测装置（四轴步进电机 + 进样泵 + 分光采集）。支持 PID 闭环定位、贝叶斯参数自动优化、自动化流程编排、光谱仪电压采集及实时可视化。与 ROS 端 `pump_control_node.py` 功能平行但面向单机调试场景。

## STRUCTURE

```
MotorControlApp_Pyside6/
├── main.py                    # 应用入口
├── start.bat                  # Windows 一键启动
├── requirements.txt           # PySide6, pyserial, numpy, pandas, scikit-optimize...
├── data/                      # 运行时数据（presets.json, settings.json）
├── src/
│   ├── config/
│   │   ├── constants.py       # 全局常量、样式表
│   │   └── settings.py        # 用户设置持久化
│   ├── core/                  # 核心业务逻辑
│   │   ├── serial_manager.py  # 串口连接管理（含握手、断线重连）
│   │   ├── command_generator.py # 电机命令生成（J/R 指令编码）
│   │   ├── automation_engine.py # 多步骤自动化流程执行
│   │   ├── pid_optimizer.py   # 贝叶斯 PID 优化（高斯过程 + EI 采集函数）
│   │   ├── pid_analyzer.py    # PID 测试结果分析
│   │   └── preset_manager.py  # 预设 JSON 持久化
│   ├── hardware/
│   │   ├── serial_reader.py   # 串口异步读取线程（混合协议解析）
│   │   └── daq_thread.py      # NIDAQmx 光谱仪电压采集
│   ├── ui/
│   │   ├── main_window_complete.py  # 主窗口（Mixin 组合）
│   │   ├── mixins/            # 功能模块混入（serial/automation/pid/...）
│   │   ├── widgets/           # 自定义控件（电机圆盘/图表/优化面板）
│   │   └── dialogs/           # 对话框（I2C 设置/电机步进配置）
│   └── utils/
│       ├── data_handler.py    # 数据处理
│       └── logger.py          # 日志
└── tests/                     # pytest 测试
```

## WHERE TO LOOK

| 需求 | 位置 |
|------|------|
| 串口连接 + 握手 | `src/core/serial_manager.py` → `connect_port()`, `_perform_handshake()` |
| 电机命令发送 | `src/core/command_generator.py` |
| PID 贝叶斯优化 | `src/core/pid_optimizer.py` → `BayesianPIDOptimizer` |
| 自动化流程 | `src/core/automation_engine.py` → `AutomationThread` |
| 串口协议解析 | `src/hardware/serial_reader.py` → `SerialReader` |
| UI 主窗口 | `src/ui/main_window_complete.py` |
| 功能混入 | `src/ui/mixins/` 目录（按功能拆分） |

## CONVENTIONS

- **Mixin 架构**：主窗口类 `MotorControlApp` 通过多重继承组合 `SerialMixin`、`AutomationMixin`、`PIDDataMixin` 等功能模块。每个 Mixin 负责一组相关 UI + 逻辑。
- **Qt 信号槽**：跨线程（串口读取线程 → UI 主线程）使用 Qt Signal/Slot 安全通信。
- **弱引用**：自动化线程对主窗口使用 `weakref` 避免循环引用。
- **串口握手**：连接 ESP32 后必须先 `HELLO?` 握手，验证返回 `DET_ID:USV_DETECTOR*`，失败则关闭串口并弹错误。
- **代码风格**：Black 格式化，mypy 类型检查，flake8 代码检查。

## COMMANDS

```bash
# 创建虚拟环境 + 安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 运行
python main.py

# 测试
pytest tests/ -v

# 代码检查
black src/ tests/
mypy src/
flake8 src/
```

## NOTES

- 与 `DetFirmware/` 共享同一套串口协议（115200 8N1，文本命令 `\r\n` 终止，二进制包 0x55 帧头）。
- 与 ROS 端 `pump_control_node.py` 功能平行但面向 Windows 单机场景，无 ROS 依赖。
- 光谱仪功能需要 NI-DAQmx 驱动（仅 Windows）。
- 下位机固件参考副本 `lowerDevice/` 已过时，以 `DetFirmware/` 为准。
