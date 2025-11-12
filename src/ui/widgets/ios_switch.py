"""iOS风格开关控件"""
from PySide6.QtWidgets import QCheckBox


class IOSSwitch(QCheckBox):
    """iOS风格的开关控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 30)
        self.setStyleSheet("""
            QCheckBox {
                background-color: #e5e5e5;
                border-radius: 15px;
            }
            QCheckBox::indicator {
                width: 30px;
                height: 30px;
                border-radius: 15px;
                background-color: white;
                border: 1px solid #cccccc;
            }
            QCheckBox::indicator:checked {
                background-color: #34c759;
                border: none;
                image: none;
                margin-left: 30px;
            }
        """)

