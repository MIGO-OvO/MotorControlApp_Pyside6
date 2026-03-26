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

# ==================== 设计 Token ====================
# H2/H6/M2: 统一语义色和按钮层级

# 语义色 Token (所有颜色对比度满足 WCAG AA)
COLOR_PRIMARY = "#0055CC"         # 主操作色 (对比度 7.3:1 on white)
COLOR_PRIMARY_HOVER = "#004AB5"
COLOR_PRIMARY_PRESSED = "#003D99"
COLOR_SECONDARY_BG = "#f0f0f2"    # 次级按钮背景
COLOR_SECONDARY_TEXT = "#1d1d1f"  # 次级按钮文字
COLOR_SECONDARY_HOVER = "#e0e0e5"
COLOR_TERTIARY_TEXT = "#555555"   # 工具级按钮文字 (对比度 7.5:1)
COLOR_DANGER = "#CC1100"          # 危险操作 (对比度 6.0:1 on white)
COLOR_DANGER_HOVER = "#B50F00"
COLOR_WARNING = "#A85D00"         # 警告色 (对比度 4.7:1 on white)
COLOR_SUCCESS = "#1E7B34"         # 成功色 (对比度 5.7:1 on white)
COLOR_SUCCESS_HOVER = "#176B2C"
COLOR_TEXT_PRIMARY = "#1d1d1f"
COLOR_TEXT_SECONDARY = "#555555"  # 辅助文字 (对比度 7.5:1)
COLOR_TEXT_MUTED = "#6e6e73"      # 占位符文字 (对比度 4.6:1, AA for large text)
COLOR_BORDER = "#d1d1d6"
COLOR_BORDER_LIGHT = "#e5e5e7"
COLOR_BG_SUBTLE = "#f5f5f7"
COLOR_ACCENT_BLUE = "#0055CC"
COLOR_ACCENT_RED = "#CC1100"
COLOR_ACCENT_ORANGE = "#A85D00"
COLOR_ACCENT_GREEN = "#1E7B34"

# 字体角色 Token
FONT_FAMILY_UI = "'Microsoft YaHei', 'Segoe UI', 'PingFang SC', -apple-system, sans-serif"
FONT_FAMILY_MONO = "'Cascadia Mono', 'Consolas', 'Menlo', monospace"
FONT_SIZE_BASE = 16
FONT_SIZE_SMALL = 13
FONT_SIZE_LARGE = 20

