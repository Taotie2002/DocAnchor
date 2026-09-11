"""标准样式映射表（3.5.2）。

按 `node_type` 映射到预置 DOCX 模板的样式 ID。
参考文档3.5.2的样式映射规范。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docanchor.common.schema import NodeType


@dataclass
class StyleSpec:
    """单个样式的完整定义。"""

    style_id: str  # DOCX style id
    display_name: str  # 用户可见名
    font_name: str  # 字体（英文/中文）
    font_name_cn: str | None = None  # 中文名
    font_size_pt: float = 11.0
    bold: bool = False
    space_before_pt: float = 0
    space_after_pt: float = 0
    line_spacing: float = 1.5  # 倍数
    first_line_indent_chars: float = 0  # 首行缩进字符数
    keep_with_next: bool = False
    page_break_before: bool = False
    alignment: str = "left"  # left | center | right | both
    extra: dict[str, Any] | None = None  # 表格/图片特殊属性


STYLE_TABLE: dict[NodeType, StyleSpec] = {
    NodeType.HEADING: {
        1: StyleSpec(
            style_id="Heading1",
            display_name="Heading 1",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=22.0,  # 二号 = 22pt
            bold=False,
            space_before_pt=24,
            space_after_pt=18,
            line_spacing=1.5,
            keep_with_next=True,
            page_break_before=True,
            alignment="left",
        ),
        2: StyleSpec(
            style_id="Heading2",
            display_name="Heading 2",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=16.0,  # 三号 = 16pt
            bold=False,
            space_before_pt=18,
            space_after_pt=12,
            line_spacing=1.5,
            keep_with_next=True,
            alignment="left",
        ),
        3: StyleSpec(
            style_id="Heading3",
            display_name="Heading 3",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=14.0,  # 四号 = 14pt
            bold=False,
            space_before_pt=12,
            space_after_pt=6,
            line_spacing=1.5,
            keep_with_next=True,
            alignment="left",
        ),
        4: StyleSpec(
            style_id="Heading4",
            display_name="Heading 4",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=12.0,
            bold=False,
            space_before_pt=6,
            space_after_pt=3,
            line_spacing=1.5,
            keep_with_next=True,
            alignment="left",
        ),
        5: StyleSpec(
            style_id="Heading5",
            display_name="Heading 5",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=11.0,
            bold=True,
            space_before_pt=3,
            space_after_pt=3,
            line_spacing=1.5,
            keep_with_next=True,
            alignment="left",
        ),
        6: StyleSpec(
            style_id="Heading6",
            display_name="Heading 6",
            font_name="Times New Roman",
            font_name_cn="黑体",
            font_size_pt=11.0,
            bold=True,
            space_before_pt=3,
            space_after_pt=3,
            line_spacing=1.5,
            keep_with_next=True,
            alignment="left",
        ),
    },  # type: ignore[dict-item]
    NodeType.PARAGRAPH: StyleSpec(
        style_id="Normal",
        display_name="Normal",
        font_name="Times New Roman",
        font_name_cn="宋体",
        font_size_pt=12.0,  # 小四 = 12pt
        space_before_pt=0,
        space_after_pt=0,
        line_spacing=1.5,
        first_line_indent_chars=2.0,  # 首行缩进2字符
        keep_with_next=True,  # 孤行控制
    ),
    NodeType.LIST: StyleSpec(
        style_id="ListParagraph",
        display_name="List Paragraph",
        font_name="Times New Roman",
        font_name_cn="宋体",
        font_size_pt=12.0,
        line_spacing=1.5,
        first_line_indent_chars=0,
    ),
    NodeType.TABLE: StyleSpec(
        style_id="TableNormal",
        display_name="Table",
        font_name="Times New Roman",
        font_name_cn="宋体",
        font_size_pt=10.5,  # 五号
        line_spacing=1.0,
        alignment="center",
        extra={
            "border_size_pt": 1.0,
            "repeat_header": True,
        },
    ),
    NodeType.IMAGE: StyleSpec(
        style_id="ImageStyle",
        display_name="Image",
        font_name="Times New Roman",
        font_name_cn="宋体",
        font_size_pt=12.0,
        alignment="center",
        extra={
            "embed_inline": True,  # 禁止浮动
            "max_width_ratio": 0.85,  # 最大占版心宽度比例
        },
    ),
    NodeType.CAPTION: StyleSpec(
        style_id="Caption",
        display_name="Caption",
        font_name="Times New Roman",
        font_name_cn="宋体",
        font_size_pt=10.5,  # 五号
        line_spacing=1.5,
        alignment="center",
    ),
    NodeType.FORMULA: StyleSpec(
        style_id="FormulaStyle",
        display_name="Formula",
        font_name="Cambria Math",
        font_name_cn=None,
        font_size_pt=11.0,
        line_spacing=1.5,
        alignment="center",
    ),
}


def get_heading_style(level: int) -> StyleSpec:
    """获取指定层级的标题样式。"""
    if level not in STYLE_TABLE[NodeType.HEADING]:  # type: ignore[operator]
        level = max(1, min(6, level))
    return STYLE_TABLE[NodeType.HEADING][level]  # type: ignore[index]


def get_style(node_type: NodeType, level: int | None = None) -> StyleSpec:
    """获取节点类型的样式。"""
    if node_type == NodeType.HEADING:
        return get_heading_style(level or 1)
    return STYLE_TABLE[node_type]  # type: ignore[index]


__all__ = ["StyleSpec", "STYLE_TABLE", "get_heading_style", "get_style"]