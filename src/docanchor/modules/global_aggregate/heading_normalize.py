"""标题层级归一化（3.3.3原型）。

阶段1实现：基于文档自带章节编号的规则解析（最高优先级信号）。
阶段2完善：滑动窗口 + LLM小模型判断。

支持的编号格式：
- 阿拉伯数字：1. / 1.1 / 1.1.1
- 中文数字：第一章 / 第一节
- 罗马数字：I. / II.
- 带括号：(一) / (1)
"""

from __future__ import annotations

import re

from docanchor.common.logger import get_logger

logger = get_logger("global_aggregate.heading_normalize")


# 编号模式（从最具体到最宽泛）
_NUMBERING_PATTERNS: list[tuple[re.Pattern, int]] = [
    # 1.1.1.1 阿拉伯数字（最多4层）
    (re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)(?:\s|[\.。]|$)"), 4),
    (re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\s|[\.。]|$)"), 3),
    (re.compile(r"^(\d+)\.(\d+)(?:\s|[\.。]|$)"), 2),
    (re.compile(r"^(\d+)\.(?:\s|[\.。]|$)"), 1),
    # 第X章 / 第X节 / 第X部分
    (re.compile(r"^第[\d一二三四五六七八九十百千]+(?:章|节|部分|篇)(?:\s|[\.。]|$)"), 1),
    # (一)(1)
    (re.compile(r"^\([\d一二三四五六七八九十]+\)(?:\s|$)"), 2),
    # I. / II. / III. 罗马数字
    (re.compile(r"^[IVX]+\.(?:\s|$)"), 1),
]


def extract_numbering(text: str) -> tuple[int, str]:
    """从标题文本中提取章节编号与对应层级。

    Args:
        text: 标题文本。

    Returns:
        (level, numbering_str)：level 0表示未识别，1-6表示层级。
    """
    text = text.strip()
    for pattern, level in _NUMBERING_PATTERNS:
        m = pattern.match(text)
        if m:
            numbering = m.group(0).rstrip()
            # 去掉结尾的点和句号
            while numbering and numbering[-1] in " .。":
                numbering = numbering[:-1]
            return level, numbering
    return 0, ""


def normalize_heading_levels(
    headings: list[dict],
) -> list[dict]:
    """对标题列表做全局层级归一化（规则优先版本）。

    Args:
        headings: 标题列表，每项包含 id/text/local_level/page_id。

    Returns:
        每项添加 global_level 字段。
    """
    result: list[dict] = []
    for h in headings:
        text = h.get("text", "").strip()
        level, numbering = extract_numbering(text)
        # 优先级：文档自带编号 > local_level
        if level > 0:
            global_level = level
        else:
            # local_level可能是None或1-6
            local = h.get("local_level")
            global_level = local if isinstance(local, int) and 1 <= local <= 6 else 1
        new_h = dict(h)
        new_h["global_level"] = global_level
        new_h["numbering"] = numbering
        result.append(new_h)
    return result


__all__ = ["extract_numbering", "normalize_heading_levels"]