# ==================== 样式表 ====================
MACOS_STYLE = f"""
/* 全局样式 */
QWidget {{
    font-family: {FONT_FAMILY_UI};
    font-size: {FONT_SIZE_BASE}px;
    color: {COLOR_TEXT_PRIMARY};
    background-color: #FFFFFF;
}}

/* 分组框 */
QGroupBox {{
    border: 1px solid {COLOR_BORDER_LIGHT};
    border-radius: 12px;
    margin-top: 10px;
    padding-top: 15px;
    background-color: #FFFFFF;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 15px;
    padding: 0 8px;
    color: {COLOR_TEXT_PRIMARY};
    font-weight: 600;
    background-color: #FFFFFF;
}}

/* H6: Primary 按钮 - 主要动作 */
QPushButton {{
    background-color: {COLOR_PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    min-width: 90px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}

QPushButton:pressed {{
    background-color: {COLOR_PRIMARY_PRESSED};
}}

QPushButton:focus {{
    outline: none;
    border: 2px solid {COLOR_PRIMARY};
    padding: 6px 16px;
}}

QPushButton:disabled {{
    background-color: #d1d1d6;
    color: #6e6e73;
}}

/* 输入控件 */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    background: #FFFFFF;
    selection-background-color: {COLOR_PRIMARY};
}}

QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {COLOR_PRIMARY};
    background: #FFFFFF;
}}

QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border: 1.5px solid #b0b0b5;
}}

QTextEdit {{
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px;
    background: #FFFFFF;
    selection-background-color: {COLOR_PRIMARY};
}}

QTextEdit:focus {{
    border: 1.5px solid {COLOR_PRIMARY};
}}

/* 下拉框箭头 */
QComboBox::drop-down {{
    border: none;
    width: 25px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLOR_TEXT_MUTED};
    margin-right: 8px;
}}

/* 树形控件 */
QTreeWidget {{
    border: 1.5px solid {COLOR_BORDER_LIGHT};
    border-radius: 10px;
    background: #FFFFFF;
    alternate-background-color: #f9f9f9;
    outline: none;
}}

QTreeWidget::item {{
    padding: 5px;
    border-radius: 4px;
}}

QTreeWidget::item:hover {{
    background-color: #f0f0f0;
}}

QTreeWidget::item:selected {{
    background-color: #e3f2fd;
    color: {COLOR_TEXT_PRIMARY};
}}

/* 表格 */
QTableWidget {{
    border: 1.5px solid {COLOR_BORDER_LIGHT};
    border-radius: 10px;
    background: #FFFFFF;
    gridline-color: {COLOR_BORDER_LIGHT};
    outline: none;
}}

QTableWidget::item {{
    padding: 6px;
}}

QTableWidget::item:selected {{
    background-color: #e3f2fd;
    color: {COLOR_TEXT_PRIMARY};
}}

QHeaderView::section {{
    background-color: {COLOR_BG_SUBTLE};
    padding: 8px;
    border: none;
    border-bottom: 1.5px solid {COLOR_BORDER_LIGHT};
    font-weight: 600;
}}

/* 状态栏 */
QStatusBar {{
    background: #FFFFFF;
    border-top: 1px solid {COLOR_BORDER_LIGHT};
    color: {COLOR_TEXT_MUTED};
    padding: 4px 8px;
}}

/* 复选框和单选框 */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 1.5px solid {COLOR_BORDER};
    background: #FFFFFF;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1.5px solid {COLOR_PRIMARY};
}}

QCheckBox::indicator:checked {{
    background-color: {COLOR_PRIMARY};
    border: 1.5px solid {COLOR_PRIMARY};
}}

QRadioButton::indicator {{
    border-radius: 10px;
}}

QRadioButton::indicator:checked {{
    background-color: {COLOR_PRIMARY};
    border: 1.5px solid {COLOR_PRIMARY};
}}

/* 滚动条 */
QScrollBar:vertical {{
    background: {COLOR_BG_SUBTLE};
    width: 12px;
    border-radius: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: #c7c7cc;
    border-radius: 6px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: #aeaeb2;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {COLOR_BG_SUBTLE};
    height: 12px;
    border-radius: 6px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: #c7c7cc;
    border-radius: 6px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #aeaeb2;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* 标签页 */
QTabWidget::pane {{
    border: 0;
    background: #FFFFFF;
}}

QTabBar::tab {{
    background: {COLOR_BG_SUBTLE};
    border: none;
    padding: 8px 16px;
    margin-right: 4px;
    border-radius: 8px;
}}

QTabBar::tab:selected {{
    background: {COLOR_PRIMARY};
    color: white;
}}

QTabBar::tab:hover:!selected {{
    background: {COLOR_BORDER_LIGHT};
}}

/* 分隔线 */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {COLOR_BORDER_LIGHT};
}}

/* 自定义组件 */
MotorStatusButton {{
    background-color: {COLOR_PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    min-width: 90px;
    font-weight: 500;
}}

MotorStatusButton:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}

MotorStatusButton:checked {{
    background-color: {COLOR_PRIMARY_PRESSED};
}}

MotorCircle {{
    border: 2px solid {COLOR_PRIMARY};
    border-radius: 50%;
    background-color: #FFFFFF;
}}

ChartWidget {{
    background-color: #FFFFFF;
    border: 1.5px solid {COLOR_BORDER_LIGHT};
    border-radius: 10px;
    padding: 16px;
}}
"""

# H6: Secondary 按钮样式 (用于工具级操作: 加载/保存/刷新等)
BUTTON_SECONDARY = f"""
    QPushButton {{
        background-color: {COLOR_SECONDARY_BG};
        color: {COLOR_SECONDARY_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        padding: 8px 18px;
        min-width: 80px;
        font-weight: 400;
    }}
    QPushButton:hover {{
        background-color: {COLOR_SECONDARY_HOVER};
    }}
    QPushButton:pressed {{
        background-color: #d5d5da;
    }}
"""

# H6: Danger 按钮样式 (用于危险操作: 重置/停止等)
BUTTON_DANGER = f"""
    QPushButton {{
        background-color: {COLOR_DANGER};
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        min-width: 80px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {COLOR_DANGER_HOVER};
    }}
"""

# H6: Success 按钮样式 (用于确认/开始操作)
BUTTON_SUCCESS = f"""
    QPushButton {{
        background-color: {COLOR_SUCCESS};
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        min-width: 80px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {COLOR_SUCCESS_HOVER};
    }}
"""

# H6: Tertiary 按钮样式 (最低优先级: 清空/删除等)
BUTTON_TERTIARY = f"""
    QPushButton {{
        background-color: transparent;
        color: {COLOR_TERTIARY_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        padding: 6px 14px;
        min-width: 60px;
        font-weight: 400;
    }}
    QPushButton:hover {{
        background-color: {COLOR_BG_SUBTLE};
    }}
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
