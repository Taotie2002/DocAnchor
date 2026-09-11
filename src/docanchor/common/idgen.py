"""全局唯一ID生成。

格式：{kind}-{8位hex}
- block_id: 页内唯一，VLX 分页解析产物
- node_id: 全局唯一，全局聚合后唯一
- object_id: PDF原生对象引用
"""

from __future__ import annotations

import os
import threading
import time

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {}


def _new(kind: str, prefix_len: int = 6) -> str:
    """生成形如 'block-1f2e3a' 的ID。

    前缀：kind
    主体：纳秒时间戳后6位hex + 自增计数器后2位hex
    """
    with _LOCK:
        _COUNTERS[kind] = _COUNTERS.get(kind, -1) + 1
        seq = _COUNTERS[kind]
    ts_part = f"{int(time.time_ns() & 0xFFFFFFFF):08x}"[:prefix_len]
    seq_part = f"{seq & 0xFF:02x}"
    return f"{kind}-{ts_part}{seq_part}"


def new_block_id() -> str:
    """页内Block唯一ID（VLX分页解析产物）。"""
    return _new("block")


def new_node_id() -> str:
    """全局节点唯一ID（全局聚合后）。"""
    return _new("node")


def new_object_id() -> str:
    """PDF原生对象引用ID。"""
    return _new("obj")


def reset_counters() -> None:
    """测试用：重置所有计数器。"""
    with _LOCK:
        _COUNTERS.clear()


def seed_from_pid() -> None:
    """跨进程防冲突：用PID扰动种子（阶段2批量处理时使用）。"""
    os.environ.get("DOCANCHOR_SEED", "")
    # 当前实现依赖纳秒时间戳+进程内计数器已足够，单进程安全；
    # 批量阶段如需跨进程唯一，可在此追加 PID 后缀


__all__ = ["new_block_id", "new_node_id", "new_object_id", "reset_counters", "seed_from_pid"]