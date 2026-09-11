"""文本span提取（3.1.5）。"""

from __future__ import annotations

from docanchor.common.idgen import new_object_id
from docanchor.common.schema import BoundingBox, PdfObjectKind, PdfObjectRef


def extract_text_objects(page, page_no: int) -> list[PdfObjectRef]:
    """从PyMuPDF page中提取文本span。

    使用 page.get_text("dict") 获取结构化文本，
    每个 line 的 spans 作为一个文本对象（保留字体属性）。

    Args:
        page: PyMuPDF Page实例。
        page_no: 页码（1-based）。

    Returns:
        该页所有文本span的 PdfObjectRef 列表。
    """
    refs: list[PdfObjectRef] = []
    try:
        d = page.get_text("dict")
    except Exception:
        return refs

    for block in d.get("blocks", []):
        if block.get("type") != 0:  # 0=文本，1=图片
            continue
        bbox = block.get("bbox", (0, 0, 0, 0))
        if not bbox or len(bbox) != 4:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                span_bbox = span.get("bbox", bbox)
                refs.append(
                    PdfObjectRef(
                        object_id=new_object_id(),
                        kind=PdfObjectKind.TEXT_SPAN,
                        page_id=page_no,
                        bbox=BoundingBox(
                            x1=float(span_bbox[0]),
                            y1=float(span_bbox[1]),
                            x2=float(span_bbox[2]),
                            y2=float(span_bbox[3]),
                        ),
                        text=text,
                        font_name=span.get("font"),
                        font_size=float(span.get("size", 0)),
                    )
                )
    return refs


__all__ = ["extract_text_objects"]