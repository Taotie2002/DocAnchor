"""Mock VLM Provider（阶段1开发联调用）。

按PDF文本span位置生成对应的Block，用于在没有真实MinerU时打通下游链路。

改进版标题识别：
- 字号≥13.5pt → title候选
- 文本以"1.1"/"1.1.1"/"第一章"等编号开头 → title候选（level由编号层级推断）
- 文本以"-" / "•"开头 → list候选

阶段2可替换为真实MinerU Provider。
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from docanchor.common.idgen import new_block_id
from docanchor.common.logger import get_logger
from docanchor.common.schema import Block, BlockType, BoundingBox

logger = get_logger("vlm_adapter.mock")

_TITLE_FONT_SIZE_THRESHOLD = 13.5  # 大于此字号视为标题候选

# 编号标题模式（与 heading_normalize.py 保持一致）
_NUMBERING_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)(?:\s|[\.。]|$)"), 4),
    (re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\s|[\.。]|$)"), 3),
    (re.compile(r"^(\d+)\.(\d+)(?:\s|[\.。]|$)"), 2),
    (re.compile(r"^(\d+)\.(?:\s|[\.。]|$)"), 1),
    (re.compile(r"^第[\d一二三四五六七八九十百千]+(?:章|节|部分|篇)(?:\s|[\.。]|$)"), 1),
    (re.compile(r"^第[\d一二三四五六七八九十百千]+(?:部分)(?:\s|[\.。]|$)"), 1),
]

# 列表项模式
_LIST_PATTERNS = [
    re.compile(r"^\s*\d+[\.\)、]"),
    re.compile(r"^\s*[-•·*]"),
]


def _detect_title_level(text: str, font_size: float) -> tuple[bool, int | None]:
    """判断是否为标题并推断层级。

    Returns:
        (is_title, level)。is_title=False时level=None。
    """
    text = text.strip()
    # 1) 字号阈值 + 短文本
    if font_size >= _TITLE_FONT_SIZE_THRESHOLD and len(text) < 80:
        return True, 1
    # 2) 编号标题（不依赖字号）
    for pattern, level in _NUMBERING_PATTERNS:
        if pattern.match(text):
            return True, level
    return False, None


def _is_list_item(text: str) -> bool:
    """判断是否为列表项。"""
    return any(p.match(text) for p in _LIST_PATTERNS)


class MockVLMProvider:
    """基于PDF原生文本层的Mock VLM Provider。"""

    name = "mock"

    def parse(self, pdf_path: Path) -> list[list[Block]]:
        """解析PDF，按页返回Block数组。"""
        doc = fitz.open(pdf_path)
        try:
            pages: list[list[Block]] = []
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_no = page_idx + 1
                page_size = (page.rect.width, page.rect.height)
                blocks = self._parse_page(page, page_no, page_size)
                pages.append(blocks)
            logger.info(f"Mock VLM: 解析 {len(pages)} 页")
            return pages
        finally:
            doc.close()

    def _parse_page(
        self,
        page,
        page_no: int,
        page_size: tuple[float, float],
    ) -> list[Block]:
        blocks: list[Block] = []
        try:
            d = page.get_text("dict")
        except Exception:
            return blocks

        for block_data in d.get("blocks", []):
            if block_data.get("type") != 0:  # 仅文本
                continue
            for line in block_data.get("lines", []):
                # 同一行的多个span合并（避免编号与文本被切分）
                line_text = "".join(
                    span.get("text", "") for span in line.get("spans", [])
                ).strip()
                if not line_text:
                    continue
                line_bbox = line.get("bbox", (0, 0, 0, 0))
                if len(line_bbox) != 4:
                    continue
                # 取行内最大字号作为行的字号
                max_font_size = max(
                    (float(span.get("size", 0)) for span in line.get("spans", [])),
                    default=0,
                )

                # 块类型判定
                is_title, level = _detect_title_level(line_text, max_font_size)
                if is_title:
                    block_type = BlockType.TITLE
                    local_level = level
                elif _is_list_item(line_text):
                    block_type = BlockType.LIST
                    local_level = None
                else:
                    block_type = BlockType.PARAGRAPH
                    local_level = None

                blocks.append(
                    Block(
                        page_id=page_no,
                        block_id=new_block_id(),
                        bbox=BoundingBox(
                            x1=float(line_bbox[0]),
                            y1=float(line_bbox[1]),
                            x2=float(line_bbox[2]),
                            y2=float(line_bbox[3]),
                        ),
                        block_type=block_type,
                        local_level=local_level,
                        text=line_text,
                        confidence=0.85,
                        vlm_model_version=self.version(),
                    )
                )
        return blocks

    def version(self) -> str:
        return "mock-0.2.0"  # 升级版本号


__all__ = ["MockVLMProvider"]