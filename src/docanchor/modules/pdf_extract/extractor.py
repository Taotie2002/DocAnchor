"""PyMuPDF对象提取主入口（3.1.5）。

协调 text_objects / image_objects / table_objects 三个子模块，
按页面顺序返回统一的 PdfObjectRef 列表。

坐标系说明（3.1.5）：
- 采用PDF原生页面坐标系（点单位，1英寸=72点）
- 原点在页面左下角，X向右递增，Y向上递增
- 与 PyMuPDF page.get_text("dict")["blocks"][...]["bbox"] 完全兼容
"""

from __future__ import annotations

from pathlib import Path

from docanchor.common.idgen import new_object_id
from docanchor.common.logger import get_logger
from docanchor.common.schema import BoundingBox, PdfObjectRef

logger = get_logger("pdf_extract")


def extract_pdf_objects(
    pdf_path: Path,
    *,
    image_output_dir: Path | None = None,
    extract_images: bool = True,
) -> list[PdfObjectRef]:
    """从PDF中提取文本span、图片、表格三类对象。

    Args:
        pdf_path: PDF文件路径。
        image_output_dir: 图片导出目录（None则不导出）。
        extract_images: 是否提取图片。

    Returns:
        按页面顺序的 PdfObjectRef 列表。
    """
    from docanchor.modules.pdf_extract.text_objects import extract_text_objects
    from docanchor.modules.pdf_extract.image_objects import extract_image_objects
    from docanchor.modules.pdf_extract.table_objects import extract_table_objects

    import fitz

    if image_output_dir is None and extract_images:
        image_output_dir = pdf_path.parent / f"{pdf_path.stem}_images"

    doc = fitz.open(pdf_path)
    try:
        all_objects: list[PdfObjectRef] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_no = page_idx + 1

            # 文本span
            all_objects.extend(extract_text_objects(page, page_no))

            # 图片
            if extract_images:
                all_objects.extend(
                    extract_image_objects(page, page_no, image_output_dir)
                )

            # 表格
            all_objects.extend(extract_table_objects(page, page_no))

        logger.info(
            f"PDF对象提取完成: 共 {len(all_objects)} 个对象 "
            f"(页数={len(doc)})"
        )
        return all_objects
    finally:
        doc.close()


def get_object_summary(objects: list[PdfObjectRef]) -> dict[str, int]:
    """统计各类对象数量。"""
    from docanchor.common.schema import PdfObjectKind

    summary: dict[str, int] = {k.value: 0 for k in PdfObjectKind}
    for obj in objects:
        summary[obj.kind.value] += 1
    return summary


__all__ = ["extract_pdf_objects", "get_object_summary"]