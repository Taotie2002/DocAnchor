"""PyMuPDF对象提取（3.1.5）。

提取文本span、图片、表格三类对象，按页面输出，统一坐标系。
"""

from docanchor.modules.pdf_extract.extractor import (
    extract_pdf_objects,
    get_object_summary,
)

__all__ = ["extract_pdf_objects", "get_object_summary"]