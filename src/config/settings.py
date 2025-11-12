"""
设置管理器
负责应用程序设置的加载、保存和管理
"""
import json
import os
from typing import Dict, Any, Optional
from .constants import SETTINGS_FILE


class SettingsManager:
    """应用程序设置管理器"""
    
    def __init__(self, settings_file: str = SETTINGS_FILE):
        """
        初始化设置管理器
        
        Args:
            settings_file: 设置文件路径
        """
        self.settings_file = settings_file
        self._settings: Dict[str, Any] = {}
        self._ensure_data_directory()
    
    def _ensure_data_directory(self) -> None:
        """确保data目录存在"""
        directory = os.path.dirname(self.settings_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
    
    def load(self) -> Dict[str, Any]:
        """
        从文件加载设置
        
        Returns:
            设置字典
        """
        if not os.path.exists(self.settings_file):
            return {}
        
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                self._settings = json.load(f)
            return self._settings
        except Exception as e:
            print(f"加载设置文件错误: {str(e)}")
            return {}
    
    def save(self, settings: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存设置到文件
        
        Args:
            settings: 要保存的设置字典，如果为None则保存当前设置
            
        Returns:
            是否保存成功
        """
        if settings is not None:
            self._settings = settings
        
        try:
            self._ensure_data_directory()
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存设置文件错误: {str(e)}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取设置项
        
        Args:
            key: 设置键（支持点号分隔的嵌套键，如"serial.port"）
            default: 默认值
            
        Returns:
            设置值
        """
        keys = key.split('.')
        value = self._settings
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 设置键（支持点号分隔的嵌套键）
            value: 设置值
        """
        keys = key.split('.')
        current = self._settings
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置节
        
        Args:
            section: 节名称
            
        Returns:
            配置节字典
        """
        return self._settings.get(section, {})
    
    def set_section(self, section: str, data: Dict[str, Any]) -> None:
        """
        设置配置节
        
        Args:
            section: 节名称
            data: 配置数据
        """
        self._settings[section] = data
    
    @property
    def all_settings(self) -> Dict[str, Any]:
        """获取所有设置"""
        return self._settings.copy()
    
    def clear(self) -> None:
        """清空所有设置"""
        self._settings = {}
    
    def delete_setting(self, key: str) -> bool:
        """
        删除设置项
        
        Args:
            key: 设置键
            
        Returns:
            是否删除成功
        """
        keys = key.split('.')
        current = self._settings
        
        try:
            for k in keys[:-1]:
                current = current[k]
            
            if keys[-1] in current:
                del current[keys[-1]]
                return True
            return False
        except (KeyError, TypeError):
            return False

