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
        
        # 动画
        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setDuration(1000)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
    
    def set_angle(self, angle: float):
        """设置角度"""
        self.target_angle = angle
        if hasattr(self, 'animation'):
            self.animation.stop()
            self.animation.setStartValue(self._angle)
            self.animation.setEndValue(angle)
            self.animation.start()
        self._angle = angle
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

