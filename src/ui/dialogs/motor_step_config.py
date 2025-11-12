"""电机步骤配置对话框"""
import weakref
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QGroupBox, QCheckBox, QRadioButton, QLineEdit,
    QLabel, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QButtonGroup, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...config.constants import MOTOR_NAMES


class MotorStepConfig(QDialog):
    """电机步骤配置对话框"""
    
    def __init__(self, parent, step_num: int, initial_params: Optional[Dict] = None):
        """
        初始化对话框
        
        Args:
            parent: 父窗口
            step_num: 步骤编号
            initial_params: 初始参数
        """
        super().__init__(parent)
        self.parent = weakref.ref(parent)
        self.step_params = initial_params or {}
        self.setWindowTitle(f"步骤 {step_num} 参数配置")
        self.setFixedSize(500, 650)
        self.setWindowModality(Qt.ApplicationModal)
        self.init_ui()
        self.load_initial_params()
    
    def init_ui(self):
        """初始化UI"""
        layout = QGridLayout()
        self.widgets = {}
        
        # 步骤名称
        name_frame = QFrame()
        hbox = QHBoxLayout(name_frame)
        name_lbl = QLabel("步骤名称:")
        name_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.name_entry = QLineEdit()
        self.name_entry.setFont(QFont("Microsoft YaHei", 16))
        self.name_entry.setFixedHeight(40)
        self.name_entry.setPlaceholderText("输入步骤名称")
        hbox.addWidget(name_lbl)
        hbox.addWidget(self.name_entry)
        layout.addWidget(name_frame, 0, 0, 1, 2)
        
        # 电机控制区
        for i, motor in enumerate(MOTOR_NAMES):
            group = QGroupBox(f"电机 {motor}")
            group.setFont(QFont("Microsoft YaHei", 13))
            vbox = QVBoxLayout(group)
            
            # 启用开关
            enable_check = QCheckBox("启用电机")
            enable_check.setFont(QFont("Microsoft YaHei", 16))
            vbox.addWidget(enable_check)
            
            # 方向选择
            dir_group = QButtonGroup(self)
            dir_frame = QFrame()
            hbox = QHBoxLayout(dir_frame)
            forward_btn = QRadioButton("正转")
            backward_btn = QRadioButton("反转")
            forward_btn.setFont(QFont("Microsoft YaHei", 16))
            backward_btn.setFont(QFont("Microsoft YaHei", 16))
            dir_group.addButton(forward_btn)
            dir_group.addButton(backward_btn)
            forward_btn.setChecked(True)
            hbox.addWidget(forward_btn)
            hbox.addWidget(backward_btn)
            vbox.addWidget(dir_frame)
            
            # 速度和角度输入
            speed_entry = QLineEdit()
            speed_entry.setPlaceholderText("速度值 (RPM)")
            speed_entry.setFont(QFont("Microsoft YaHei", 16))
            speed_entry.setFixedHeight(40)
            vbox.addWidget(speed_entry)
            
            angle_entry = QLineEdit()
            angle_entry.setPlaceholderText("角度值")
            angle_entry.setFont(QFont("Microsoft YaHei", 16))
            angle_entry.setFixedHeight(40)
            vbox.addWidget(angle_entry)
            
            self.widgets[motor] = {
                "enable": enable_check,
                "direction": dir_group,
                "speed": speed_entry,
                "angle": angle_entry
            }
            
            layout.addWidget(group, (i // 2) + 1, i % 2)
        
        # 间隔时间
        interval_frame = QFrame()
        hbox = QHBoxLayout(interval_frame)
        interval_lbl = QLabel("间隔时间(ms):")
        interval_lbl.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry = QLineEdit()
        self.interval_entry.setFont(QFont("Microsoft YaHei", 16))
        self.interval_entry.setFixedHeight(40)
        hbox.addWidget(interval_lbl)
        hbox.addWidget(self.interval_entry)
        layout.addWidget(interval_frame, 3, 0, 1, 2)
        
        # 按钮
        btn_frame = QFrame()
        hbox_btn = QHBoxLayout(btn_frame)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = QPushButton("确认")
        confirm_btn.clicked.connect(self.save_params)
        hbox_btn.addWidget(cancel_btn)
        hbox_btn.addWidget(confirm_btn)
        layout.addWidget(btn_frame, 4, 0, 1, 2)
        
        self.setLayout(layout)
    
    def load_initial_params(self):
        """加载初始参数"""
        if self.step_params:
            self.name_entry.setText(self.step_params.get("name", ""))
            for motor in MOTOR_NAMES:
                params = self.step_params.get(motor, {})
                widgets = self.widgets[motor]
                widgets["enable"].setChecked(params.get("enable", "D") == "E")
                if params.get("direction", "F") == "F":
                    widgets["direction"].buttons()[0].setChecked(True)
                else:
                    widgets["direction"].buttons()[1].setChecked(True)
                widgets["speed"].setText(params.get("speed", ""))
                widgets["angle"].setText(params.get("angle", ""))
            self.interval_entry.setText(str(self.step_params.get("interval", 0)))
    
    def save_params(self):
        """保存参数"""
        try:
            params = {"name": self.name_entry.text()}
            for motor in MOTOR_NAMES:
                widgets = self.widgets[motor]
                enable = "E" if widgets["enable"].isChecked() else "D"
                direction = "F" if widgets["direction"].checkedButton().text() == "正转" else "B"
                
                speed_text = widgets["speed"].text().strip()
                speed = "0" if not speed_text else f"{float(speed_text):.1f}".rstrip('0').rstrip('.')
                
                angle_text = widgets["angle"].text().strip().upper()
                if not angle_text:
                    angle = "0"
                elif angle_text == "G":
                    angle = "G"
                else:
                    angle = f"{float(angle_text):.3f}".rstrip('0').rstrip('.')
                
                params[motor] = {
                    "enable": enable,
                    "direction": direction,
                    "speed": speed,
                    "angle": angle
                }
            
            interval_text = self.interval_entry.text().strip()
            params["interval"] = 5000 if not interval_text else int(interval_text)
            
            self.step_params = params
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "输入错误", str(e))

