"""可拖拽排序的树形控件"""
from PySide6.QtWidgets import QTreeWidget
from PySide6.QtCore import Qt


class DragDropTreeWidget(QTreeWidget):
    """支持拖拽排序的树形控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setExpandsOnDoubleClick(False)
        self.setDragDropOverwriteMode(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
    
    def dropEvent(self, event):
        """重写drop事件精确控制项目移动"""
        dragged_item = self.currentItem()
        if not dragged_item:
            return
        
        # 获取目标位置
        drop_pos = event.position().toPoint()
        target_item = self.itemAt(drop_pos)
        
        # 计算插入位置
        new_index = self.indexAt(drop_pos).row()
        new_index = max(0, new_index) if new_index != -1 else self.topLevelItemCount()
        
        # 执行移动逻辑
        if dragged_item.parent() is None:
            source_index = self.indexOfTopLevelItem(dragged_item)
            item = self.takeTopLevelItem(source_index)
            
            if new_index >= self.topLevelItemCount():
                self.addTopLevelItem(item)
            else:
                self.insertTopLevelItem(new_index, item)
            
            self.setCurrentItem(item)
        
        # 通知父窗口同步步骤顺序
        parent_window = self.window()
        if hasattr(parent_window, 'sync_automation_steps_order'):
            parent_window.sync_automation_steps_order()
        
        event.accept()

