"""DOCX → PDF 转换模块（3.1.4）。

主选 LibreOffice headless，备选 OnlyOffice，兜底 Word COM（Windows）。
"""

from docanchor.modules.pdf_convert.converter import (
    ConversionReport,
    convert_docx_to_pdf,
    list_available_engines,
)

__all__ = ["convert_docx_to_pdf", "ConversionReport", "list_available_engines"]