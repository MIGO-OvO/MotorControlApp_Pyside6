"""
数据处理工具
负责数据导入导出
"""
import csv
from typing import Dict, List, Optional
from datetime import datetime
from ..config.constants import LOG_DATE_FORMAT


class DataHandler:
    """数据处理工具类"""
    
    @staticmethod
    def export_to_csv(
        data: List[Dict],
        filepath: str,
        fieldnames: Optional[List[str]] = None
    ) -> bool:
        """
        导出数据到CSV文件
        
        Args:
            data: 数据列表
            filepath: 文件路径
            fieldnames: 字段名列表
            
        Returns:
            是否成功
        """
        if not data:
            return False
        
        try:
            if fieldnames is None:
                fieldnames = list(data[0].keys())
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            return True
        except Exception as e:
            print(f"导出CSV错误: {e}")
            return False
    
    @staticmethod
    def generate_filename(prefix: str, extension: str = "csv") -> str:
        """
        生成带时间戳的文件名
        
        Args:
            prefix: 文件名前缀
            extension: 文件扩展名
            
        Returns:
            文件名
        """
        timestamp = datetime.now().strftime(LOG_DATE_FORMAT)
        return f"{prefix}_{timestamp}.{extension}"

