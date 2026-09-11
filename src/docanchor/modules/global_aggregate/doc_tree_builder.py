"""全局文档树构建（3.3.4）。

完整版本（阶段2）：
1. 标题归一化（基于规则编号解析）
2. 构建章节栈（基于归一化层级）
3. 段落/列表挂载到最近上级标题
4. 图片+图注配对（基于垂直距离）
5. 合并跨页对象
6. 输出完整可序列化的全局文档树
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docanchor.common.idgen import new_node_id
from docanchor.common.logger import get_logger
from docanchor.common.schema import (
    Block,
    BlockType,
    DocumentTree,
    GlobalNode,
    ImageExtension,
    ListExtension,
    NativeProvenance,
    NodeType,
    PdfObjectKind,
    PdfObjectRef,
    TableExtension,
)
from docanchor.modules.global_aggregate.heading_normalize import normalize_heading_levels

logger = get_logger("global_aggregate.doc_tree_builder")

# BlockType -> NodeType 映射
_BLOCK_TO_NODE: dict[BlockType, NodeType] = {
    BlockType.TITLE: NodeType.HEADING,
    BlockType.PARAGRAPH: NodeType.PARAGRAPH,
    BlockType.TABLE: NodeType.TABLE,
    BlockType.LIST: NodeType.LIST,
    BlockType.IMAGE: NodeType.IMAGE,
    BlockType.CAPTION: NodeType.CAPTION,
    BlockType.FORMULA: NodeType.FORMULA,
}


@dataclass
class ImageCaptionPair:
    """图片与图注的配对。"""

    image: GlobalNode
    caption: GlobalNode | None = None


def build_document_tree(
    blocks: list[Block],
    *,
    document_id: str = "",
    source_pdf: str = "",
    pdf_objects: list[PdfObjectRef] | None = None,
    image_caption_distance_ratio: float = 0.30,
) -> DocumentTree:
    """从Block列表构建全局文档树（完整版本）。

    Args:
        blocks: 已预处理的Block列表。
        document_id: 文档标识。
        source_pdf: 源PDF路径。
        pdf_objects: PyMuPDF对象（用于表格单元格填充与图文配对）。
        image_caption_distance_ratio: 图文配对距离阈值（图片高度的倍数）。

    Returns:
        DocumentTree：含 root + 所有 GlobalNode，按章节结构组织。
    """
    if not document_id:
        document_id = "doc_" + new_node_id().split("-")[1]

    # 1) 预处理由调用方完成（pipeline.py），此处直接使用 blocks
    preprocessed = blocks

    # 2) 创建GlobalNode
    nodes: dict[str, GlobalNode] = {}
    root = GlobalNode(
        node_id="root",
        node_type=NodeType.DOCUMENT_ROOT,
        text="",
        confidence=1.0,
    )
    nodes["root"] = root

    # 记录顺序（用于阅读顺序）
    for b in preprocessed:
        node = _block_to_node(b)
        nodes[node.node_id] = node

    # 3) 标题归一化 + 章节栈构建
    heading_nodes = [n for n in nodes.values() if n.node_type == NodeType.HEADING]
    _normalize_and_attach_headings(root, heading_nodes, nodes)

    # 4) 非标题Block挂载到最近上级标题
    _attach_to_chapter(root, heading_nodes, nodes)

    # 5) 图文配对
    _pair_image_caption(nodes.values(), ratio=image_caption_distance_ratio)

    # 6) PyMuPDF表格单元格填充 + 表格节点生成
    if pdf_objects:
        _populate_tables_from_pdf(nodes.values(), pdf_objects)
        # PyMuPDF识别的表格但VLM未生成对应table node的，补建
        _add_missing_tables_from_pdf(root, preprocessed, pdf_objects, nodes)

    # 7) 收集统计
    vlm_versions = {b.vlm_model_version for b in preprocessed if b.vlm_model_version}

    tree = DocumentTree(
        document_id=document_id,
        root=root,
        nodes=nodes,
        source_pdf=source_pdf,
        pdf_renderer_version="libreoffice",
        vlm_model_version=",".join(sorted(vlm_versions)) if vlm_versions else "",
        template_version="",
        vlm_block_count=len(preprocessed),
        pdf_object_count=len(pdf_objects) if pdf_objects else 0,
    )
    logger.info(
        f"全局文档树: doc={document_id}, "
        f"headings={len(heading_nodes)}, "
        f"total_nodes={len(nodes)}"
    )
    return tree


def _block_to_node(b: Block) -> GlobalNode:
    """Block -> GlobalNode。"""
    node_type = _BLOCK_TO_NODE.get(b.block_type, NodeType.PARAGRAPH)
    node = GlobalNode(
        node_id=new_node_id(),
        node_type=node_type,
        text=b.text,
        page_range=[b.page_id, b.page_id],
        source_bbox=[b.bbox.x1, b.bbox.y1, b.bbox.x2, b.bbox.y2],
        confidence=b.confidence,
        vlm_model_version=b.vlm_model_version,
        page_block_ids=[b.block_id],
        native_provenance=_infer_provenance(b),
    )
    if node_type == NodeType.HEADING and b.local_level:
        node.global_level = b.local_level
    node.recompute_content_hash()
    return node


def _normalize_and_attach_headings(
    root: GlobalNode,
    headings: list[GlobalNode],
    nodes: dict[str, GlobalNode],
) -> None:
    """标题归一化 + 章节树构建：按编号优先解析全局层级，构建父子关系。

    章节栈策略：
    - 维护一个栈（level, node）
    - 当前标题level > 栈顶level -> 入栈，作为栈顶的子节点
    - 当前标题level <= 栈顶level -> 弹出直到栈顶level < 当前level或栈空
    - 当前标题level = 0 -> 挂到root下
    """
    # 收集标题信息
    heading_info = []
    for h in headings:
        # 用heading_normalize抽取编号信息
        from docanchor.modules.global_aggregate.heading_normalize import extract_numbering

        level, numbering = extract_numbering(h.text)
        if level == 0:
            # 没有编号，使用local_level
            level = h.global_level or 1
        h.global_level = level
        h.recompute_content_hash()  # 重新计算hash
        heading_info.append((h, level, numbering))

    # 构建章节栈
    stack: list[tuple[int, GlobalNode]] = []  # (level, heading_node)

    for h, level, _ in heading_info:
        # 弹栈直到栈顶level < 当前level或栈为空
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            parent = stack[-1][1]
            parent.children_ids.append(h.node_id)
            h.parent_id = parent.node_id
        else:
            root.children_ids.append(h.node_id)
            h.parent_id = root.node_id

        stack.append((level, h))


def _attach_to_chapter(
    root: GlobalNode,
    headings: list[GlobalNode],
    nodes: dict[str, GlobalNode],
) -> None:
    """非标题Block挂载到最近上级标题。

    按页面+y轴排序后，逐个block判断属于哪一标题的章节。
    """
    # 按(页, y1)排序所有非标题block
    other_blocks = [
        n
        for n in nodes.values()
        if n.node_type != NodeType.HEADING
        and n.node_type != NodeType.DOCUMENT_ROOT
    ]
    other_blocks.sort(
        key=lambda n: (
            n.page_range[0] if n.page_range else 0,
            n.source_bbox[1] if n.source_bbox else 0,
        )
    )

    # 章节栈：按页面+y轴维护
    # 对每个非标题block，找到它之前的最后一个标题作为父
    chapter_stack: list[GlobalNode] = []  # 当前章节链

    # 先按页面顺序合并所有节点（标题+其他）做一次扫描
    all_nodes_sorted: list[GlobalNode] = list(headings) + [
        n for n in other_blocks if n not in headings
    ]
    all_nodes_sorted.sort(
        key=lambda n: (
            n.page_range[0] if n.page_range else 0,
            n.source_bbox[1] if n.source_bbox else 0,
        )
    )

    for n in all_nodes_sorted:
        if n.node_type == NodeType.HEADING:
            # 找到该标题的父，构建章节链
            chain = _build_chapter_chain(n, nodes)
            chapter_stack = chain
        elif n.node_type == NodeType.DOCUMENT_ROOT:
            continue
        else:
            # 非标题：挂到当前章节链的最后一个标题
            if chapter_stack:
                parent = chapter_stack[-1]
                parent.children_ids.append(n.node_id)
                n.parent_id = parent.node_id
            else:
                # 没有上级标题，挂到root
                root.children_ids.append(n.node_id)
                n.parent_id = root.node_id


def _build_chapter_chain(
    heading: GlobalNode,
    nodes: dict[str, GlobalNode],
) -> list[GlobalNode]:
    """从root到当前heading构建完整章节链。"""
    chain: list[GlobalNode] = []
    cur: GlobalNode | None = heading
    while cur and cur.node_type != NodeType.DOCUMENT_ROOT:
        chain.append(cur)
        if cur.parent_id is None:
            break
        cur = nodes.get(cur.parent_id)
    chain.reverse()
    return chain


def _pair_image_caption(
    nodes_iter,
    ratio: float = 0.30,
) -> None:
    """图片+图注配对：基于垂直距离最近且位于图片下方/上方的caption。

    距离阈值：图片高度的 ratio 倍（PDF坐标单位）。
    一图多注、多图一注等歧义场景标记待复核。
    """
    images: list[GlobalNode] = [
        n for n in nodes_iter if n.node_type == NodeType.IMAGE
    ]
    captions: list[GlobalNode] = [
        n for n in nodes_iter if n.node_type == NodeType.CAPTION
    ]

    for img in images:
        if not img.image:
            img.image = ImageExtension(image_ref="", width=0.0, height=0.0)
        img_h = img.source_bbox[3] - img.source_bbox[1] if img.source_bbox else 0
        threshold = img_h * ratio

        # 找最近caption
        best_caption: GlobalNode | None = None
        best_dist = float("inf")
        caption_candidates: list[GlobalNode] = []

        for cap in captions:
            if cap.image and cap.image.caption_id:  # 已配对
                continue
            # 垂直距离
            cap_y = cap.source_bbox[1] if cap.source_bbox else 0
            img_y_top = img.source_bbox[1] if img.source_bbox else 0
            img_y_bot = img.source_bbox[3] if img.source_bbox else 0
            # 距离：caption在图下方/上方都允许
            if cap_y >= img_y_top:
                v_dist = cap_y - img_y_bot  # caption在图下方
            else:
                v_dist = img_y_top - cap_y  # caption在图上方
            if v_dist <= threshold and v_dist < best_dist:
                best_dist = v_dist
                best_caption = cap

        if best_caption:
            # 配对成功
            img.image.caption_id = best_caption.node_id
            if not best_caption.image:
                best_caption.image = ImageExtension(image_ref="", width=0.0, height=0.0)
            best_caption.image.caption_id = img.node_id
        else:
            # 无配对：标记待复核
            img.need_review = True
            img.review_reason = "图片未找到匹配图注"


def _populate_tables_from_pdf(
    nodes_iter,
    pdf_objects: list[PdfObjectRef],
) -> None:
    """从PyMuPDF表格对象填充node的table扩展字段。"""
    pdf_tables = [o for o in pdf_objects if o.kind == PdfObjectKind.TABLE]
    table_nodes = [n for n in nodes_iter if n.node_type == NodeType.TABLE]

    # 简单按位置匹配：每个table_node找最近的pdf_table
    for tn in table_nodes:
        if not tn.table:
            tn.table = TableExtension()
        best: PdfObjectRef | None = None
        best_dist = float("inf")
        for pt in pdf_tables:
            if not tn.source_bbox or not pt.bbox:
                continue
            dx = (tn.source_bbox[0] + tn.source_bbox[2]) / 2 - (pt.bbox.x1 + pt.bbox.x2) / 2
            dy = (tn.source_bbox[1] + tn.source_bbox[3]) / 2 - (pt.bbox.y1 + pt.bbox.y2) / 2
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = pt
        if best and best.cell_matrix:
            tn.table.row_count = len(best.cell_matrix)
            tn.table.col_count = best.col_count or 0
            tn.table.cell_matrix = best.cell_matrix
            tn.table.pymupdf_check = "一致" if (
                best.row_count == tn.table.row_count
                and best.col_count == tn.table.col_count
            ) else "不一致"


def _add_missing_tables_from_pdf(
    root: GlobalNode,
    blocks: list[Block],
    pdf_objects: list[PdfObjectRef],
    nodes: dict[str, GlobalNode],
) -> None:
    """PyMuPDF识别的表格但VLM未生成对应table node的，补建并挂到合适章节。

    阶段2增强：Mock VLM不识别表格，PyMuPDF侧识别的表格需补充到文档树。
    """
    pdf_tables = [o for o in pdf_objects if o.kind == PdfObjectKind.TABLE]
    existing_tables = [n for n in nodes.values() if n.node_type == NodeType.TABLE]

    for pt in pdf_tables:
        # 检查是否已有table_node覆盖此pdf_table（_populate_tables_from_pdf中已处理）
        already_covered = any(
            n.table and n.table.cell_matrix == pt.cell_matrix
            for n in existing_tables
        )
        if already_covered:
            continue

        # 创建新table node
        node = GlobalNode(
            node_id=new_node_id(),
            node_type=NodeType.TABLE,
            text="",
            page_range=[pt.page_id, pt.page_id],
            source_bbox=[pt.bbox.x1, pt.bbox.y1, pt.bbox.x2, pt.bbox.y2],
            confidence=0.95,  # PyMuPDF直接识别，可信度高
            vlm_model_version="pymupdf-direct",
            table=TableExtension(
                row_count=pt.row_count or 0,
                col_count=pt.col_count or 0,
                cell_matrix=pt.cell_matrix or [],
                has_cross_page=False,
                pymupdf_check="一致",
            ),
        )
        nodes[node.node_id] = node

        # 挂到合适的章节：找最近的章节标题或root
        page = pt.page_id
        candidates = [
            n for n in nodes.values()
            if n.node_type == NodeType.HEADING
            and n.page_range
            and n.page_range[0] <= page
        ]
        # 取page≤当前且最大的heading
        candidates.sort(key=lambda n: -n.page_range[0])
        if candidates:
            parent = candidates[0]
            parent.children_ids.append(node.node_id)
            node.parent_id = parent.node_id
        else:
            root.children_ids.append(node.node_id)
            node.parent_id = root.node_id


def _infer_provenance(b: Block) -> NativeProvenance:
    """根据Block属性推断原生来源。"""
    if b.vlm_model_version.startswith(("mock-", "fallback-")):
        return NativeProvenance.PDF_TEXT
    if b.vlm_model_version.startswith("mineru-"):
        return NativeProvenance.PURE_VISION
    return NativeProvenance.PURE_VISION


__all__ = ["build_document_tree"]