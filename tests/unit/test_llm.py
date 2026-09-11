"""LLM相关单测：CostCounter/schema_validate/Providers。"""

from __future__ import annotations

import json

import pytest

from docanchor.common.errors import SchemaValidationError
from docanchor.llm.cost_counter import CostCounter
from docanchor.llm.providers.mock import MockLLMProvider
from docanchor.llm.schema_validate import validate_json


class TestCostCounter:
    def test_initial(self) -> None:
        c = CostCounter(budget=10)
        assert c.total == 0
        assert c.remaining == 10
        assert not c.budget_exceeded()

    def test_record(self) -> None:
        c = CostCounter(budget=3)
        c.record("task_a")
        c.record("task_a")
        c.record("task_b")
        assert c.total == 3
        assert c.remaining == 0
        assert c.budget_exceeded()

    def test_by_task(self) -> None:
        c = CostCounter()
        c.record("a")
        c.record("a")
        c.record("b")
        assert c.by_task() == {"a": 2, "b": 1}

    def test_reset(self) -> None:
        c = CostCounter()
        c.record("a")
        c.reset()
        assert c.total == 0


class TestMockLLMProvider:
    def test_chat_returns_dict_str(self) -> None:
        provider = MockLLMProvider()
        out = provider.chat(system_prompt="sys", user_prompt="user")
        # mock返回空JSON
        assert out == "{}"

    def test_version(self) -> None:
        provider = MockLLMProvider()
        v = provider.version()
        assert v.startswith("mock-")


class TestSchemaValidate:
    def test_valid(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }
        data = validate_json(json.dumps({"x": 1}), schema)
        assert data == {"x": 1}

    def test_missing_required(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }
        with pytest.raises(SchemaValidationError):
            validate_json(json.dumps({}), schema)

    def test_invalid_json(self) -> None:
        schema = {"type": "object"}
        with pytest.raises(SchemaValidationError):
            validate_json("not json", schema)

    def test_strips_markdown_fence(self) -> None:
        """LLM返回的```json\n{...}\n```应被自动剥离。"""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }
        # 带 ```json fence
        data = validate_json("```json\n{\"x\": 42}\n```", schema)
        assert data == {"x": 42}
        # 不带language fence
        data = validate_json("```\n{\"x\": 42}\n```", schema)
        assert data == {"x": 42}
        # 没有fence
        data = validate_json('{"x": 42}', schema)
        assert data == {"x": 42}