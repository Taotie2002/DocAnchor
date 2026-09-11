"""内容哈希：用于幂等校验与全链路可追溯。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def content_hash(text: str) -> str:
    """字符串内容的SHA1前缀（16位hex）。

    Args:
        text: 待哈希字符串。

    Returns:
        16位hex字符串（64bit），用于 content_hash 字段。
    """
    if text is None:
        text = ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def dict_hash(data: dict[str, Any], sort_keys: bool = True) -> str:
    """字典结构的稳定哈希（基于JSON规范化）。

    Args:
        data: 待哈希字典。
        sort_keys: 是否对键排序以保证稳定性。

    Returns:
        16位hex字符串。
    """
    normalized = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=sort_keys,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


__all__ = ["content_hash", "dict_hash"]