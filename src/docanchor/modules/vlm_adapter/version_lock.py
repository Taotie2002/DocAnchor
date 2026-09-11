"""版本锁定（3.2.2.5）：固定MinerU管线版本、配置哈希。"""

from __future__ import annotations


def current_version() -> str:
    """返回当前Provider的版本标识。"""
    return "mock-0.1.0"


def config_hash(config: dict) -> str:
    """计算配置的稳定哈希。"""
    from docanchor.common.hash import dict_hash

    return dict_hash(config)


__all__ = ["current_version", "config_hash"]