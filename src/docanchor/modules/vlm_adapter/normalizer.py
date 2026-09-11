"""结构归一化（3.2.2.1）：将Provider输出映射为标准block_type。

将MinerU或其他Provider的原始类型字符串统一映射到标准 BlockType 枚举值。
未识别的类型归类为 paragraph。
"""

from __future__ import annotations

from docanchor.common.schema import BlockType

# Provider原始类型 -> 标准 BlockType 的对照
_TYPE_MAPPING: dict[str, BlockType] = {
    # MinerU
    "text": BlockType.PARAGRAPH,
    "title": BlockType.TITLE,
    "paragraph": BlockType.PARAGRAPH,
    "list": BlockType.LIST,
    "image": BlockType.IMAGE,
    "figure": BlockType.IMAGE,
    "table": BlockType.TABLE,
    "table_cell": BlockType.TABLE,
    "formula": BlockType.FORMULA,
    "equation": BlockType.FORMULA,
    "caption": BlockType.CAPTION,
    "figure_caption": BlockType.CAPTION,
    "table_caption": BlockType.CAPTION,
    # Donut / Pix2Struct
    "paragraph_title": BlockType.TITLE,
    "page_header": BlockType.PARAGRAPH,
    "page_footer": BlockType.PARAGRAPH,
}


def normalize_block_type(raw_type: str) -> BlockType:
    """将Provider原始类型字符串映射为标准 BlockType。

    Args:
        raw_type: Provider输出的类型字符串（大小写不敏感）。

    Returns:
        标准 BlockType 枚举值。无法识别则返回 PARAGRAPH。
    """
    key = raw_type.strip().lower()
    if key in _TYPE_MAPPING:
        return _TYPE_MAPPING[key]
    # 尝试模糊匹配
    for k, v in _TYPE_MAPPING.items():
        if k in key or key in k:
            return v
    return BlockType.PARAGRAPH


__all__ = ["normalize_block_type"]