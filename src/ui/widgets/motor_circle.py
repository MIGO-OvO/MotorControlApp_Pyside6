"""电机角度可视化圆盘控件"""
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QPen, QBrush, QColor


class MotorCircle(QWidget):
    """电机角度可视化圆盘"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.target_angle = 0
        self.setFixedSize(150, 150)
        
        # 禁用动画以提高性能（高频更新时动画会导致卡顿）
        self._use_animation = False
        self._last_update_time = 0
        self._update_interval = 0.05  # 最小更新间隔50ms (20Hz)
    
    def set_angle(self, angle: float):
        """设置角度 - 优化版本，带节流"""
        import time
        self.target_angle = angle
        self._angle = angle
        
        # 节流：限制UI更新频率
        current_time = time.time()
        if current_time - self._last_update_time >= self._update_interval:
            self._last_update_time = current_time
            self.update()
    
    def get_angle(self) -> float:
        """获取角度"""
        return self._angle
    
    angle = property(get_angle, set_angle)
    
    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 背景圆
        painter.setPen(QPen(QColor(200, 200, 200), 4))
        painter.drawEllipse(10, 10, 130, 130)
        
        # 转轴
        painter.setPen(QPen(QColor(0, 122, 255), 5))
        painter.setBrush(QBrush(QColor(0, 122, 255, 50)))
        radius = 50
        center = QPointF(75, 75)
        end_x = center.x() + radius * math.cos(math.radians(self.angle - 90))
        end_y = center.y() + radius * math.sin(math.radians(self.angle - 90))
        painter.drawLine(center, QPointF(end_x, end_y))
        painter.drawEllipse(center, 15, 15)

