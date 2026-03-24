"""
全局常量配置
包含样式表、默认值、硬件配置等
"""

from typing import Dict, List

# ==================== 应用信息 ====================
APP_NAME = "环境现场监测系统控制程序"
APP_VERSION = "2.0.0"
APP_ID = "motor.control.v1"

# ==================== 电机配置 ====================
MOTOR_NAMES: List[str] = ["X", "Y", "Z", "A"]
DEFAULT_SPEED = 5  # RPM
DEFAULT_ANGLE = 0.0
MAX_DATA_POINTS = 10000  # 图表最大数据点数

# ==================== 串口配置 ====================
DEFAULT_PORT = "COM4"
DEFAULT_BAUDRATE = 115200
AVAILABLE_BAUDRATES: List[str] = ["9600", "19200", "38400", "57600", "115200"]
SERIAL_TIMEOUT = 1  # 秒
WRITE_TIMEOUT = 1  # 秒

# ==================== 时间配置 ====================
CALIBRATION_WAIT_TIME = 10000  # 毫秒
ANGLE_REQUEST_WAIT = 100  # 毫秒
DEFAULT_INTERVAL = 5000  # 默认步骤间隔（毫秒）
AUTOMATION_WAIT_TIMEOUT = 1000  # 自动化线程等待超时
CHART_UPDATE_INTERVAL = 100  # 图表更新间隔（毫秒）

# ==================== 校准配置 ====================
CALIBRATION_PRECISION = 1.5  # 校准精度（度）
MAX_CALIBRATION_ATTEMPTS = 3  # 最大校准尝试次数
DEFAULT_CALIBRATION_AMPLITUDE = 1.0  # 默认校准幅值

# ==================== 光谱仪配置 ====================
DEFAULT_SAMPLE_RATE = 90  # SPS (ADS122C04 默认采样率)
MAX_SPECTRO_DATA_POINTS = 500

# ADS122C04 支持的采样率列表 (Normal mode)
ADS_SUPPORTED_RATES = [20, 45, 90, 175, 330, 600, 1000]
# ADS122C04 Turbo mode 采样率列表
ADS_TURBO_RATES = [40, 90, 180, 350, 660, 1200, 2000]

# 默认 I2C 通道映射
DEFAULT_I2C_MAPPING = {
    "angles": {"X": 0, "Y": 3, "Z": 4, "A": 7},
    "spectro_channel": 2,
}

# 默认 ADS122C04 配置
DEFAULT_ADS_CONFIG = {
    "ads_address": "0x40",
    "ain": "AIN0",
    "vref": "AVDD",
    "gain": 1,
    "pga_bypass": True,
    "mode": "continuous",
    "adc_rate": 90,
    "publish_rate": 50,
}

# ADS 参考源选项
ADS_VREF_OPTIONS = ["AVDD", "INT_2V048"]
# ADS 增益选项 (PGA旁路模式下)
ADS_GAIN_OPTIONS = [1, 2, 4]
# ADS AIN 输入选项
ADS_AIN_OPTIONS = ["AIN0", "AIN1", "AIN2", "AIN3"]
# 串口上传频率范围
ADS_PUBLISH_RATE_RANGE = (1, 200)

# ==================== 文件路径 ====================
PRESETS_FILE = "data/presets.json"
SETTINGS_FILE = "data/settings.json"
ICON_PATH = "resources/icons/meow.ico"
STYLE_PATH = "resources/styles/macos.qss"

# ==================== UI配置 ====================
MIN_WINDOW_WIDTH = 1280
MIN_WINDOW_HEIGHT = 960
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 960

