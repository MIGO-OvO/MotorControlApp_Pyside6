"""PID优化历史管理器 - 持久化与数据导出"""
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any


class PIDHistoryManager:
    """优化历史持久化管理"""

    SAVE_DIR = Path("data/pid_optimization_history")

    def __init__(self, save_dir: Optional[Path] = None):
        if save_dir:
            self.SAVE_DIR = save_dir
        self.SAVE_DIR.mkdir(parents=True, exist_ok=True)

    def save_session(
        self,
        history: List[Dict],
        best_params: Dict,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """保存优化会话到JSON文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pid_opt_{timestamp}.json"
        filepath = self.SAVE_DIR / filename

        data = {
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "best_params": best_params,
            "metadata": metadata or {},
            "history": history,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return filepath

    def load_session(self, filepath: Path) -> Dict:
        """加载历史会话"""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_sessions(self) -> List[Path]:
        """列出所有历史会话文件"""
        return sorted(self.SAVE_DIR.glob("pid_opt_*.json"), reverse=True)

    def get_session_summary(self, filepath: Path) -> Dict:
        """获取会话摘要（不加载完整历史）"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "filename": filepath.name,
            "created_at": data.get("created_at", ""),
            "best_params": data.get("best_params", {}),
            "iterations": len(data.get("history", [])),
            "best_score": data.get("best_params", {}).get("best_score", 0),
        }

    def export_csv(self, history: List[Dict], filepath: Path) -> None:
        """导出优化历史为CSV格式"""
        if not history:
            return

        fieldnames = [
            "index",
            "Kp",
            "Ki",
            "Kd",
            "avg_score",
            "adjusted_score",
            "max_overshoot",
            "avg_conv_time",
            "convergence_rsd",
            "runs",
        ]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for i, record in enumerate(history):
                row = {"index": i}
                row.update(record)
                writer.writerow(row)

    def delete_session(self, filepath: Path) -> bool:
        """删除会话文件"""
        try:
            filepath.unlink()
            return True
        except Exception:
            return False

    def auto_cleanup(self, max_sessions: int = 50) -> int:
        """自动清理旧会话，保留最近的N个"""
        sessions = self.list_sessions()
        deleted = 0
        if len(sessions) > max_sessions:
            for old_session in sessions[max_sessions:]:
                if self.delete_session(old_session):
                    deleted += 1
        return deleted
