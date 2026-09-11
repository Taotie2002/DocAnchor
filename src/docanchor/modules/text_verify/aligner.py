"""VLM↔PDF文本预对齐（3.4.2）。

策略（文档3.4.2）：
1. 匹配算法：先按坐标范围粗筛候选对象，再计算文本相似度
2. 采用贪心匹配算法，计算双向匹配度
3. 匹配分级：
   - 强匹配：文本相似度≥0.95 且 坐标范围重叠
   - 弱匹配：文本相似度0.8~0.95 或 坐标部分重叠
   - 无匹配：VLM区块无对应PDF文本对象

注意：本实现聚焦规则层的预对齐与分级，不调用LLM（LLM仅在后续语义校验中使用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

from docanchor.common.logger import get_logger
from docanchor.common.schema import Block, PdfObjectKind, PdfObjectRef

logger = get_logger("text_verify.aligner")

# 默认阈值（来自配置项）
from docanchor.config import get_settings

settings = get_settings()


@dataclass
class AlignmentMatch:
    """对齐匹配结果。"""

    vlm_block_id: str
    pdf_object_id: str
    text_similarity: float
    bbox_overlap: bool
    level: str  # strong | weak | none
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "vlm_block_id": self.vlm_block_id,
            "pdf_object_id": self.pdf_object_id,
            "text_similarity": round(self.text_similarity, 4),
            "bbox_overlap": self.bbox_overlap,
            "level": self.level,
            "confidence": round(self.confidence, 4),
        }


def _text_similarity(a: str, b: str) -> float:
    """文本相似度（SequenceMatcher ratio）。

    Args:
        a: 字符串A。
        b: 字符串B。

    Returns:
        0-1之间的相似度。
    """
    if not a or not b:
        return 0.0
    a_norm = a.strip()
    b_norm = b.strip()
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _bbox_overlap(bbox_a, bbox_b) -> bool:
    """判断两个bbox是否重叠（任一像素）。"""
    return bbox_a.overlaps(bbox_b)


def align_vlm_with_pdf(
    vlm_blocks: list[Block],
    pdf_objects: list[PdfObjectRef],
) -> list[AlignmentMatch]:
    """VLM块与PDF文本对象的对齐。

    Args:
        vlm_blocks: VLM Adapter输出Block列表。
        pdf_objects: PyMuPDF对象列表（含text_span）。

    Returns:
        对齐匹配结果列表。每个VLM块最多与一个PDF对象对齐（贪心）。
    """
    # 仅考虑PDF文本span
    pdf_texts = [o for o in pdf_objects if o.kind == PdfObjectKind.TEXT_SPAN]
    if not vlm_blocks:
        return []

    # 如果PDF无文本对象，所有VLM块标记为无匹配
    if not pdf_texts:
        return [
            AlignmentMatch(
                vlm_block_id=vb.block_id,
                pdf_object_id="",
                text_similarity=0.0,
                bbox_overlap=False,
                level="none",
                confidence=0.0,
            )
            for vb in vlm_blocks
            if vb.text
        ]

    # 计算所有(vlm, pdf)对的相似度矩阵
    candidates: list[tuple[float, bool, Block, PdfObjectRef]] = []
    for vb in vlm_blocks:
        if not vb.text:
            continue
        for po in pdf_texts:
            sim = _text_similarity(vb.text, po.text)
            if sim < settings.text_weak_match_threshold:
                continue
            overlap = _bbox_overlap(vb.bbox, po.bbox)
            candidates.append((sim, overlap, vb, po))

    # 按相似度排序，贪心匹配
    candidates.sort(key=lambda c: (-c[0], not c[1]))

    used_vlm: set[str] = set()
    used_pdf: set[str] = set()
    matches: list[AlignmentMatch] = []

    for sim, overlap, vb, po in candidates:
        if vb.block_id in used_vlm or po.object_id in used_pdf:
            continue
        if sim >= settings.text_strong_match_threshold and overlap:
            level = "strong"
            conf = (sim + 1.0) / 2
        elif sim >= settings.text_weak_match_threshold:
            level = "weak"
            conf = sim * 0.8
        else:
            level = "none"
            conf = sim * 0.5
        matches.append(
            AlignmentMatch(
                vlm_block_id=vb.block_id,
                pdf_object_id=po.object_id,
                text_similarity=sim,
                bbox_overlap=overlap,
                level=level,
                confidence=conf,
            )
        )
        used_vlm.add(vb.block_id)
        used_pdf.add(po.object_id)

    # 对未匹配的VLM块生成无匹配条目
    matched_vlm = {m.vlm_block_id for m in matches}
    for vb in vlm_blocks:
        if vb.block_id not in matched_vlm and vb.text:
            matches.append(
                AlignmentMatch(
                    vlm_block_id=vb.block_id,
                    pdf_object_id="",
                    text_similarity=0.0,
                    bbox_overlap=False,
                    level="none",
                    confidence=0.0,
                )
            )

    logger.info(
        f"对齐完成: vlm_blocks={len(vlm_blocks)}, "
        f"pdf_objects={len(pdf_texts)}, "
        f"matches={len(matches)} "
        f"(strong={sum(1 for m in matches if m.level=='strong')}, "
        f"weak={sum(1 for m in matches if m.level=='weak')}, "
        f"none={sum(1 for m in matches if m.level=='none')})"
    )
    return matches


__all__ = ["AlignmentMatch", "align_vlm_with_pdf"]