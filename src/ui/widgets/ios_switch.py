"""iOS风格开关控件 - H1: 增强可访问性"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox


class IOSSwitch(QCheckBox):
    """iOS风格的开关控件

    H1: 增加键盘可达性和可访问语义。
    """

    def __init__(self, parent=None, accessible_name: str = ""):
        super().__init__(parent)
        self.setFixedSize(60, 30)
        # H1: 设置可访问属性
        if accessible_name:
            self.setAccessibleName(accessible_name)
        self.setAccessibleDescription("切换开关")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            """
            QCheckBox {
                background-color: #e5e5e5;
                border-radius: 15px;
            }
            QCheckBox:focus {
                border: 2px solid #0055CC;
            }
            QCheckBox::indicator {
                width: 30px;
                height: 30px;
                border-radius: 15px;
                background-color: white;
                border: 1px solid #cccccc;
            }
            QCheckBox::indicator:checked {
                background-color: #1E7B34;
                border: none;
                image: none;
                margin-left: 30px;
            }
        """
        )

    def keyPressEvent(self, event):
        """H1: 支持空格键和回车键切换"""
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self.isChecked())
            event.accept()
        else:
            super().keyPressEvent(event)
