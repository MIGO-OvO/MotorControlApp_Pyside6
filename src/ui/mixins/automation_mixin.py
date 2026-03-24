"""自动化控制 Mixin 模块。

该模块提供自动化流程控制相关功能，包括：
- 自动化步骤管理（添加/删除/编辑/复制/粘贴）
- 自动化流程执行和停止
- 自动化预设管理（保存/加载）
"""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
)

from src.core.automation_engine import AutomationThread
from src.ui.dialogs.motor_step_config import MotorStepConfig
from src.ui.widgets import DragDropTreeWidget


class AutomationMixin:
    """自动化控制功能 Mixin。

    提供自动化步骤管理、流程执行和预设管理功能。

    Attributes:
        automation_steps: 自动化步骤列表
        automation_thread: 自动化执行线程
        copied_step: 复制的步骤数据
    """

    def init_auto_tab(self) -> None:
        """初始化自动化控制标签页的UI。"""
        layout = QVBoxLayout(self.auto_tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # 预设管理
        preset_frame = QFrame()
        hbox = QHBoxLayout(preset_frame)

        self.auto_preset_combo = QComboBox()
        self.auto_preset_combo.setFont(QFont("Microsoft YaHei", 16))
        self.auto_preset_combo.setFixedWidth(200)

        preset_lbl = QLabel("自动预设:")
        load_btn = QPushButton("加载")
        load_btn.clicked.connect(self.load_auto_preset)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_auto_preset)
        del_auto_btn = QPushButton("删除")
        del_auto_btn.clicked.connect(lambda: self.delete_preset("auto"))

        hbox.addWidget(QLabel("自动预设:"))
        hbox.addWidget(self.auto_preset_combo)
        hbox.addWidget(load_btn)
        hbox.addWidget(save_btn)
        hbox.addWidget(del_auto_btn)
        layout.addWidget(preset_frame)

        # 步骤表格
        from PySide6.QtWidgets import QTreeWidget

        self.steps_table = DragDropTreeWidget()
        self.steps_table.setHeaderLabels(["编号", "名称", "参数配置", "间隔(s)"])
        self.steps_table.setRootIsDecorated(False)
        self.steps_table.setUniformRowHeights(True)
        self.steps_table.setSortingEnabled(False)
        self.steps_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        for i in range(self.steps_table.columnCount()):
            header_item = self.steps_table.headerItem()
            header_item.setTextAlignment(i, Qt.AlignmentFlag.AlignCenter)
        self.steps_table.setColumnWidth(0, 80)
        self.steps_table.setColumnWidth(1, 150)
        self.steps_table.setColumnWidth(2, 500)
        self.steps_table.setColumnWidth(3, 120)
        self.steps_table.itemDoubleClicked.connect(self.edit_step)
        layout.addWidget(self.steps_table)

        # 控制按钮
        btn_frame = QFrame()
        hbox = QHBoxLayout(btn_frame)
        buttons = [
            ("添加步骤", self.add_step),
            ("删除步骤", self.remove_step),
            ("复制步骤", self.copy_step),
            ("粘贴步骤", self.paste_step),
            ("开始执行", self.start_automation),
            ("停止执行", self.stop_automation),
        ]
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.setFont(QFont("Microsoft YaHei", 16))
            btn.setFixedHeight(40)
            btn.clicked.connect(slot)
            hbox.addWidget(btn)
        layout.addWidget(btn_frame)

        # 循环次数设置
        loop_frame = QFrame()
        hbox = QHBoxLayout(loop_frame)
        loop_label = QLabel("循环次数 (0=无限):")
        self.loop_entry = QLineEdit("1")
        self.loop_entry.setFixedWidth(100)
        hbox.addWidget(loop_label)
        hbox.addWidget(self.loop_entry)
        hbox.addStretch()
        layout.addWidget(loop_frame)

    def sync_automation_steps_order(self):
        """精确同步步骤顺序"""
        try:
            valid_items = [
                (self.steps_table.topLevelItem(i), i)
                for i in range(self.steps_table.topLevelItemCount())
                if self.steps_table.topLevelItem(i) is not None
            ]

            new_steps = []
            for idx, (item, _) in enumerate(valid_items, 1):
                if not item:
                    continue
                step_data = item.data(0, Qt.UserRole)
                if step_data:
                    new_steps.append(step_data)
                    item.setText(0, str(idx))

            self.automation_steps.clear()
            self.automation_steps.extend(new_steps)

            self.steps_table.clear()
            for step in self.automation_steps:
                self._add_step_to_table(step)

            self.log("步骤顺序已调整")
        except Exception as e:
            self.log(f"同步步骤顺序失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"同步步骤顺序失败: {str(e)}")

    def _add_step_to_table(self, step):
        """安全的表格项添加方法"""
        try:
            current_count = self.steps_table.topLevelItemCount()
            idx = current_count + 1

            params_desc = []
            for motor in ["X", "Y", "Z", "A"]:
                cfg = step.get(motor, {})
                if cfg.get("enable") == "E":
                    desc = f"{motor}:方向{cfg.get('direction', '?')} 速度{cfg.get('speed', '?')} 角度{cfg.get('angle', '?')}"
                    params_desc.append(desc)

            # 添加进样泵信息
            pump_cfg = step.get("pump", {})
            if pump_cfg.get("enable", False):
                params_desc.append(f"进样泵:{pump_cfg.get('speed', 0)}%")

            params_str = " | ".join(params_desc) if params_desc else "所有微泵脱机"
            interval_ms = step.get("interval", 0)
            name = step.get("name", f"步骤 {idx}")

            item = QTreeWidgetItem([str(idx), name, params_str, f"{interval_ms / 1000.0:.1f}"])
            item.setData(0, Qt.UserRole, step)

            for i in range(self.steps_table.columnCount()):
                item.setTextAlignment(i, Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)

            self.steps_table.addTopLevelItem(item)

        except Exception as e:
            self.log(f"步骤添加错误: {str(e)}")

    def edit_step(self, item, column):
        step_index = self.steps_table.indexOfTopLevelItem(item)
        if step_index >= 0 and step_index < len(self.automation_steps):
            step = self.automation_steps[step_index]
            config_window = MotorStepConfig(self, step_index + 1, step)
            if config_window.exec() == QDialog.DialogCode.Accepted:
                self.automation_steps[step_index] = config_window.step_params
                self.update_steps_table()
                self.log(f"步骤 {step_index + 1} 已编辑")

    def delete_preset(self, preset_type):
        """删除预设的通用方法"""
        if preset_type == "manual":
            combo = self.manual_preset_combo
        else:
            combo = self.auto_preset_combo

        name = combo.currentText()
        if not name:
            return

        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除预设 '{name}' 吗？", QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._preset_manager.delete_preset(preset_type, name)
            self.update_preset_combos()
            self.log(f"预设 '{name}' 已删除")

    def copy_step(self):
        selected = self.steps_table.selectedItems()
        if not selected:
            return
        item = selected[0]
        step_index = self.steps_table.indexOfTopLevelItem(item)
        if step_index >= 0 and step_index < len(self.automation_steps):
            self.copied_step = self.automation_steps[step_index].copy()
            self.log("步骤已复制")

    def paste_step(self):
        if not self.copied_step:
            QMessageBox.warning(self, "警告", "没有复制的步骤")
            return

        new_step = self.copied_step.copy()
        new_step["name"] = f"步骤 {len(self.automation_steps) + 1} (副本)"
        self.automation_steps.append(new_step)
        self._add_step_to_table(new_step)
        self.log("步骤已粘贴")

    def add_step(self):
        step_num = len(self.automation_steps) + 1
        config_window = MotorStepConfig(self, step_num)
        if config_window.exec() == QDialog.DialogCode.Accepted:
            self.automation_steps.append(config_window.step_params)
            self._add_step_to_table(config_window.step_params)
            self.log(f"步骤 {step_num} 已添加")

    def remove_step(self):
        selected = self.steps_table.selectedItems()
        if not selected:
            return
        item = selected[0]
        idx = self.steps_table.indexOfTopLevelItem(item)
        if idx >= 0 and idx < len(self.automation_steps):
            del self.automation_steps[idx]
            self.update_steps_table()
            self.log(f"步骤 {idx + 1} 已删除")

    def start_automation(self):
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        if not self.automation_steps:
            QMessageBox.warning(self, "警告", "请先添加自动化步骤")
            return

        try:
            loop_count = int(self.loop_entry.text())
        except:
            loop_count = 1
        self.loop_count = loop_count

        self.running_mode = "auto"
        self.is_first_command = True

        # 创建自动化线程
        self.automation_thread = AutomationThread(
            parent_ref=weakref.ref(self),
            steps=self.automation_steps,
            loop_count=loop_count,
            serial_port=self.serial_port,
            serial_lock=self.serial_lock,
        )

        # 设置 PID 模式
        self.automation_thread.set_pid_mode(self.auto_calibration_enabled)

        self.automation_thread.update_status.connect(self.log)
        self.automation_thread.error_occurred.connect(self.handle_automation_error)
        self.automation_thread.finished.connect(self._on_automation_finished)

        self.automation_thread.start()
        self.log("自动化流程已启动")
        self.status_bar.showMessage("自动化运行中...")

    def _on_automation_finished(self):
        self.log("自动化流程已完成")
        self.status_bar.showMessage("自动化已完成")
        QTimer.singleShot(500, self._cleanup_automation_thread)

    def _cleanup_automation_thread(self):
        """延迟清理自动化线程"""
        if self.automation_thread:
            if self.automation_thread.isRunning():
                self.automation_thread.stop()
                self.automation_thread.wait(1000)
            try:
                self.automation_thread.update_status.disconnect()
                self.automation_thread.error_occurred.disconnect()
                self.automation_thread.finished.disconnect()
            except:
                pass
            self.automation_thread = None

    def handle_automation_error(self, message):
        QTimer.singleShot(0, lambda: self._handle_automation_error_delayed(message))

    def _handle_automation_error_delayed(self, message):
        """延迟处理自动化错误"""
        self.log(f"自动化错误: {message}")
        QMessageBox.warning(self, "自动化错误", message)

    def stop_automation(self):
        if not self.automation_thread:
            return

        try:
            self.automation_thread.stop()

            if self.automation_thread.isRunning():
                self.automation_thread.wait(2000)

            if self.automation_thread.isRunning():
                self.automation_thread.terminate()
                self.automation_thread.wait(500)

            try:
                self.automation_thread.update_status.disconnect()
                self.automation_thread.error_occurred.disconnect()
                self.automation_thread.finished.disconnect()
            except:
                pass

            self.automation_thread = None
            self.running = False
            self.running_mode = "manual"

            # 发送停止指令
            if self.serial_port and self.serial_port.is_open:
                stop_cmd = "XDFV0J0YDFV0J0ZDFV0J0ADFV0J0\r\n"
                with self.serial_lock:
                    self.serial_port.write(stop_cmd.encode())

            self.log("自动化流程已停止")
            self.status_bar.showMessage("自动化已停止")
        except Exception as e:
            self.log(f"停止自动化时出错: {e}")

    def update_steps_table(self):
        self.steps_table.clear()
        for step in self.automation_steps:
            self._add_step_to_table(step)

    def _update_step_item(self, item, step, idx):
        params_desc = []
        for motor in ["X", "Y", "Z", "A"]:
            cfg = step.get(motor, {})
            if cfg.get("enable") == "E":
                desc = f"{motor}:{cfg.get('direction', '?')}{cfg.get('speed', '?')}°"
                params_desc.append(desc)

        # 添加进样泵信息
        pump_cfg = step.get("pump", {})
        if pump_cfg.get("enable", False):
            params_desc.append(f"进样泵:{pump_cfg.get('speed', 0)}%")

        item.setText(0, str(idx))
        item.setText(1, step.get("name", f"步骤 {idx}"))
        item.setText(2, " | ".join(params_desc) if params_desc else "所有微泵脱机")
        item.setText(3, f"{step.get('interval', 0) / 1000.0:.1f}")
        item.setData(0, Qt.UserRole, step)

    def save_auto_preset(self):
        name, ok = QInputDialog.getText(self, "保存预设", "请输入预设名称:")
        if not ok or not name:
            return

        try:
            loop_count = int(self.loop_entry.text())
        except:
            loop_count = 1
        self.loop_count = loop_count
        self._preset_manager.save_auto_preset(name, self.automation_steps, loop_count)
        self.update_preset_combos()
        self.log(f"自动预设 '{name}' 已保存")

    def load_auto_preset(self):
        name = self.auto_preset_combo.currentText()
        if not name:
            return

        preset_data = self._preset_manager.load_auto_preset(name)
        if preset_data:
            self.automation_steps = preset_data.get("steps", [])
            self.loop_count = preset_data.get("loop_count", 1)
            if hasattr(self, "loop_entry"):
                self.loop_entry.setText(str(self.loop_count))
            self.update_steps_table()
            self.log(f"自动预设 '{name}' 已加载")

    def _notify_automation_pid_complete(self, motor: str) -> None:
        """
        通知自动化线程 PID 完成

        Args:
            motor: 完成的电机名称
        """
        try:
            if self.automation_thread and self.automation_thread.isRunning():
                self.automation_thread.notify_pid_complete(motor)
        except Exception:
            pass
