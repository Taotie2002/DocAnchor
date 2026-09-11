"""语义校验任务（3.6契约）。

输入：text + context
输出：[{"location": str, "issue_type": str, "description": str, "confidence": float}]
约束：仅发现异常并定位，不修改文本
"""

from __future__ import annotations

from dataclasses import dataclass

from docanchor.common.logger import get_logger
from docanchor.llm.client import LLMClient, LLMResult

logger = get_logger("llm.semantic_check")

SEMANTIC_CHECK_ISSUE_SCHEMA = {
    "type": "object",
    "required": ["location", "issue_type", "description", "confidence"],
    "properties": {
        "location": {"type": "string"},
        "issue_type": {"type": "string", "enum": ["不通顺", "歧义", "语病", "错别字", "其他"]},
        "description": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}

SEMANTIC_CHECK_SCHEMA = {
    "type": "array",
    "items": SEMANTIC_CHECK_ISSUE_SCHEMA,
}


SYSTEM_PROMPT = """你是一个中文文本质检专家。你的任务是发现文本中的语义异常。

严格规则：
1. 仅发现不通顺、歧义、语病、错别字等异常，不修改原文
2. location描述异常位置（如"第2段第3句"或"标题：xxx"）
3. issue_type从["不通顺","歧义","语病","错别字","其他"]中选择
4. description简述问题，不要修改原文本
5. confidence表示确信度，无明显异常时返回空数组"""


USER_PROMPT_TEMPLATE = """请检查以下文本是否存在语义异常：

{context_intro}

文本：
{text}

如无明显异常，返回空数组[]。如有异常，按JSON数组返回。"""


@dataclass
class SemanticCheckIssue:
    location: str
    issue_type: str
    description: str
    confidence: float


def semantic_check_text(
    *,
    client: LLMClient,
    text: str,
    context: dict | None = None,
) -> list[SemanticCheckIssue]:
    """调用LLM检测文本中的语义异常。

    Args:
        client: LLM客户端。
        text: 待校验文本。
        context: 可选上下文（如章节、相邻段落）。

    Returns:
        SemanticCheckIssue 列表。无异常则返回空列表。
    """
    context_intro = ""
    if context:
        chapter = context.get("chapter", "")
        if chapter:
            context_intro = f"所属章节：{chapter}"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        context_intro=context_intro,
        text=text,
    )

    # 用judgment温度（默认0.0）；如需更高灵敏度可改用semantic温度（≤0.3）
    from docanchor.config import get_settings

    settings = get_settings()

    result: LLMResult = client.call(
        task="semantic_check",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=SEMANTIC_CHECK_SCHEMA,
        temperature=settings.llm_temperature_semantic,
        max_tokens=512,
    )

    issues: list[SemanticCheckIssue] = []
    if isinstance(result.data, list):
        for d in result.data:
            issues.append(
                SemanticCheckIssue(
                    location=str(d.get("location", "")),
                    issue_type=str(d.get("issue_type", "其他")),
                    description=str(d.get("description", "")),
                    confidence=float(d.get("confidence", 0.0)),
                )
            )
    return issues


__all__ = [
    "semantic_check_text",
    "SemanticCheckIssue",
    "SEMANTIC_CHECK_SCHEMA",
    "SEMANTIC_CHECK_ISSUE_SCHEMA",
]