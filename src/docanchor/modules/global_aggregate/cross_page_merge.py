"""跨页对象合并（3.3.2）。

类型：
1. 跨页段落合并
2. 跨页列表合并
3. 跨页表格合并

原则：宁可漏合、不可错合。模糊场景标记待复核，不自动篡改结构。
"""

from __future__ import annotations

import re

from docanchor.common.logger import get_logger
from docanchor.common.schema import Block, BlockType, PdfObjectKind, PdfObjectRef

logger = get_logger("global_aggregate.cross_page_merge")

# 跨页段落合并阈值
_PARAGRAPH_MERGE_MIN_OVERLAP = 0.30

# 跨页表格合并阈值
_TABLE_HEADER_MATCH_THRESHOLD = 0.80


def detect_cross_page_paragraphs(blocks: list[Block]) -> list[tuple[Block, Block]]:
    """检测跨页段落对。

    Args:
        blocks: 已排序的Block列表（按视觉阅读顺序）。

    Returns:
        跨页段落对列表 (页尾段, 下页首段)。
    """
    if not blocks:
        return []

    pairs: list[tuple[Block, Block]] = []
    by_page: dict[int, list[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page_id, []).append(b)

    pages = sorted(by_page.keys())
    for i in range(len(pages) - 1):
        cur_page = by_page[pages[i]]
        next_page = by_page[pages[i + 1]]
        if not cur_page or not next_page:
            continue
        cur_tail = [b for b in cur_page[-3:] if b.block_type == BlockType.PARAGRAPH]
        next_head = [b for b in next_page[:3] if b.block_type == BlockType.PARAGRAPH]
        for tail in cur_tail:
            for head in next_head:
                if _should_merge_paragraph(tail, head):
                    pairs.append((tail, head))
                    break
    return pairs


def detect_cross_page_lists(blocks: list[Block]) -> list[tuple[Block, Block]]:
    """检测跨页列表项对。

    规则（3.3.2.2）：
    1. 页尾为有序列表项（以数字/中文数字/罗马数字/括号编号开头）
    2. 下页首列表项编号连续
    3. 列表缩进层级一致（粗略：bbox的x坐标一致）

    Returns:
        跨页列表项对列表。
    """
    if not blocks:
        return []

    pairs: list[tuple[Block, Block]] = []
    by_page: dict[int, list[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page_id, []).append(b)

    pages = sorted(by_page.keys())
    for i in range(len(pages) - 1):
        cur_page = by_page[pages[i]]
        next_page = by_page[pages[i + 1]]
        if not cur_page or not next_page:
            continue
        cur_tail = [b for b in cur_page[-5:] if _is_list_item(b.text)]
        next_head = [b for b in next_page[:5] if _is_list_item(b.text)]
        for tail in cur_tail:
            for head in next_head:
                if _should_merge_list(tail, head):
                    pairs.append((tail, head))
                    break
    return pairs


def detect_cross_page_tables(
    blocks: list[Block],
    pdf_objects: list[PdfObjectRef],
) -> list[tuple[PdfObjectRef, PdfObjectRef]]:
    """检测跨页表格对（基于PyMuPDF的表格对象）。

    规则（3.3.2.3）：
    1. 列数一致
    2. 表头关键词匹配度≥80%
    3. 跨页归属（页码连续）

    Args:
        blocks: Block列表（暂未直接使用，保留接口用于阶段2增强）
        pdf_objects: PyMuPDF提取的表格对象列表。

    Returns:
        跨页表格对列表。
    """
    tables = [o for o in pdf_objects if o.kind == PdfObjectKind.TABLE]
    if len(tables) < 2:
        return []

    pairs: list[tuple[PdfObjectRef, PdfObjectRef]] = []
    for i in range(len(tables) - 1):
        a, b = tables[i], tables[i + 1]
        # 跨页判定：页码连续
        if b.page_id - a.page_id != 1:
            continue
        # 列数一致
        if a.col_count != b.col_count:
            continue
        # 表头关键词匹配
        match_ratio = _header_keyword_overlap(a, b)
        if match_ratio < _TABLE_HEADER_MATCH_THRESHOLD:
            continue
        pairs.append((a, b))
    return pairs


# ============================================================
# 内部工具函数
# ============================================================


_SENTENCE_ENDINGS = ("。", "！", "？", "；", "：", '"', ".", "!", "?", ";", ":")

# 列表编号模式
_LIST_PATTERNS = [
    re.compile(r"^\s*\d+[\.\)、]"),       # 1.  1)  1、
    re.compile(r"^\s*[一二三四五六七八九十]+[、\.]"),  # 一、 二.
    re.compile(r"^\s*\([\d一二三四五六七八九十]+\)"),  # (1) (一)
    re.compile(r"^\s*[IVX]+[\.\)]"),     # I. II)
    re.compile(r"^\s*[-•·*]"),            # - •
]


def _should_merge_paragraph(tail: Block, head: Block) -> bool:
    """判断两个段落是否应合并（跨页段落规则）。"""
    if tail.block_type != BlockType.PARAGRAPH or head.block_type != BlockType.PARAGRAPH:
        return False
    if not tail.text or not head.text:
        return False
    if tail.text.rstrip().endswith(_SENTENCE_ENDINGS):
        return False
    overlap = _keyword_overlap(tail.text, head.text)
    return overlap >= _PARAGRAPH_MERGE_MIN_OVERLAP


def _is_list_item(text: str) -> bool:
    """判断文本是否为列表项。"""
    if not text:
        return False
    return any(p.match(text) for p in _LIST_PATTERNS)


def _should_merge_list(tail: Block, head: Block) -> bool:
    """判断两个列表项是否应合并（跨页列表规则）。"""
    if not _is_list_item(tail.text) or not _is_list_item(head.text):
        return False
    # 编号连续性
    tail_num = _extract_list_number(tail.text)
    head_num = _extract_list_number(head.text)
    if tail_num is None or head_num is None:
        return False
    if head_num != tail_num + 1:
        return False
    # 缩进层级（bbox的x1）一致
    return abs(tail.bbox.x1 - head.bbox.x1) < 30


def _extract_list_number(text: str) -> int | None:
    """从列表项文本中提取编号。"""
    text = text.strip()
    # 阿拉伯数字
    m = re.match(r"^(\d+)", text)
    if m:
        return int(m.group(1))
    # 中文数字
    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    for k, v in cn_map.items():
        if text.startswith(k):
            return v
    return None


def _keyword_overlap(a: str, b: str) -> float:
    """计算两个文本的关键词重叠率。"""
    def _tokenize(text: str) -> set[str]:
        text = text.strip()
        tokens: set[str] = set()
        for word in text.split():
            if len(word) > 1:
                tokens.add(word.lower())
            for ch in word:
                if "\u4e00" <= ch <= "\u9fff":
                    tokens.add(ch)
        return tokens

    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union) if union else 0.0


def _header_keyword_overlap(
    a: PdfObjectRef, b: PdfObjectRef
) -> float:
    """计算两个表格表头的关键词匹配度。"""
    if not a.cell_matrix or not b.cell_matrix:
        return 0.0
    header_a = a.cell_matrix[0] if a.cell_matrix else []
    header_b = b.cell_matrix[0] if b.cell_matrix else []
    text_a = " ".join(header_a).strip()
    text_b = " ".join(header_b).strip()
    if not text_a or not text_b:
        return 0.0
    return _keyword_overlap(text_a, text_b)


__all__ = [
    "detect_cross_page_paragraphs",
    "detect_cross_page_lists",
    "detect_cross_page_tables",
]