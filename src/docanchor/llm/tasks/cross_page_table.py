"""跨页表格二元判断（3.6契约）。

输入：上下两个表格的表头文本、列数、首行内容、页面位置
输出：{"is_same_table": bool, "confidence": float}
约束：
- 仅做二元判断，不修改文本
- 置信度<0.8标记待复核
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docanchor.common.errors import SchemaValidationError
from docanchor.common.logger import get_logger
from docanchor.llm.client import LLMClient, LLMResult

logger = get_logger("llm.cross_page_table")

CROSS_PAGE_TABLE_SCHEMA = {
    "type": "object",
    "required": ["is_same_table", "confidence"],
    "properties": {
        "is_same_table": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}


SYSTEM_PROMPT = """你是一个文档结构分析专家。你的任务是判断两个表格是否逻辑上是同一个表格（被分页拆断）。

严格规则：
1. 仅基于表格的列数、表头语义、首行内容判断
2. 不要修改、猜测或补充任何文字内容
3. confidence表示判断确信度
5. 无法确定时，confidence<0.5

返回严格JSON：{"is_same_table": <bool>, "confidence": <0-1>}"""


USER_PROMPT_TEMPLATE = """判断以下两个表格是否逻辑上是同一个表格（被分页拆断）：

表格A：
- 表头：{header_a}
- 列数：{col_count_a}
- 首行：{first_row_a}
- 所在页：{page_a}

表格B：
- 表头：{header_b}
- 列数：{col_count_b}
- 首行：{first_row_b}
- 所在页：{page_b}

请仅返回JSON。"""


@dataclass
class CrossPageTableResult:
    is_same_table: bool
    confidence: float


def judge_cross_page_table(
    *,
    client: LLMClient,
    header_a: str,
    col_count_a: int,
    first_row_a: list[str],
    page_a: int,
    header_b: str,
    col_count_b: int,
    first_row_b: list[str],
    page_b: int,
) -> CrossPageTableResult:
    """调用LLM判断两个表格是否同一逻辑表格。

    Args:
        client: LLM客户端。
        header_a: 表格A的表头文本。
        col_count_a: 表格A的列数。
        first_row_a: 表格A的首行内容列表。
        page_a: 表格A所在页码。
        （header_b/col_count_b/first_row_b/page_b 同理）

    Returns:
        CrossPageTableResult：is_same_table + confidence。
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        header_a=header_a,
        col_count_a=col_count_a,
        first_row_a=" | ".join(first_row_a),
        page_a=page_a,
        header_b=header_b,
        col_count_b=col_count_b,
        first_row_b=" | ".join(first_row_b),
        page_b=page_b,
    )

    result: LLMResult = client.call(
        task="cross_page_table",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=CROSS_PAGE_TABLE_SCHEMA,
        temperature=0.0,  # 严格确定性
        max_tokens=64,
    )

    data = result.data
    return CrossPageTableResult(
        is_same_table=bool(data.get("is_same_table", False)),
        confidence=float(data.get("confidence", 0.0)),
    )


__all__ = ["judge_cross_page_table", "CrossPageTableResult", "CROSS_PAGE_TABLE_SCHEMA"]