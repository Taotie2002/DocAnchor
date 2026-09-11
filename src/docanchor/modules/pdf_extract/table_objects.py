"""表格对象提取（3.1.5）。

使用 PyMuPDF 的 page.find_tables() 接口识别表格结构。
对每页的每个表格生成 cell_matrix（二维字符串数组）。
"""

from __future__ import annotations

from docanchor.common.idgen import new_object_id
from docanchor.common.schema import BoundingBox, PdfObjectKind, PdfObjectRef


def extract_table_objects(page, page_no: int) -> list[PdfObjectRef]:
    """从PyMuPDF page中识别表格结构。

    Args:
        page: PyMuPDF Page实例。
        page_no: 页码（1-based）。

    Returns:
        该页所有表格的 PdfObjectRef 列表。
    """
    refs: list[PdfObjectRef] = []
    try:
        tables = page.find_tables()
    except Exception:
        # 较老版本PyMuPDF可能不支持此API
        return refs

    for table in tables:
        try:
            extracted = table.extract()
        except Exception:
            continue
        if not extracted:
            continue
        # 过滤完全空的表格
        cell_matrix = [
            [(cell or "").strip() for cell in row]
            for row in extracted
        ]
        if not any(any(cell for cell in row) for row in cell_matrix):
            continue

        row_count = len(cell_matrix)
        col_count = max((len(row) for row in cell_matrix), default=0)

        # bbox
        try:
            bbox = table.bbox  # (x0, y0, x1, y1)
        except Exception:
            bbox = (0, 0, 0, 0)

        refs.append(
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TABLE,
                page_id=page_no,
                bbox=BoundingBox(
                    x1=float(bbox[0]),
                    y1=float(bbox[1]),
                    x2=float(bbox[2]),
                    y2=float(bbox[3]),
                ),
                row_count=row_count,
                col_count=col_count,
                cell_matrix=cell_matrix,
            )
        )
    return refs


__all__ = ["extract_table_objects"]