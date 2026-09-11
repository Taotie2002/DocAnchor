"""JSON Schema 校验 + 重试辅助。"""

from __future__ import annotations

import json
import re
from typing import Any

from docanchor.common.errors import SchemaValidationError


def _strip_markdown_fence(text: str) -> str:
    """剥离LLM返回的markdown fence（```json ... ```）。"""
    text = text.strip()
    # 匹配 ```json\n{...}\n``` 或 ```\n{...}\n```
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def validate_json(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    """校验LLM返回的JSON文本是否符合Schema。

    自动剥离markdown fence、提取JSON部分。

    Args:
        text: LLM返回文本（可能含markdown fence）。
        schema: JSON Schema定义。

    Returns:
        解析后的字典。

    Raises:
        SchemaValidationError: 解析或校验失败。
    """
    import jsonschema

    text = _strip_markdown_fence(text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SchemaValidationError(
            f"JSON解析失败: {e}; raw={text[:200]!r}"
        ) from e

    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise SchemaValidationError(
            f"Schema校验失败: {e.message}",
            errors=[e.message],
        ) from e
    return data


__all__ = ["validate_json"]