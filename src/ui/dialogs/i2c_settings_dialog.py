from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.config.constants import ADS_GAIN_OPTIONS, ADS_SUPPORTED_RATES, ADS_VREF_OPTIONS


class I2CSettingsDialog(QDialog):
    """I2C 与 ADS122C04 设置对话框。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("I2C设置")
        self.resize(420, 420)
        self._build_ui()
        self._load_from_parent()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        i2c_group = QGroupBox("I2C 通道映射 (TCA9548A)")
        i2c_group.setFont(QFont("Microsoft YaHei", 11))
        i2c_form = QFormLayout(i2c_group)
        self.i2c_spins = {}
        for key, label in [("X", "角度传感器 X:"), ("Y", "角度传感器 Y:"), ("Z", "角度传感器 Z:"), ("A", "角度传感器 A:"), ("SPEC", "分光 ADC:")]:
            spin = QSpinBox()
            spin.setRange(0, 7)
            self.i2c_spins[key] = spin
            i2c_form.addRow(label, spin)
        layout.addWidget(i2c_group)

        ads_group = QGroupBox("ADS122C04 配置")
        ads_group.setFont(QFont("Microsoft YaHei", 11))
        ads_form = QFormLayout(ads_group)
        self.ads_addr_combo = QComboBox()
        self.ads_addr_combo.addItems(["0x40", "0x41", "0x44", "0x45"])
        self.ads_vref_combo = QComboBox()
        self.ads_vref_combo.addItems(ADS_VREF_OPTIONS)
        self.ads_gain_combo = QComboBox()
        self.ads_gain_combo.addItems([str(g) for g in ADS_GAIN_OPTIONS])
        self.ads_rate_combo = QComboBox()
        self.ads_rate_combo.addItems([str(r) for r in ADS_SUPPORTED_RATES])
        self.ads_publish_spin = QSpinBox()
        self.ads_publish_spin.setRange(1, 200)
        ads_form.addRow("ADS 地址:", self.ads_addr_combo)
        ads_form.addRow("参考源:", self.ads_vref_combo)
        ads_form.addRow("增益:", self.ads_gain_combo)
        ads_form.addRow("ADC 数据率:", self.ads_rate_combo)
        ads_form.addRow("上传频率 (Hz):", self.ads_publish_spin)
        layout.addWidget(ads_group)

        action_row = QHBoxLayout()
        self.read_btn = QPushButton("读取下位机配置")
        self.read_btn.clicked.connect(self.parent_window._i2c_read_from_device)
        self.apply_btn = QPushButton("应用到下位机")
        self.apply_btn.clicked.connect(self._apply_to_parent_and_device)
        action_row.addWidget(self.read_btn)
        action_row.addWidget(self.apply_btn)
        layout.addLayout(action_row)

        footer = QHBoxLayout()
        footer.addStretch()
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self._save_settings)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(save_btn)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

    def _load_from_parent(self):
        parent = self.parent_window
        if hasattr(parent, "i2c_map_spins"):
            for key, spin in self.i2c_spins.items():
                spin.setValue(parent.i2c_map_spins[key].value())
        if hasattr(parent, "spectro_ads_addr_combo"):
            self.ads_addr_combo.setCurrentText(parent.spectro_ads_addr_combo.currentText())
            self.ads_vref_combo.setCurrentText(parent.spectro_vref_combo.currentText())
            self.ads_gain_combo.setCurrentText(parent.spectro_gain_combo.currentText())
            self.ads_rate_combo.setCurrentText(parent.spectro_rate_combo.currentText())
            self.ads_publish_spin.setValue(parent.spectro_publish_spin.value())

    def _apply_to_parent_widgets(self):
        parent = self.parent_window
        if hasattr(parent, "i2c_map_spins"):
            for key, spin in self.i2c_spins.items():
                parent.i2c_map_spins[key].setValue(spin.value())
        if hasattr(parent, "spectro_ads_addr_combo"):
            parent.spectro_tca_channel_spin.setValue(self.i2c_spins["SPEC"].value())
            parent.spectro_ads_addr_combo.setCurrentText(self.ads_addr_combo.currentText())
            parent.spectro_vref_combo.setCurrentText(self.ads_vref_combo.currentText())
            parent.spectro_gain_combo.setCurrentText(self.ads_gain_combo.currentText())
            parent.spectro_rate_combo.setCurrentText(self.ads_rate_combo.currentText())
            parent.spectro_publish_spin.setValue(self.ads_publish_spin.value())

    def _apply_to_parent_and_device(self):
        self._apply_to_parent_widgets()
        self.parent_window._i2c_apply_to_device()
        self.parent_window.save_settings()

    def _save_settings(self):
        self._apply_to_parent_widgets()
        self.parent_window.save_settings()
        self.parent_window.status_bar.showMessage("I2C / ADS 设置已保存", 3000)

