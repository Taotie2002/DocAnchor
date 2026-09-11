"""OpenAI 兼容 API Provider。

适用于内网部署的Qwen/DeepSeek等兼容OpenAI Chat Completions的服务。
"""

from __future__ import annotations

import time
from typing import Any

from docanchor.common.errors import LLMCallError
from docanchor.common.logger import get_logger

logger = get_logger("llm.openai_compat")


class OpenAICompatProvider:
    """OpenAI Chat Completions 兼容协议Provider。"""

    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float | None = None):
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # 优先使用传入的timeout，否则从环境变量读取，再否则用默认值
        if timeout is None:
            import os
            timeout = float(os.environ.get("DOCANCHOR_LLM_TIMEOUT", "120"))
        self.timeout = timeout
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as e:
                raise LLMCallError(
                    "openai SDK未安装",
                    task="init",
                    attempts=0,
                ) from e
            self._client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        """调用chat completions接口，返回模型输出的文本内容。

        Args:
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            temperature: 采样温度。
            max_tokens: 最大输出token数。

        Returns:
            模型输出的纯文本（通常是JSON字符串，由调用方解析校验）。

        Raises:
            LLMCallError: 调用失败。
        """
        client = self._ensure_client()
        start = time.time()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            elapsed = time.time() - start
            logger.error(f"LLM调用失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
            raise LLMCallError(
                f"OpenAI兼容API调用失败: {e}",
                task="chat",
                attempts=1,
            ) from e

        elapsed = time.time() - start
        if not response.choices:
            raise LLMCallError("LLM返回choices为空", task="chat")

        content = response.choices[0].message.content or ""
        logger.info(
            f"LLM调用成功 ({elapsed:.1f}s, "
            f"in={response.usage.prompt_tokens if response.usage else '?'}, "
            f"out={response.usage.completion_tokens if response.usage else '?'})"
        )
        return content

    def version(self) -> str:
        return f"openai_compat:{self.model}"


__all__ = ["OpenAICompatProvider"]