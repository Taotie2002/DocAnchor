"""标题层级归一化（3.6契约）。

输入：连续标题列表（文本、局部层级、页码、编号信息）
输出：[{"id": str, "global_level": int, "parent_id": str, "confidence": float}]
约束：
- 禁止改写标题文本
- 层级只能为1-6整数
- 无法判定标记confidence<0.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docanchor.common.logger import get_logger
from docanchor.llm.client import LLMClient, LLMResult

logger = get_logger("llm.heading_level")

HEADING_LEVEL_ITEM_SCHEMA = {
    "type": "object",
    "required": ["id", "global_level", "parent_id", "confidence"],
    "properties": {
        "id": {"type": "string"},
        "global_level": {"type": "integer", "minimum": 1, "maximum": 6},
        "parent_id": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}

HEADING_LEVEL_SCHEMA = {
    "type": "array",
    "items": HEADING_LEVEL_ITEM_SCHEMA,
}


SYSTEM_PROMPT = """你是一个文档结构分析专家。你的任务是对一组标题判断其全局层级（1-6级）与父子关系。

严格规则：
1. 禁止改写、补充、删减任何标题文本
2. global_level必须是1-6的整数
3. parent_id必须是该窗口内另一标题的id，或null（顶级标题）
4. confidence表示判断确信度，无法判定时<0.5
5. 如果标题文本自带"第X章"或"X.Y"等编号，应作为强信号
6. 返回严格JSON数组，按输入顺序排列"""


USER_PROMPT_TEMPLATE = """以下是按顺序出现的标题列表，请判断它们的全局层级与父子关系：

输入标题（每行一个）：
{titles}

请返回JSON数组，每个元素形如：
{{"id": "<标题id>", "global_level": <1-6整数>, "parent_id": "<父标题id或null>", "confidence": <0-1>}}"""


@dataclass
class HeadingLevelItem:
    id: str
    global_level: int
    parent_id: str | None
    confidence: float


def normalize_heading_levels(
    *,
    client: LLMClient,
    window: list[dict[str, Any]],
) -> list[HeadingLevelItem]:
    """调用LLM对标题窗口做全局层级判断。

    Args:
        client: LLM客户端。
        window: 标题窗口，每项包含 id/text/local_level/page_id/numbering。

    Returns:
        HeadingLevelItem 列表，与输入顺序一致。
    """
    titles_lines: list[str] = []
    for item in window:
        numbering = item.get("numbering") or ""
        line = f"[id={item['id']}] {numbering}{item['text']} (页={item.get('page_id', '?')}, 局部level={item.get('local_level', '?')})"
        titles_lines.append(line)

    user_prompt = USER_PROMPT_TEMPLATE.format(titles="\n".join(titles_lines))

    result: LLMResult = client.call(
        task="heading_level",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=HEADING_LEVEL_SCHEMA,
        temperature=0.0,
        max_tokens=2048,
    )

    items: list[HeadingLevelItem] = []
    if isinstance(result.data, list):
        for d in result.data:
            items.append(
                HeadingLevelItem(
                    id=str(d.get("id", "")),
                    global_level=int(d.get("global_level", 1)),
                    parent_id=d.get("parent_id"),
                    confidence=float(d.get("confidence", 0.0)),
                )
            )
    return items


__all__ = [
    "normalize_heading_levels",
    "HeadingLevelItem",
    "HEADING_LEVEL_SCHEMA",
    "HEADING_LEVEL_ITEM_SCHEMA",
]