"""统一日志：控制台+文件，结构化JSON格式。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DEFAULT_LEVEL = logging.INFO


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class _JsonFormatter(logging.Formatter):
    """结构化JSON日志，便于阶段2以后聚合分析。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _now_iso(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # 自定义字段通过logger.info("msg", extra={"k": "v"})传入
        for k, v in record.__dict__.items():
            if k in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "taskName",
            ):
                continue
            payload[k] = v
        return json.dumps(payload, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    """人类可读的文本格式（默认）。"""

    def __init__(self) -> None:
        super().__init__(_LOG_FORMAT)


_configured = False


def setup_logging(
    level: int = _DEFAULT_LEVEL,
    log_file: Path | None = None,
    json_format: bool = False,
) -> None:
    """初始化根日志配置。可重复调用（仅首次生效）。

    Args:
        level: 日志级别，默认 INFO。
        log_file: 可选，额外输出到文件。
        json_format: True 时输出 JSON 行（默认人类可读）。
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger("docanchor")
    root.setLevel(level)
    root.propagate = False  # 避免与根logger重复输出

    # 关闭fitz/pymupdf的deprecation warning噪音
    logging.getLogger("pymupdf").setLevel(logging.ERROR)
    logging.getLogger("fitz").setLevel(logging.ERROR)

    formatter: logging.Formatter = _JsonFormatter() if json_format else _TextFormatter()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取命名logger。自动初始化（首次调用）。"""
    if not _configured:
        setup_logging()
    return logging.getLogger(f"docanchor.{name}")


__all__ = ["get_logger", "setup_logging"]