"""VLM Provider 基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from docanchor.common.schema import Block


class BaseVLMProvider(ABC):
    """VLM Provider 接口契约。"""

    name: str = "base"

    @abstractmethod
    def parse(self, pdf_path: Path) -> list[list[Block]]:
        """解析PDF，按页返回Block数组。"""
        raise NotImplementedError

    @abstractmethod
    def version(self) -> str:
        """返回Provider版本标识。"""
        raise NotImplementedError


__all__ = ["BaseVLMProvider"]