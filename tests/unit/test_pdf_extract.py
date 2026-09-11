"""PyMuPDF对象提取单测（3.1.5）。"""

from __future__ import annotations

from pathlib import Path

import fitz

from docanchor.common.schema import PdfObjectKind
from docanchor.modules.pdf_extract import extract_pdf_objects, get_object_summary


def _make_pdf_with_content(tmp_path: Path) -> Path:
    """生成测试PDF：含文字+表格。"""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        # 文本
        page.insert_text((50, 100), "Hello PDF Extract", fontsize=14)
        page.insert_text((50, 130), "第二行：中文测试", fontsize=12)
        # 简易表格（手工画线模拟）
        page.insert_text((50, 200), "A | B | C")
        page.insert_text((50, 220), "1 | 2 | 3")
        page.insert_text((50, 240), "4 | 5 | 6")
        doc.save(pdf_path)
    finally:
        doc.close()
    return pdf_path


class TestExtractPdfObjects:
    def test_extract_text_spans(self, tmp_path: Path) -> None:
        pdf = _make_pdf_with_content(tmp_path)
        objects = extract_pdf_objects(pdf)
        texts = [o for o in objects if o.kind == PdfObjectKind.TEXT_SPAN]
        assert len(texts) > 0
        # 至少包含"Hello PDF Extract"
        assert any("Hello" in t.text for t in texts)

    def test_summary(self, tmp_path: Path) -> None:
        pdf = _make_pdf_with_content(tmp_path)
        objects = extract_pdf_objects(pdf)
        summary = get_object_summary(objects)
        assert "text_span" in summary
        assert "image" in summary
        assert "table" in summary

    def test_text_span_has_font(self, tmp_path: Path) -> None:
        pdf = _make_pdf_with_content(tmp_path)
        objects = extract_pdf_objects(pdf)
        texts = [o for o in objects if o.kind == PdfObjectKind.TEXT_SPAN]
        assert texts[0].font_size > 0
        # bbox 是 4-tuple
        bb = texts[0].bbox
        assert bb.x2 > bb.x1
        assert bb.y2 > bb.y1


class TestCoordinates:
    """坐标系统一性验证（PDF原生坐标系）。"""

    def test_page_coordinates(self, tmp_path: Path) -> None:
        pdf = _make_pdf_with_content(tmp_path)
        objects = extract_pdf_objects(pdf)
        for obj in objects:
            # 所有对象bbox必须在页面尺寸内
            assert 0 <= obj.bbox.x1 <= 595
            assert 0 <= obj.bbox.y1 <= 842
            assert obj.bbox.x1 <= obj.bbox.x2
            assert obj.bbox.y1 <= obj.bbox.y2


class TestGetObjectSummary:
    def test_zero_objects(self) -> None:
        summary = get_object_summary([])
        assert summary == {"text_span": 0, "image": 0, "table": 0}

    def test_mixed_objects(self) -> None:
        from docanchor.common.idgen import new_object_id
        from docanchor.common.schema import BoundingBox, PdfObjectRef

        objs = [
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TEXT_SPAN,
                page_id=1,
                bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
                text="a",
            ),
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.IMAGE,
                page_id=1,
                bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
            ),
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.IMAGE,
                page_id=1,
                bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
            ),
        ]
        summary = get_object_summary(objs)
        assert summary["text_span"] == 1
        assert summary["image"] == 2
        assert summary["table"] == 0