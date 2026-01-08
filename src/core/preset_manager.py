"""
预设管理器
负责手动控制和自动化流程预设的管理
"""

import json
import os
from typing import Any, Dict, List, Optional

from ..config.constants import PRESETS_FILE


class PresetManager:
    """预设管理器"""

    def __init__(self, presets_file: str = PRESETS_FILE):
        """
        初始化预设管理器

        Args:
            presets_file: 预设文件路径
        """
        self.presets_file = presets_file
        self.presets: Dict[str, Any] = {}
        self._ensure_data_directory()
        self.load_all()

    def _ensure_data_directory(self) -> None:
        """确保data目录存在"""
        directory = os.path.dirname(self.presets_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def load_all(self) -> Dict[str, Any]:
        """
        从文件加载所有预设

        Returns:
            预设字典
        """
        if not os.path.exists(self.presets_file):
            return {}

        try:
            with open(self.presets_file, "r", encoding="utf-8") as f:
                self.presets = json.load(f)
            return self.presets
        except Exception as e:
            print(f"加载预设文件错误: {str(e)}")
            return {}

    def save_all(self) -> bool:
        """
        保存所有预设到文件

        Returns:
            是否保存成功
        """
        try:
            self._ensure_data_directory()
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存预设文件错误: {str(e)}")
            return False

    def save_manual_preset(self, name: str, params: Dict[str, Any]) -> bool:
        """
        保存手动控制预设

        Args:
            name: 预设名称
            params: 参数字典

        Returns:
            是否保存成功
        """
        preset_key = f"manual_{name}"
        self.presets[preset_key] = params
        return self.save_all()

    def load_manual_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """
        加载手动控制预设

        Args:
            name: 预设名称

        Returns:
            参数字典，如果不存在返回None
        """
        preset_key = f"manual_{name}"
        return self.presets.get(preset_key)

    def save_auto_preset(self, name: str, steps: List[Dict], loop_count: int) -> bool:
        """
        保存自动化流程预设

        Args:
            name: 预设名称
            steps: 步骤列表
            loop_count: 循环次数

        Returns:
            是否保存成功
        """
        preset_key = f"auto_{name}"
        self.presets[preset_key] = {"steps": [s.copy() for s in steps], "loop_count": loop_count}
        return self.save_all()

    def load_auto_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """
        加载自动化流程预设

        Args:
            name: 预设名称

        Returns:
            包含steps和loop_count的字典，如果不存在返回None
        """
        preset_key = f"auto_{name}"
        return self.presets.get(preset_key)

    def delete_preset(self, preset_type: str, name: str) -> bool:
        """
        删除预设

        Args:
            preset_type: 预设类型 ("manual" 或 "auto")
            name: 预设名称

        Returns:
            是否删除成功
        """
        preset_key = f"{preset_type}_{name}"
        if preset_key in self.presets:
            del self.presets[preset_key]
            return self.save_all()
        return False

    def get_manual_preset_names(self) -> List[str]:
        """
        获取所有手动控制预设名称

        Returns:
            预设名称列表
        """
        return sorted(
            [
                key[7:]  # 移除 "manual_" 前缀
                for key in self.presets.keys()
                if key.startswith("manual_")
            ]
        )

    def get_auto_preset_names(self) -> List[str]:
        """
        获取所有自动化流程预设名称

        Returns:
            预设名称列表
        """
        return sorted(
            [key[5:] for key in self.presets.keys() if key.startswith("auto_")]  # 移除 "auto_" 前缀
        )

    def preset_exists(self, preset_type: str, name: str) -> bool:
        """
        检查预设是否存在

        Args:
            preset_type: 预设类型 ("manual" 或 "auto")
            name: 预设名称

        Returns:
            是否存在
        """
        preset_key = f"{preset_type}_{name}"
        return preset_key in self.presets

    def clear_all_presets(self) -> bool:
        """
        清空所有预设

        Returns:
            是否成功
        """
        self.presets = {}
        return self.save_all()
