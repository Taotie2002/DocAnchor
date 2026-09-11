"""坐标对齐（3.2.2.2）：统一为PDF原生页面坐标系。

VLM Provider 输出的 bbox 应当已是PDF原生坐标系，
本模块负责：
1. 验证 bbox 在页面尺寸内
2. 必要时归一化（百分比→点单位）
3. 检测并修正top-left origin到PDF origin的y轴翻转
4. 修正常见的Provider错误（如左右颠倒）
"""

from __future__ import annotations

from docanchor.common.schema import BoundingBox


def align_coordinates(
    bbox: list[float],
    page_size: tuple[float, float],
) -> list[float]:
    """统一VLM Provider输出的bbox到PDF原生坐标系。

    Args:
        bbox: Provider输出的 [x1, y1, x2, y2]。
        page_size: (page_width, page_height) in points。

    Returns:
        修正后的 [x1, y1, x2, y2]，点单位，左下原点。
    """
    if not bbox or len(bbox) != 4:
        return [0.0, 0.0, page_size[0], page_size[1]]

    x1, y1, x2, y2 = bbox

    # 第一阶段：处理左右颠倒
    if x1 > x2:
        x1, x2 = x2, x1

    # 第二阶段：检测并修正top-left origin → PDF origin（在百分比转换之前）
    page_h = page_size[1]
    # 如果 y1 < y2 且 y2 接近 page_h，则认为是top-left origin，需翻转
    # 启发式：翻转后y值的合理性——翻转后 (page_h - y2) 应小于 (page_h - y1)
    # 即翻转后的"高度"与原bbox高度一致
    if y1 < y2 and y2 > page_h * 0.5 and y1 < page_h * 0.5:
        y1_new = page_h - y1
        y2_new = page_h - y2
        y1, y2 = min(y1_new, y2_new), max(y1_new, y2_new)

    # 第三阶段：处理百分比坐标（[0,1]范围，必须在origin修正后做）
    if 0 <= x1 <= 1 and 0 <= x2 <= 1 and 0 <= y1 <= 1 and 0 <= y2 <= 1:
        x1 *= page_size[0]
        x2 *= page_size[0]
        y1 *= page_size[1]
        y2 *= page_size[1]

    # 裁剪到页面范围内
    x1 = max(0.0, min(x1, page_size[0]))
    x2 = max(0.0, min(x2, page_size[0]))
    y1 = max(0.0, min(y1, page_size[1]))
    y2 = max(0.0, min(y2, page_size[1]))

    return [x1, y1, x2, y2]


def normalize_bbox(
    bbox: list[float],
    page_size: tuple[float, float],
) -> BoundingBox:
    """便捷函数：返回 BoundingBox 对象。"""
    aligned = align_coordinates(bbox, page_size)
    return BoundingBox(x1=aligned[0], y1=aligned[1], x2=aligned[2], y2=aligned[3])


__all__ = ["align_coordinates", "normalize_bbox"]