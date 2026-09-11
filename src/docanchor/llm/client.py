"""LLM 统一客户端（3.6）。

调用规则：
- 所有任务固定Prompt模板、固定JSON Schema
- 输出格式校验不通过自动重试2次，重试失败标记待复核
- 温度参数控制：分类/判断/层级类任务温度=0，语义分析≤0.3
- 防幻觉：禁止改写原文，仅做判断/分类/异常标注
- 单篇文档LLM调用次数上限可配置（默认20）

强约束（3.6）：
1. 输入输出强约束
2. 温度参数控制
3. 防幻觉机制
4. 一致性校验（多轮投票）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from docanchor.common.errors import LLMCallError, SchemaValidationError
from docanchor.common.logger import get_logger
from docanchor.config import get_settings
from docanchor.llm.cost_counter import CostCounter
from docanchor.llm.schema_validate import validate_json

logger = get_logger("llm.client")


@dataclass
class LLMResult:
    """单次LLM调用结果。"""

    data: dict[str, Any]
    confidence: float = 1.0
    raw_text: str = ""
    attempts: int = 1
    elapsed: float = 0.0


class LLMClient:
    """小模型统一客户端。"""

    def __init__(
        self,
        provider: Any,
        *,
        cost_counter: CostCounter | None = None,
        budget: int | None = None,
    ):
        self.provider = provider
        self.settings = get_settings()
        self._counter = cost_counter or CostCounter(
            budget=budget if budget is not None else self.settings.llm_call_budget
        )

    @property
    def cost_counter(self) -> CostCounter:
        return self._counter

    def call(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int = 1024,
        max_retries: int = 2,
        needs_schema: bool = True,
    ) -> LLMResult:
        """调用LLM，返回校验后的字典结果。

        Args:
            task: 任务名（用于成本计数与日志）。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            schema: JSON Schema，校验失败自动重试（除非 needs_schema=False）。
            temperature: 温度（None则用配置默认值0）。
            max_tokens: 最大输出token数。
            max_retries: 校验失败重试次数。
            needs_schema: 是否需要Schema校验（False则跳过）。

        Returns:
            LLMResult：包含解析后的data与其他元数据。

        Raises:
            LLMCallError: 调用失败超过重试次数。
            SchemaValidationError: Schema校验失败超过重试次数。
        """
        if self._counter.budget_exceeded():
            raise LLMCallError(
                f"LLM调用预算耗尽 (剩余={self._counter.remaining})",
                task=task,
                attempts=0,
            )

        temp = temperature if temperature is not None else self.settings.llm_temperature_judgment
        last_error: Exception | None = None
        raw_text = ""
        start = time.time()

        for attempt in range(max_retries + 1):
            try:
                raw_text = self.provider.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temp,
                    max_tokens=max_tokens,
                )
            except LLMCallError as e:
                last_error = e
                logger.warning(f"LLM调用失败 (attempt {attempt + 1}): {e}")
                continue

            # 校验
            if not needs_schema or schema is None:
                # 无schema时尝试JSON解析，但不严格
                try:
                    data = json.loads(raw_text)
                    if not isinstance(data, dict):
                        data = {"text": raw_text}
                except json.JSONDecodeError:
                    data = {"text": raw_text}
                self._counter.record(task)
                return LLMResult(
                    data=data,
                    confidence=1.0,
                    raw_text=raw_text,
                    attempts=attempt + 1,
                    elapsed=time.time() - start,
                )

            try:
                data = validate_json(raw_text, schema)
                self._counter.record(task)
                return LLMResult(
                    data=data,
                    confidence=1.0,
                    raw_text=raw_text,
                    attempts=attempt + 1,
                    elapsed=time.time() - start,
                )
            except SchemaValidationError as e:
                last_error = e
                logger.warning(
                    f"Schema校验失败 (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{e}"
                )
                continue

        # 重试耗尽
        if isinstance(last_error, SchemaValidationError):
            raise last_error
        raise LLMCallError(
            f"LLM调用失败: {last_error}",
            task=task,
            attempts=max_retries + 1,
        )

    def call_json_array(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        item_schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int = 2048,
        max_retries: int = 2,
    ) -> LLMResult:
        """调用LLM并期望返回JSON数组。

        Returns:
            LLMResult，data为list类型。
        """
        # 包装array schema
        array_schema = {
            "type": "array",
            "items": item_schema or {"type": "object"},
        }
        return self.call(
            task=task,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=array_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )


def get_default_client() -> LLMClient:
    """根据配置创建默认客户端。"""
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        from docanchor.llm.providers.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    else:
        from docanchor.llm.providers.mock import MockLLMProvider

        provider = MockLLMProvider()
    return LLMClient(provider=provider)


__all__ = ["LLMClient", "LLMResult", "get_default_client"]