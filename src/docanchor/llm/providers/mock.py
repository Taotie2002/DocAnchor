"""Mock LLM Provider。"""

from __future__ import annotations


class MockLLMProvider:
    """Mock实现：返回固定JSON，供开发与测试阶段。"""

    name = "mock"

    def chat(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0, max_tokens: int = 2048) -> str:
        return "{}"

    def version(self) -> str:
        return "mock-0.1.0"


__all__ = ["MockLLMProvider"]