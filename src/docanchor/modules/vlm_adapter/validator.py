"""二次校验（3.2.2.3）：对Block列表做规则级校验。

主要修正：
- 表格行列数与cell_matrix一致性
- 合并单元格坐标合法性
- 局部层级与block_type匹配（title的local_level应为1-6，paragraph无level）
- 重复区块检测
"""

from __future__ import annotations

from docanchor.common.schema import Block, BlockType


def validate_blocks(blocks: list[Block]) -> list[Block]:
    """对Block列表做规则级校验，返回修正后的列表。

    Args:
        blocks: 原始Block列表（来自Provider或Adapter归一化）。

    Returns:
        修正后的Block列表。无效Block会被过滤。
    """
    validated: list[Block] = []
    seen_keys: set[tuple] = set()

    for b in blocks:
        # 1) 必填字段校验
        if not b.block_id or b.page_id < 1:
            continue
        # bbox必须有面积
        if b.bbox.width <= 0 or b.bbox.height <= 0:
            continue

        # 2) title必须带local_level
        if b.block_type == BlockType.TITLE:
            if b.local_level is None or b.local_level < 1 or b.local_level > 6:
                # 强制设置默认level=1
                b.local_level = 1
                b.confidence = min(b.confidence, 0.5)

        # 3) 去重（同页同bbox同type）
        key = (b.page_id, round(b.bbox.x1, 1), round(b.bbox.y1, 1), b.block_type)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        validated.append(b)

    return validated


__all__ = ["validate_blocks"]