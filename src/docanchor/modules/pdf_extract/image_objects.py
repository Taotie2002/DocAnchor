"""图片对象提取（3.1.5）。

提取PDF内嵌图片，导出到指定目录，记录bbox与尺寸。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from docanchor.common.idgen import new_object_id
from docanchor.common.schema import BoundingBox, PdfObjectKind, PdfObjectRef


def extract_image_objects(
    page,
    page_no: int,
    output_dir: Path | None,
) -> list[PdfObjectRef]:
    """从PyMuPDF page中提取图片。

    Args:
        page: PyMuPDF Page实例。
        page_no: 页码（1-based）。
        output_dir: 图片导出目录。

    Returns:
        该页所有图片的 PdfObjectRef 列表。
    """
    refs: list[PdfObjectRef] = []
    image_list = page.get_images(full=True)
    if not image_list:
        return refs

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
        except Exception:
            continue
        if not base_image:
            continue

        # 图片bbox：用page.get_image_rects获取精确位置
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []

        if not rects:
            # 没有rect信息时跳过（不创建占位对象）
            continue

        # 处理每个实例（同一xref可能多次出现）
        for rect_idx, rect in enumerate(rects):
            ext = base_image.get("ext", "png")
            img_bytes = base_image["image"]
            # 内容hash作为去重锚
            content_hash = hashlib.sha1(img_bytes).hexdigest()[:12]

            image_ref = ""
            if output_dir is not None:
                filename = f"p{page_no:03d}_x{xref:04d}_h{content_hash}.{ext}"
                target = output_dir / filename
                if not target.exists():
                    target.write_bytes(img_bytes)
                image_ref = str(target)

            refs.append(
                PdfObjectRef(
                    object_id=new_object_id(),
                    kind=PdfObjectKind.IMAGE,
                    page_id=page_no,
                    bbox=BoundingBox(
                        x1=float(rect.x0),
                        y1=float(rect.y0),
                        x2=float(rect.x1),
                        y2=float(rect.y1),
                    ),
                    image_ref=image_ref,
                    width=float(base_image.get("width", 0)),
                    height=float(base_image.get("height", 0)),
                )
            )
    return refs


__all__ = ["extract_image_objects"]