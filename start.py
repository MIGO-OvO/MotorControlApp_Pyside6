"""

"""
import sys
import os
import ctypes
import platform

# 设置路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows平台设置
if platform.system() == 'Windows':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("motor.control.v1")
    except:
        pass
    
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

# 设置高DPI缩放
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

# 创建应用程序
app = QApplication(sys.argv)
app.setApplicationName("电机控制系统")
app.setApplicationVersion("2.0.0 (完整功能重构版)")

# 导入完整功能主窗口
from src.ui.main_window_complete import MotorControlApp
from src.config.constants import MACOS_STYLE

try:
    app.setWindowIcon(QIcon('resources/icons/meow.ico'))
except:
    pass

app.setStyleSheet(MACOS_STYLE)

# 创建并显示主窗口
window = MotorControlApp()
window.show()

# 运行
exit_code = app.exec()

# 清理
if platform.system() == 'Windows':
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except:
        pass

sys.exit(exit_code)

