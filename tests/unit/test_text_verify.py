"""文字校验模块单测。"""

from __future__ import annotations

from docanchor.common.idgen import new_block_id, new_object_id
from docanchor.common.schema import (
    Block,
    BlockType,
    BoundingBox,
    PdfObjectKind,
    PdfObjectRef,
)
from docanchor.modules.text_verify.aligner import align_vlm_with_pdf
from docanchor.modules.text_verify.critical_fields import (
    extract_critical_fields,
    verify_critical_fields,
)


class TestCriticalFields:
    def test_extract_amount(self) -> None:
        hits = extract_critical_fields("总金额为 RMB 12,500.00 元")
        amount_hits = [h for h in hits if h.field_type == "amount"]
        assert len(amount_hits) >= 1

    def test_extract_date(self) -> None:
        hits = extract_critical_fields("合同日期 2026-09-10 生效")
        date_hits = [h for h in hits if h.field_type == "date"]
        assert len(date_hits) >= 1

    def test_extract_code(self) -> None:
        hits = extract_critical_fields("合同编号: ABC-2026-001 签署")
        code_hits = [h for h in hits if h.field_type == "code"]
        assert len(code_hits) >= 1

    def test_extract_phone(self) -> None:
        hits = extract_critical_fields("联系方式: 13800138000")
        phone_hits = [h for h in hits if h.field_type == "phone"]
        assert len(phone_hits) >= 1

    def test_extract_email(self) -> None:
        hits = extract_critical_fields("邮箱: test.user@example.com")
        email_hits = [h for h in hits if h.field_type == "email"]
        assert len(email_hits) >= 1

    def test_verify_no_conflict(self) -> None:
        text = "总金额 1000 元，日期 2026-01-01，编号 ABC-001"
        conflicts = verify_critical_fields(text, text, text)
        assert len(conflicts) == 0

    def test_verify_vlm_vs_pdf_conflict(self) -> None:
        vlm = "总金额 1000 元"
        pdf = "总金额 10000 元"
        conflicts = verify_critical_fields(vlm, pdf)
        assert len(conflicts) >= 1
        assert conflicts[0].source == "vlm_vs_pdf"
        assert conflicts[0].resolution == "adopted_pdf"


class TestAligner:
    def _block(self, text: str, page: int = 1, x: float = 0, y: float = 0) -> Block:
        return Block(
            page_id=page,
            block_id=new_block_id(),
            bbox=BoundingBox(x1=x, y1=y, x2=x + 100, y2=y + 20),
            block_type=BlockType.PARAGRAPH,
            text=text,
            confidence=0.9,
        )

    def _pdf_text(self, text: str, page: int = 1, x: float = 0, y: float = 0) -> PdfObjectRef:
        return PdfObjectRef(
            object_id=new_object_id(),
            kind=PdfObjectKind.TEXT_SPAN,
            page_id=page,
            bbox=BoundingBox(x1=x, y1=y, x2=x + 100, y2=y + 20),
            text=text,
        )

    def test_strong_match(self) -> None:
        vlm_blocks = [self._block("完全相同的文本内容")]
        pdf_objects = [self._pdf_text("完全相同的文本内容")]
        matches = align_vlm_with_pdf(vlm_blocks, pdf_objects)
        assert len(matches) == 1
        assert matches[0].level == "strong"

    def test_no_match(self) -> None:
        vlm_blocks = [self._block("苹果是一种水果")]
        pdf_objects = [self._pdf_text("汽车需要加油")]
        matches = align_vlm_with_pdf(vlm_blocks, pdf_objects)
        assert len(matches) == 1
        assert matches[0].level == "none"

    def test_empty_inputs(self) -> None:
        assert align_vlm_with_pdf([], []) == []
        # PDF无文本对象时，VLM块视为无匹配
        result = align_vlm_with_pdf([self._block("VLM识别文字")], [])
        assert len(result) == 1
        assert result[0].level == "none"

    def test_greedy_no_double_match(self) -> None:
        # 两个VLM块都想匹配同一PDF对象，贪心确保只匹配一个
        vlm_blocks = [
            self._block("相同的文本"),
            self._block("相同的文本"),
        ]
        pdf_objects = [self._pdf_text("相同的文本")]
        matches = align_vlm_with_pdf(vlm_blocks, pdf_objects)
        # 只有一个强匹配，另一个无匹配
        strong = [m for m in matches if m.level == "strong"]
        assert len(strong) == 1