"""预处理清洗（3.3.1）。

- 区块排序：按PDF页面坐标y轴升序、同y轴按x轴升序排列
- 噪声过滤：剔除页眉、页脚、空区块、分割线等
- 文本归一化：统一换行符、去除多余空格，保留原始识别文本
- 类型校验：校验区块类型与内容匹配度
"""

from __future__ import annotations

from docanchor.common.logger import get_logger
from docanchor.common.schema import Block, BlockType

logger = get_logger("global_aggregate.preprocessor")


def preprocess_blocks(blocks: list[Block]) -> list[Block]:
    """对Block列表做排序、去噪、归一、校验。

    Args:
        blocks: 原始Block列表（来自VLM Adapter）。

    Returns:
        处理后的Block列表。
    """
    if not blocks:
        return []

    # 1) 按 (page_id, y, x) 排序 — 保证视觉阅读顺序
    sorted_blocks = sorted(
        blocks,
        key=lambda b: (b.page_id, b.bbox.y1, b.bbox.x1),
    )

    # 2) 噪声过滤：剔除页眉页脚、空区块
    filtered = _filter_noise(sorted_blocks)

    # 3) 文本归一化
    normalized = _normalize_text(filtered)

    # 4) 类型校验：title必须有文本，paragraph可空
    validated = _validate_types(normalized)

    logger.info(
        f"预处理: 输入{len(blocks)} -> "
        f"排序{len(sorted_blocks)} -> "
        f"去噪{len(filtered)} -> "
        f"归一{len(normalized)} -> "
        f"校验{len(validated)}"
    )
    return validated


def _filter_noise(blocks: list[Block]) -> list[Block]:
    """剔除页眉、页脚、空区块、分割线等无效内容。

    页眉页脚启发式：同一页最顶5%或最底5%范围内的、内容长度<50字符的文本块。
    阶段2可结合字体大小判定（页眉页脚通常字号小）。
    """
    result: list[Block] = []
    # 标准A4页面高度842pt。后续可从PDF元数据获取。
    # 注意：不能用"本页最大y2"作为页高——会因block分布不均而误判
    DEFAULT_PAGE_HEIGHT = 842.0
    # 通过page+最大y2 + 余量估算真实页高
    page_bottom_y: dict[int, float] = {}
    for b in blocks:
        cur = page_bottom_y.get(b.page_id, 0.0)
        page_bottom_y[b.page_id] = max(cur, b.bbox.y2)
    # 页高 = max(默认高度, 最大y2)
    page_sizes: dict[int, float] = {
        p: max(DEFAULT_PAGE_HEIGHT, y) for p, y in page_bottom_y.items()
    }

    for b in blocks:
        page_h = page_sizes.get(b.page_id, DEFAULT_PAGE_HEIGHT)
        # 顶部5%或底部5%且文字<50字符视为页眉页脚
        is_top = b.bbox.y2 < page_h * 0.05
        is_bottom = b.bbox.y1 > page_h * 0.95
        if (is_top or is_bottom) and len(b.text) < 50:
            # 保留较长的页眉页脚（如有公司名），仅过滤纯噪音
            continue
        # 完全无内容且非image/table/formula
        if (
            not b.text
            and b.block_type
            not in (BlockType.IMAGE, BlockType.TABLE, BlockType.FORMULA)
        ):
            continue
        result.append(b)
    return result


def _normalize_text(blocks: list[Block]) -> list[Block]:
    """统一换行符、去除多余空格。"""
    for b in blocks:
        if b.text:
            # 统一为 \n
            b.text = b.text.replace("\r\n", "\n").replace("\r", "\n")
            # 每行 strip 首尾空白，再合并连续空白行
            lines = [line.strip() for line in b.text.split("\n")]
            cleaned_lines: list[str] = []
            for line in lines:
                if line or (cleaned_lines and cleaned_lines[-1]):
                    cleaned_lines.append(line)
            b.text = "\n".join(cleaned_lines).strip()
    return blocks


def _validate_types(blocks: list[Block]) -> list[Block]:
    """校验区块类型与内容匹配度，不匹配标记为异常。"""
    for b in blocks:
        if b.block_type == BlockType.TITLE and not b.text:
            b.need_review = True
            b.review_reason = "标题块无文本"
    return blocks


__all__ = ["preprocess_blocks"]