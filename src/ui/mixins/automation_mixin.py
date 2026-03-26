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
from PySide6.QtGui import QFont, QKeySequence, QShortcut
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
    QSpinBox,
    QTreeWidgetItem,
    QVBoxLayout,
)

from src.config.constants import BUTTON_SECONDARY, BUTTON_TERTIARY, BUTTON_DANGER, BUTTON_SUCCESS
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

        # 预设管理 - H6: 加载/保存为Secondary，删除为Tertiary
        preset_frame = QFrame()
        hbox = QHBoxLayout(preset_frame)

        self.auto_preset_combo = QComboBox()
        self.auto_preset_combo.setFont(QFont("Microsoft YaHei", 16))
        self.auto_preset_combo.setMinimumWidth(150)

        load_btn = QPushButton("加载")
        load_btn.setStyleSheet(BUTTON_SECONDARY)
        load_btn.clicked.connect(self.load_auto_preset)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(BUTTON_SECONDARY)
        save_btn.clicked.connect(self.save_auto_preset)
        del_auto_btn = QPushButton("删除")
        del_auto_btn.setStyleSheet(BUTTON_TERTIARY)
        del_auto_btn.clicked.connect(lambda: self.delete_preset("auto"))

        hbox.addWidget(QLabel("自动预设:"))
        hbox.addWidget(self.auto_preset_combo)
        hbox.addWidget(load_btn)
        hbox.addWidget(save_btn)
        hbox.addWidget(del_auto_btn)
        hbox.addStretch()
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
        # H3: 使用弹性列宽而非固定宽度
        self.steps_table.header().setStretchLastSection(True)
        self.steps_table.setColumnWidth(0, 60)
        self.steps_table.setColumnWidth(1, 120)
        self.steps_table.setColumnWidth(3, 80)
        self.steps_table.itemDoubleClicked.connect(self.edit_step)
        self.steps_table.itemActivated.connect(self.edit_step)
        QShortcut(QKeySequence.StandardKey.InsertParagraphSeparator, self.steps_table, self.edit_selected_step)
        QShortcut(QKeySequence(Qt.Key_F2), self.steps_table, self.edit_selected_step)
        layout.addWidget(self.steps_table)

        # H5: 空状态提示
        self._auto_empty_hint = QLabel(
            "📋 尚无自动化步骤\n\n"
            "点击「添加步骤」配置微泵参数，\n"
            "可拖拽步骤调整执行顺序，双击编辑参数。"
        )
        self._auto_empty_hint.setAlignment(Qt.AlignCenter)
        self._auto_empty_hint.setStyleSheet(
            "color: #888; font-size: 14px; padding: 40px; border: 2px dashed #ddd; border-radius: 12px;"
        )
        layout.addWidget(self._auto_empty_hint)

        # 控制按钮 - H6/H5: 按钮层级分化 + 上移/下移
        btn_frame = QFrame()
        hbox = QHBoxLayout(btn_frame)

        add_btn = QPushButton("添加步骤")
        add_btn.clicked.connect(self.add_step)

        remove_btn = QPushButton("删除步骤")
        remove_btn.setStyleSheet(BUTTON_TERTIARY)
        remove_btn.clicked.connect(self.remove_step)

        self.edit_step_btn = QPushButton("编辑步骤")
        self.edit_step_btn.setStyleSheet(BUTTON_SECONDARY)
        self.edit_step_btn.setToolTip("编辑当前选中的步骤（Enter / F2）")
        self.edit_step_btn.clicked.connect(self.edit_selected_step)

        copy_btn = QPushButton("复制")
        copy_btn.setStyleSheet(BUTTON_TERTIARY)
        copy_btn.clicked.connect(self.copy_step)

        paste_btn = QPushButton("粘贴")
        paste_btn.setStyleSheet(BUTTON_TERTIARY)
        paste_btn.clicked.connect(self.paste_step)

        # H5: 上移/下移按钮 (键盘友好的步骤重排)
        move_up_btn = QPushButton("上移")
        move_up_btn.setStyleSheet(BUTTON_SECONDARY)
        move_up_btn.setToolTip("将选中步骤上移一位")
        move_up_btn.clicked.connect(self._move_step_up)

        move_down_btn = QPushButton("下移")
        move_down_btn.setStyleSheet(BUTTON_SECONDARY)
        move_down_btn.setToolTip("将选中步骤下移一位")
        move_down_btn.clicked.connect(self._move_step_down)

        for btn in [add_btn, self.edit_step_btn, remove_btn, copy_btn, paste_btn, move_up_btn, move_down_btn]:
            btn.setFont(QFont("Microsoft YaHei", 14))
            btn.setFixedHeight(36)
            hbox.addWidget(btn)
        layout.addWidget(btn_frame)

        # 执行区域 - H5: 循环次数和执行放在一起
        exec_frame = QFrame()
        exec_layout = QHBoxLayout(exec_frame)

        # H5: 循环次数改用 QSpinBox
        loop_label = QLabel("循环次数:")
        self.loop_entry = QSpinBox()
        self.loop_entry.setRange(0, 9999)
        self.loop_entry.setValue(1)
        self.loop_entry.setSpecialValueText("无限")
        self.loop_entry.setToolTip("0 = 无限循环")
        self.loop_entry.setFixedWidth(100)

        self.start_auto_btn = QPushButton("开始执行")
        self.start_auto_btn.setStyleSheet(BUTTON_SUCCESS)
        self.start_auto_btn.setFont(QFont("Microsoft YaHei", 16))
        self.start_auto_btn.setFixedHeight(40)
        self.start_auto_btn.clicked.connect(self.start_automation)

        self.stop_auto_btn = QPushButton("停止执行")
        self.stop_auto_btn.setStyleSheet(BUTTON_DANGER)
        self.stop_auto_btn.setFont(QFont("Microsoft YaHei", 16))
        self.stop_auto_btn.setFixedHeight(40)
        self.stop_auto_btn.setEnabled(False)
        self.stop_auto_btn.clicked.connect(self.stop_automation)

        exec_layout.addWidget(loop_label)
        exec_layout.addWidget(self.loop_entry)
        exec_layout.addStretch()
        exec_layout.addWidget(self.start_auto_btn)
        exec_layout.addWidget(self.stop_auto_btn)
        layout.addWidget(exec_frame)

        self.refresh_automation_view_state()

    def refresh_automation_view_state(self):
        """统一刷新步骤列表与空状态提示。"""
        if not hasattr(self, "steps_table"):
            return

        self.steps_table.clear()
        for step in self.automation_steps:
            self._add_step_to_table(step)

        has_steps = len(self.automation_steps) > 0
        if hasattr(self, "_auto_empty_hint"):
            self._auto_empty_hint.setVisible(not has_steps)
        self.steps_table.setVisible(has_steps)

    def _set_automation_running_state(self, is_running: bool):
        """统一管理自动化执行态按钮与可编辑控件状态。"""
        if hasattr(self, "start_auto_btn"):
            self.start_auto_btn.setEnabled(not is_running)
        if hasattr(self, "stop_auto_btn"):
            self.stop_auto_btn.setEnabled(is_running)
        if hasattr(self, "loop_entry"):
            self.loop_entry.setEnabled(not is_running)
        if hasattr(self, "edit_step_btn"):
            self.edit_step_btn.setEnabled(not is_running)
        if hasattr(self, "steps_table"):
            self.steps_table.setEnabled(not is_running)
        if hasattr(self, "auto_preset_combo"):
            self.auto_preset_combo.setEnabled(not is_running)

    def edit_selected_step(self):
        """编辑当前选中的步骤。"""
        selected = self.steps_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选择一个步骤")
            return
        self.edit_step(selected[0], 0)

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

            self.refresh_automation_view_state()
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
        self.refresh_automation_view_state()
        self.log("步骤已粘贴")

    def add_step(self):
        step_num = len(self.automation_steps) + 1
        config_window = MotorStepConfig(self, step_num)
        if config_window.exec() == QDialog.DialogCode.Accepted:
            self.automation_steps.append(config_window.step_params)
            self.refresh_automation_view_state()
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
        if self.automation_thread and self.automation_thread.isRunning():
            QMessageBox.information(self, "提示", "自动化流程正在运行中")
            return

        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        if not self.automation_steps:
            QMessageBox.warning(self, "警告", "请先添加自动化步骤")
            return

        loop_count = self.loop_entry.value()
        self.loop_count = loop_count

        self.running_mode = "auto"
        self.is_first_command = True
        self._set_automation_running_state(True)

        self.automation_thread = AutomationThread(
            parent_ref=weakref.ref(self),
            steps=self.automation_steps,
            loop_count=loop_count,
            serial_port=self.serial_port,
            serial_lock=self.serial_lock,
        )
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
        self._set_automation_running_state(False)
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
            except Exception:
                pass
            self.automation_thread = None
        self._set_automation_running_state(False)

    def handle_automation_error(self, message):
        QTimer.singleShot(0, lambda: self._handle_automation_error_delayed(message))

    def _handle_automation_error_delayed(self, message):
        """延迟处理自动化错误"""
        self._set_automation_running_state(False)
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
            except Exception:
                pass

            self.automation_thread = None
            self.running = False
            self.running_mode = "manual"
            self._set_automation_running_state(False)

            if self.serial_port and self.serial_port.is_open:
                stop_cmd = "XDFV0J0YDFV0J0ZDFV0J0ADFV0J0\r\n"
                with self.serial_lock:
                    self.serial_port.write(stop_cmd.encode())

            self.log("自动化流程已停止")
            self.status_bar.showMessage("自动化已停止")
        except Exception as e:
            self._set_automation_running_state(False)
            self.log(f"停止自动化时出错: {e}")

    def _move_step_up(self):
        """将选中步骤上移一位"""
        selected = self.steps_table.selectedItems()
        if not selected:
            return
        idx = self.steps_table.indexOfTopLevelItem(selected[0])
        if idx <= 0 or idx >= len(self.automation_steps):
            return
        self.automation_steps[idx], self.automation_steps[idx - 1] = (
            self.automation_steps[idx - 1],
            self.automation_steps[idx],
        )
        self.update_steps_table()
        self.steps_table.setCurrentItem(self.steps_table.topLevelItem(idx - 1))
        self.log(f"步骤 {idx + 1} 已上移")

    def _move_step_down(self):
        """将选中步骤下移一位"""
        selected = self.steps_table.selectedItems()
        if not selected:
            return
        idx = self.steps_table.indexOfTopLevelItem(selected[0])
        if idx < 0 or idx >= len(self.automation_steps) - 1:
            return
        self.automation_steps[idx], self.automation_steps[idx + 1] = (
            self.automation_steps[idx + 1],
            self.automation_steps[idx],
        )
        self.update_steps_table()
        self.steps_table.setCurrentItem(self.steps_table.topLevelItem(idx + 1))
        self.log(f"步骤 {idx + 1} 已下移")

    def update_steps_table(self):
        self.refresh_automation_view_state()

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

        loop_count = self.loop_entry.value()
        self.loop_count = loop_count
        self._preset_manager.save_auto_preset(name, self.automation_steps, loop_count)
        self.update_preset_combos()
        self.log(f"自动预设 '{name}' 已保存")

    def load_auto_preset(self):
        name = self.auto_preset_combo.currentText()
        if not name:
            return

        preset_data = self._preset_manager.load_auto_preset(name)
        if not preset_data:
            return

        self.automation_steps = list(preset_data.get("steps", []))
        try:
            self.loop_count = int(preset_data.get("loop_count", 1))
        except (TypeError, ValueError):
            self.loop_count = 1

        if hasattr(self, "loop_entry"):
            self.loop_entry.setValue(self.loop_count)

        self.refresh_automation_view_state()
        if self.steps_table.topLevelItemCount() > 0:
            self.steps_table.setCurrentItem(self.steps_table.topLevelItem(0))
        self.log(f"自动预设 '{name}' 已加载")
        self.status_bar.showMessage(f"已加载自动预设：{name}", 3000)

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