# ==================== 样式表 ====================
MACOS_STYLE = """
/* 全局样式 */
QWidget {
    font-family: 'Times New Roman', 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
    font-size: 18px;
    color: #1d1d1f;
    background-color: #FFFFFF;
}

/* 分组框 - 添加阴影效果和更圆润的边框 */
QGroupBox {
    border: 1px solid #e5e5e7;
    border-radius: 12px;
    margin-top: 10px;
    padding-top: 15px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 15px;
    padding: 0 8px;
    color: #1d1d1f;
    font-weight: 600;
    background-color: #FFFFFF;
}

/* 按钮 - 添加悬停动画和阴影 */
QPushButton {
    background-color: #007aff;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    min-width: 90px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #0071e3;
    padding: 8px 18px;
}

QPushButton:pressed {
    background-color: #0051a8;
    padding: 8px 18px;
}

QPushButton:disabled {
    background-color: #d1d1d6;
    color: #8e8e93;
}

/* 输入控件 - 添加焦点效果 */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    border: 1.5px solid #d1d1d6;
    border-radius: 8px;
    padding: 7px 10px;
    background: #FFFFFF;
    selection-background-color: #007aff;
}

QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1.5px solid #007aff;
    background: #FFFFFF;
}

QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border: 1.5px solid #b0b0b5;
}

QTextEdit {
    border: 1.5px solid #d1d1d6;
    border-radius: 8px;
    padding: 8px;
    background: #FFFFFF;
    selection-background-color: #007aff;
}

QTextEdit:focus {
    border: 1.5px solid #007aff;
}

/* 下拉框箭头 */
QComboBox::drop-down {
    border: none;
    width: 25px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #8e8e93;
    margin-right: 8px;
}

/* 树形控件 - 优化斑马纹 */
QTreeWidget {
    border: 1.5px solid #e5e5e7;
    border-radius: 10px;
    background: #FFFFFF;
    alternate-background-color: #f9f9f9;
    outline: none;
}

QTreeWidget::item {
    padding: 5px;
    border-radius: 4px;
}

QTreeWidget::item:hover {
    background-color: #f0f0f0;
}

QTreeWidget::item:selected {
    background-color: #e3f2fd;
    color: #1d1d1f;
}

/* 表格 - 优化样式 */
QTableWidget {
    border: 1.5px solid #e5e5e7;
    border-radius: 10px;
    background: #FFFFFF;
    gridline-color: #e5e5e7;
    outline: none;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #e3f2fd;
    color: #1d1d1f;
}

QHeaderView::section {
    background-color: #f5f5f7;
    padding: 8px;
    border: none;
    border-bottom: 1.5px solid #e5e5e7;
    font-weight: 600;
}

/* 状态栏 */
QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #e5e5e7;
    color: #6e6e73;
    padding: 4px 8px;
}

/* 复选框和单选框 */
QCheckBox::indicator, QRadioButton::indicator {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 1.5px solid #d1d1d6;
    background: #FFFFFF;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border: 1.5px solid #007aff;
}

QCheckBox::indicator:checked {
    background-color: #007aff;
    border: 1.5px solid #007aff;
}

QRadioButton::indicator {
    border-radius: 10px;
}

QRadioButton::indicator:checked {
    background-color: #007aff;
    border: 1.5px solid #007aff;
}

/* 滚动条 - 现代化设计 */
QScrollBar:vertical {
    background: #f5f5f7;
    width: 12px;
    border-radius: 6px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #c7c7cc;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #aeaeb2;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #f5f5f7;
    height: 12px;
    border-radius: 6px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #c7c7cc;
    border-radius: 6px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #aeaeb2;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 标签页 */
QTabWidget::pane {
    border: 0;
    background: #FFFFFF;
}

QTabBar::tab {
    background: #f5f5f7;
    border: none;
    padding: 8px 16px;
    margin-right: 4px;
    border-radius: 8px;
}

QTabBar::tab:selected {
    background: #007aff;
    color: white;
}

QTabBar::tab:hover:!selected {
    background: #e5e5e7;
}

/* 分隔线 */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #e5e5e7;
}

/* 自定义组件 */
MotorStatusButton {
    background-color: #007aff;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    min-width: 90px;
    font-weight: 500;
}

MotorStatusButton:hover {
    background-color: #0071e3;
}

MotorStatusButton:checked {
    background-color: #0051a8;
}

MotorCircle {
    border: 2px solid #007aff;
    border-radius: 50%;
    background-color: #FFFFFF;
}

ChartWidget {
    background-color: #FFFFFF;
    border: 1.5px solid #e5e5e7;
    border-radius: 10px;
    padding: 16px;
}
"""

# ==================== 图表颜色配置 ====================
CHART_COLORS: Dict[str, str] = {
    "X": "#1f77b4",  # 蓝色
    "Y": "#2ca02c",  # 绿色
    "Z": "#d62728",  # 红色
    "A": "#9467bd",  # 紫色
}

# ==================== 偏差阈值 ====================
DEVIATION_THRESHOLDS = {"warning": 2.0, "critical": 5.0}  # 橙色警告阈值  # 红色严重阈值

# ==================== 指令格式 ====================
COMMAND_TERMINATOR = "\r\n"
ANGLE_REQUEST_COMMAND = "GETANGLE"
ANGLE_RESPONSE_PREFIX = "ANGLE"

# ==================== 方向映射 ====================
DIRECTION_MAP = {"F": 1, "B": -1}  # 正转  # 反转

# ==================== 日志配置 ====================
LOG_TIME_FORMAT = "%H:%M:%S.%f"
LOG_DATE_FORMAT = "%Y%m%d_%H%M%S"
