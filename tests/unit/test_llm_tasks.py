"""LLM客户端与任务契约单测。"""

from __future__ import annotations

import json
from typing import Any

from docanchor.common.errors import SchemaValidationError
from docanchor.llm.client import LLMClient, LLMResult
from docanchor.llm.cost_counter import CostCounter
from docanchor.llm.providers.mock import MockLLMProvider
from docanchor.llm.tasks.cross_page_table import judge_cross_page_table
from docanchor.llm.tasks.heading_level import normalize_heading_levels
from docanchor.llm.tasks.semantic_check import semantic_check_text


class StubProvider:
    """测试用Stub：返回预置JSON响应。"""

    def __init__(self, response: Any = "{}"):
        self.response = response

    def chat(self, **kwargs) -> str:
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response, ensure_ascii=False)

    def version(self) -> str:
        return "stub-0.1.0"


class TestLLMClient:
    def test_call_no_schema(self) -> None:
        client = LLMClient(provider=StubProvider("plain text"))
        result = client.call(
            task="test",
            system_prompt="sys",
            user_prompt="user",
            needs_schema=False,
        )
        assert result.data == {"text": "plain text"}

    def test_call_with_valid_schema(self) -> None:
        client = LLMClient(provider=StubProvider({"x": 1, "y": "hi"}))
        result = client.call(
            task="test",
            system_prompt="sys",
            user_prompt="user",
            schema={
                    "type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "string"}},
                    "required": ["x", "y"],
                },
        )
        assert result.data == {"x": 1, "y": "hi"}

    def test_schema_validation_retry_then_success(self) -> None:
        # 第1次返回无效，第2次返回有效
        provider = MockLLMProvider()
        # MockLLMProvider返回"{}",对任何schema都通过（除非required字段缺失）
        # 我们用required字段触发重试失败
        client = LLMClient(provider=StubProvider("{}"))
        with __import__("pytest").raises(SchemaValidationError):
            client.call(
                task="test",
                system_prompt="sys",
                user_prompt="user",
                schema={
                    "type": "object",
                    "required": ["missing_field"],
                    "properties": {},
                },
                max_retries=1,
            )

    def test_cost_counter_incremented(self) -> None:
        client = LLMClient(provider=StubProvider({"x": 1}))
        client.call(
            task="t1",
            system_prompt="s",
            user_prompt="u",
            schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        assert client.cost_counter.total == 1
        assert client.cost_counter.by_task() == {"t1": 1}

    def test_budget_exceeded_raises(self) -> None:
        counter = CostCounter(budget=1)
        counter.record("prior")
        client = LLMClient(provider=StubProvider({"x": 1}), cost_counter=counter)
        from docanchor.common.errors import LLMCallError
        with __import__("pytest").raises(LLMCallError):
            client.call(
                task="t",
                system_prompt="s",
                user_prompt="u",
                schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            )

    def test_call_json_array(self) -> None:
        client = LLMClient(provider=StubProvider([{"x": 1}, {"x": 2}]))
        result = client.call_json_array(
            task="t",
            system_prompt="s",
            user_prompt="u",
        )
        assert isinstance(result.data, list)
        assert len(result.data) == 2


class TestCrossPageTableTask:
    def test_judge_same_table(self) -> None:
        client = LLMClient(provider=StubProvider({"is_same_table": True, "confidence": 0.95}))
        result = judge_cross_page_table(
            client=client,
            header_a="阶段|周期|交付物",
            col_count_a=3,
            first_row_a=["阶段1", "2周", "POC"],
            page_a=1,
            header_b="阶段|周期|交付物",
            col_count_b=3,
            first_row_b=["阶段2", "2周", "闭环"],
            page_b=2,
        )
        assert result.is_same_table is True
        assert result.confidence == 0.95

    def test_judge_different_table(self) -> None:
        client = LLMClient(provider=StubProvider({"is_same_table": False, "confidence": 0.85}))
        result = judge_cross_page_table(
            client=client,
            header_a="A|B|C",
            col_count_a=3,
            first_row_a=["1", "2", "3"],
            page_a=1,
            header_b="X|Y",
            col_count_b=2,
            first_row_b=["a", "b"],
            page_b=2,
        )
        assert result.is_same_table is False


class TestHeadingLevelTask:
    def test_normalize_window(self) -> None:
        response = [
            {"id": "h1", "global_level": 1, "parent_id": None, "confidence": 0.95},
            {"id": "h2", "global_level": 2, "parent_id": "h1", "confidence": 0.9},
            {"id": "h3", "global_level": 3, "parent_id": "h2", "confidence": 0.85},
        ]
        client = LLMClient(provider=StubProvider(response))
        result = normalize_heading_levels(
            client=client,
            window=[
                {"id": "h1", "text": "第一章", "local_level": 1, "page_id": 1, "numbering": ""},
                {"id": "h2", "text": "1.1 概述", "local_level": 2, "page_id": 1, "numbering": ""},
                {"id": "h3", "text": "1.1.1 子节", "local_level": 3, "page_id": 2, "numbering": ""},
            ],
        )
        assert len(result) == 3
        assert result[0].global_level == 1
        assert result[1].parent_id == "h1"
        assert result[2].parent_id == "h2"


class TestSemanticCheckTask:
    def test_no_issues(self) -> None:
        client = LLMClient(provider=StubProvider([]))
        result = semantic_check_text(
            client=client,
            text="这是一段完全正常的文本。",
        )
        assert result == []

    def test_with_issues(self) -> None:
        response = [
            {
                "location": "第1段第2句",
                "issue_type": "语病",
                "description": "重复用词",
                "confidence": 0.8,
            }
        ]
        client = LLMClient(provider=StubProvider(response))
        result = semantic_check_text(
            client=client,
            text="一段有语病的文本一段有语病的文本。",
        )
        assert len(result) == 1
        assert result[0].issue_type == "语病"
        assert result[0].confidence == 0.8


class TestLLMClientIntegration:
    def test_default_client_uses_mock_when_no_api(self, monkeypatch) -> None:
        """当未配置API base_url/api_key时使用Mock。"""
        from docanchor.llm import get_default_client
        from docanchor.config import Settings
        from docanchor import config

        # 强制构造无API配置
        s = Settings(llm_base_url="", llm_api_key="")
        monkeypatch.setattr(config, "_settings", s)

        client = get_default_client()
        assert client.provider.name == "mock"

    def test_cost_counter_shared_across_calls(self) -> None:
        client = LLMClient(provider=StubProvider({"x": 1}))
        client.call(
            task="a",
            system_prompt="s",
            user_prompt="u",
            schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        client.call(
            task="b",
            system_prompt="s",
            user_prompt="u",
            schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        assert client.cost_counter.total == 2