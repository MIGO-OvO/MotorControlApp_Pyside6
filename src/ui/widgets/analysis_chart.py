"""数据分析图表组件"""
from collections import deque
from PySide6.QtCharts import QChart, QLineSeries, QValueAxis, QScatterSeries
from PySide6.QtCore import Qt, QPointF, QMargins
from PySide6.QtGui import QFont, QColor, QPen, QBrush


class AnalysisChart(QChart):
    """数据分析图表"""
    
    def __init__(self):
        super().__init__()
        self.series = {}
        self.markers = {}
        # 减小数据缓冲区大小，提高性能
        self.data = {
            "X": deque(maxlen=500),
            "Y": deque(maxlen=500),
            "Z": deque(maxlen=500),
            "A": deque(maxlen=500)
        }
        # 缓存Y轴范围，避免频繁计算
        self._y_min = -5
        self._y_max = 5
        self._update_count = 0
        self.init_chart()
        self.setup_axes()
        self.auto_scale_margin = 0.1  # 10%的边距
    
    def init_chart(self):
        """初始化图表"""
        colors = [
            QColor("#1f77b4"),  # 蓝色
            QColor("#2ca02c"),  # 绿色
            QColor("#d62728"),  # 红色
            QColor("#9467bd")   # 紫色
        ]
        
        # 创建系列并设置样式
        for i, motor in enumerate(["X", "Y", "Z", "A"]):
            # 主曲线设置
            main_series = QLineSeries()
            pen = QPen(colors[i])
            pen.setWidth(2)
            pen.setStyle(Qt.SolidLine)
            main_series.setPen(pen)
            main_series.setName(f"Motor {motor}")
            
            # 数据标记设置
            marker_series = QScatterSeries()
            marker_series.setMarkerSize(6)
            marker_series.setColor(colors[i])
            marker_series.setBorderColor(Qt.black)
            marker_series.setMarkerShape(QScatterSeries.MarkerShapeCircle)
            
            # 存储系列引用
            self.series[motor] = main_series
            self.markers[motor] = marker_series
            
            # 添加到图表
            self.addSeries(main_series)
            self.addSeries(marker_series)
        
        # 坐标轴设置
        self.axisX = QValueAxis()
        self.axisY = QValueAxis()
        
        # X轴样式
        self.axisX.setTitleText("Time Sequence")
        self.axisX.setTitleFont(QFont("Times New Roman", 18))
        self.axisX.setLabelsFont(QFont("Times New Roman", 12))
        self.axisX.setGridLineColor(QColor(220, 220, 220))
        self.axisX.setLinePen(QPen(Qt.black, 1.5))
        self.axisX.setLabelFormat("%d")
        
        # Y轴样式
        self.axisY.setTitleText("Deviation（°）")
        self.axisY.setTitleFont(QFont("Times New Roman", 18))
        self.axisY.setLabelsFont(QFont("Times New Roman", 12))
        self.axisY.setGridLineColor(QColor(220, 220, 220))
        self.axisY.setLinePen(QPen(Qt.black, 1.5))
        self.axisY.setLabelFormat("%.2f")
        
        # 添加坐标轴
        self.addAxis(self.axisX, Qt.AlignBottom)
        self.addAxis(self.axisY, Qt.AlignLeft)
        
        # 将系列附加到坐标轴
        for series in self.series.values():
            series.attachAxis(self.axisX)
            series.attachAxis(self.axisY)
            series.setUseOpenGL(True)  # 启用硬件加速
            series.setPointsVisible(False)
        
        # 标记点优化
        for marker in self.markers.values():
            marker.setBorderColor(Qt.transparent)
            marker.setBrush(QBrush(Qt.SolidPattern))
        
        # 图例设置
        self.legend().setVisible(True)
        self.legend().setAlignment(Qt.AlignTop)
        self.legend().setFont(QFont("Times New Roman", 14))
        self.legend().setLabelColor(Qt.black)
        
        # 图表整体样式
        self.setBackgroundVisible(False)
        self.setMargins(QMargins(10, 10, 10, 5))
        self.setContentsMargins(0, 0, 0, 0)
    
    def setup_axes(self):
        """初始化轴范围"""
        self.axisX.setRange(0, 60)
        self.axisY.setRange(-5, 5)
        self.axisX.setLabelFormat("%.0f")
        self.axisY.setLabelFormat("%.2f")
        self.axisY.applyNiceNumbers()
    
    def update_data(self, deviations):
        """只更新启用电机的数据 - 优化版本"""
        try:
            # 获取当前活动电机
            parent = self.parent()
            active_motors = parent.active_motors if hasattr(parent, 'active_motors') else ["X", "Y", "Z", "A"]
            
            # 过滤数据
            valid_data = {
                k: round(v, 3)
                for k, v in deviations.get("theoretical", {}).items()
                if v is not None and k in self.data and k in active_motors
            }
            
            if not valid_data:
                return
            
            # 更新数据存储
            for motor, dev in valid_data.items():
                self.data[motor].append(dev)
                
                # 更新Y轴范围缓存
                if dev < self._y_min:
                    self._y_min = dev
                if dev > self._y_max:
                    self._y_max = dev
            
            # 每5次更新才刷新图表曲线（降低刷新频率）
            self._update_count += 1
            if self._update_count >= 5:
                self._update_count = 0
                self._refresh_series(valid_data.keys())
        except Exception as e:
            print(f"AnalysisChart update_data error: {e}")
    
    def _refresh_series(self, motors):
        """刷新指定电机的曲线"""
        try:
            for motor in motors:
                if motor not in self.data:
                    continue
                data_list = list(self.data[motor])
                if not data_list:
                    continue
                
                # 只显示最近100个点
                display_data = data_list[-100:]
                start_idx = max(0, len(data_list) - 100)
                points = [QPointF(start_idx + i, y) for i, y in enumerate(display_data)]
                
                self.series[motor].replace(points)
                
                # 更新标记点
                if points:
                    self.markers[motor].replace([points[-1]])
            
            # 更新坐标轴
            self._update_axes()
        except Exception as e:
            print(f"_refresh_series error: {e}")
    
    def _update_axes(self):
        """更新坐标轴范围"""
        try:
            # Y轴使用缓存的范围
            y_range = self._y_max - self._y_min
            margin = max(y_range * self.auto_scale_margin, 0.5)
            self.axisY.setRange(self._y_min - margin, self._y_max + margin)
            
            # X轴
            max_length = max((len(d) for d in self.data.values()), default=0)
            if max_length > 0:
                start = max(0, max_length - 100)
                self.axisX.setRange(start, max(max_length, start + 100))
        except Exception:
            pass
    
    def auto_scale_axes(self):
        """智能坐标轴缩放算法 - 使用缓存值"""
        self._update_axes()
    
    def clear(self):
        """清空所有数据"""
        for motor in ["X", "Y", "Z", "A"]:
            self.data[motor].clear()
            self.series[motor].replace([])
            self.markers[motor].replace([])
        # 重置Y轴范围缓存
        self._y_min = -5
        self._y_max = 5
        self._update_count = 0
        self.setup_axes()
        self.update()
    
    def get_chart_data(self):
        """获取当前图表数据"""
        return {
            motor: list(self.data[motor])
            for motor in ["X", "Y", "Z", "A"]
        }
    
    def get_motor_data(self, motor):
        """获取指定电机的完整数据"""
        return list(self.data.get(motor, []))
    
    def replace_data(self, motor, data_points):
        """替换指定电机的数据序列"""
        if motor in self.series:
            points = [QPointF(x, y) for x, y in enumerate(data_points)]
            self.series[motor].replace(points)
            self.data[motor] = deque(data_points, maxlen=200)
            self.auto_scale_axes()

