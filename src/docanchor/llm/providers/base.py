"""LLM Provider基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """LLM Provider 接口契约。"""

    name: str = "base"

    @abstractmethod
    def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        """返回模型输出的原始文本。"""
        raise NotImplementedError

    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError


__all__ = ["BaseLLMProvider"]