"""异常过滤（3.2.2.4）：剔除越界bbox、重复区块、空内容块。

过滤规则：
1. bbox越界（超出页面尺寸）
2. 空内容块（text为空且非image/table）
3. 极小块（面积 < 1pt²）
4. 标题但local_level越界（≤0或≥7）
"""

from __future__ import annotations

from docanchor.common.schema import Block, BlockType


def filter_blocks(
    blocks: list[Block],
    page_size: tuple[float, float],
    *,
    min_area: float = 1.0,
) -> list[Block]:
    """过滤异常Block。

    Args:
        blocks: 原始Block列表。
        page_size: (page_width, page_height)。
        min_area: 最小面积阈值（点²），小于此值的Block被过滤。

    Returns:
        过滤后的Block列表。
    """
    page_w, page_h = page_size
    result: list[Block] = []

    for b in blocks:
        # 1) 越界bbox过滤
        if (
            b.bbox.x1 < 0
            or b.bbox.y1 < 0
            or b.bbox.x2 > page_w + 1
            or b.bbox.y2 > page_h + 1
        ):
            continue

        # 2) 极小块过滤
        if b.bbox.width * b.bbox.height < min_area:
            continue

        # 3) 空内容块过滤（image/table/formula允许空text）
        if (
            not b.text
            and b.block_type
            not in (BlockType.IMAGE, BlockType.TABLE, BlockType.FORMULA)
        ):
            continue

        # 4) title但local_level越界
        if b.block_type == BlockType.TITLE:
            if b.local_level is None or b.local_level < 1 or b.local_level > 6:
                continue

        result.append(b)

    return result


__all__ = ["filter_blocks"]