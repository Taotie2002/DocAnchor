"""校验审计日志（3.4.3.3 校验底线）。

记录所有文字修正、结构调整的操作日志，保证可溯源。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docanchor.common.logger import get_logger

logger = get_logger("text_verify.audit")


class AuditLogger:
    """审计日志记录器。"""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path
        self._entries: list[dict[str, Any]] = []

    def record(
        self,
        *,
        action: str,
        node_id: str,
        before: Any = None,
        after: Any = None,
        source: str = "auto",
        reason: str = "",
    ) -> None:
        """记录一条审计日志。"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "action": action,
            "node_id": node_id,
            "before": before,
            "after": after,
            "source": source,  # auto | llm | manual
            "reason": reason,
        }
        self._entries.append(entry)
        logger.info(f"审计: {action} node={node_id} source={source}")

    def save(self) -> None:
        """保存审计日志到文件（如果指定了log_path）。"""
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)


__all__ = ["AuditLogger"]