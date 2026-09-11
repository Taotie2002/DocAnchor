"""全局聚合模块单测。"""

from __future__ import annotations

from docanchor.common.idgen import reset_counters
from docanchor.common.schema import (
    Block,
    BlockType,
    BoundingBox,
    NodeType,
    PdfObjectKind,
)
from docanchor.modules.global_aggregate.cross_page_merge import (
    detect_cross_page_lists,
    detect_cross_page_paragraphs,
    detect_cross_page_tables,
)
from docanchor.modules.global_aggregate.doc_tree_builder import build_document_tree
from docanchor.modules.global_aggregate.heading_normalize import (
    extract_numbering,
    normalize_heading_levels,
)
from docanchor.modules.global_aggregate.preprocessor import preprocess_blocks


def _b(
    text: str,
    page_id: int,
    x: float,
    y: float,
    *,
    block_type: BlockType = BlockType.PARAGRAPH,
    block_id: str | None = None,
    local_level: int | None = None,
) -> Block:
    return Block(
        page_id=page_id,
        block_id=block_id or f"b-{page_id}-{x}-{y}",
        bbox=BoundingBox(x1=x, y1=y, x2=x + 100, y2=y + 20),
        block_type=block_type,
        text=text,
        local_level=local_level,
        confidence=0.9,
    )


class TestPreprocessor:
    def setup_method(self) -> None:
        reset_counters()

    def test_sort_by_page_y_x(self) -> None:
        blocks = [
            _b("B", page_id=1, x=0, y=200),
            _b("A", page_id=1, x=0, y=100),
            _b("C", page_id=2, x=0, y=100),
        ]
        result = preprocess_blocks(blocks)
        assert result[0].text == "A"
        assert result[1].text == "B"
        assert result[2].text == "C"

    def test_filter_empty_paragraph(self) -> None:
        blocks = [
            _b("real", page_id=1, x=0, y=100),
            _b("", page_id=1, x=0, y=200),  # 空段
        ]
        result = preprocess_blocks(blocks)
        assert len(result) == 1
        assert result[0].text == "real"

    def test_normalize_whitespace(self) -> None:
        blocks = [_b("  hello \r\n world  ", page_id=1, x=0, y=100)]
        result = preprocess_blocks(blocks)
        assert result[0].text == "hello\nworld"

    def test_no_false_positive_page_footer(self) -> None:
        """验证：单页文档中位于页面下方的正文不应被误判为页脚。"""
        # 模拟单页block分布：top=0-100, 段=100-200, 段=200-300
        # 旧bug：page_h=300（最大y2），那么y1=222的block会因>0.95*300=285被误判为页脚
        # 修复：page_h=max(842, 300)=842，y1=222不会被误判
        blocks = [
            _b("header", page_id=1, x=0, y=10),  # 真页眉
            _b("段落1", page_id=1, x=0, y=100),
            _b("段落2", page_id=1, x=0, y=222),  # 应保留
        ]
        result = preprocess_blocks(blocks)
        # header被过滤（顶部5%），段落1、2保留
        assert len(result) == 2
        texts = [b.text for b in result]
        assert "段落1" in texts
        assert "段落2" in texts
        assert "header" not in texts

    def test_keeps_long_paragraphs_at_edges(self) -> None:
        """长文本即使在边缘也不应被过滤。"""
        long_text = "x" * 60
        blocks = [
            _b(long_text, page_id=1, x=0, y=10),  # 长header保留
        ]
        result = preprocess_blocks(blocks)
        assert len(result) == 1  # 保留长header


class TestHeadingNormalize:
    def test_arabic_numbering(self) -> None:
        assert extract_numbering("1.1.1 子节") == (3, "1.1.1")
        assert extract_numbering("1.1 概述") == (2, "1.1")
        assert extract_numbering("1. 引言") == (1, "1")
        assert extract_numbering("1.1.1.1 深嵌") == (4, "1.1.1.1")

    def test_chinese_numbering(self) -> None:
        assert extract_numbering("第一章 概述")[0] == 1
        assert extract_numbering("第二章 详细")[0] == 1
        assert extract_numbering("第三节 标题")[0] == 1

    def test_parenthesized(self) -> None:
        assert extract_numbering("(一) 内容")[0] == 2

    def test_no_numbering(self) -> None:
        assert extract_numbering("无编号标题") == (0, "")

    def test_normalize_list(self) -> None:
        headings = [
            {"id": "h1", "text": "第一章 概述", "local_level": 3, "page_id": 1},
            {"id": "h2", "text": "无编号", "local_level": 1, "page_id": 1},
            {"id": "h3", "text": "1.1 节", "local_level": 2, "page_id": 1},
        ]
        result = normalize_heading_levels(headings)
        assert result[0]["global_level"] == 1  # 编号优先于local
        assert result[1]["global_level"] == 1  # 无编号取local
        assert result[2]["global_level"] == 2  # 编号1.1=level 2


class TestCrossPageMerge:
    def test_detect_cross_page_paragraph(self) -> None:
        blocks = [
            _b("本章介绍项目背景与主要工作内容，", page_id=1, x=0, y=100),  # 无句末标点
            _b("本章介绍项目背景与主要工作内容", page_id=2, x=0, y=100),  # 大量关键词重叠
        ]
        pairs = detect_cross_page_paragraphs(blocks)
        assert len(pairs) == 1
        assert pairs[0][0].text.startswith("本章介绍")
        assert pairs[0][1].text.startswith("本章介绍")

    def test_no_merge_when_sentence_ends(self) -> None:
        blocks = [
            _b("完整段落。", page_id=1, x=0, y=100),  # 有句末标点
            _b("新段落", page_id=2, x=0, y=100),
        ]
        pairs = detect_cross_page_paragraphs(blocks)
        assert len(pairs) == 0


class TestDocTreeBuilder:
    def test_build_simple_tree(self) -> None:
        blocks = [
            _b("第一章 概述", page_id=1, x=0, y=100, block_type=BlockType.TITLE, local_level=1),
            _b("正文段落", page_id=1, x=0, y=200),
        ]
        tree = build_document_tree(blocks, document_id="d1")
        assert tree.document_id == "d1"
        assert tree.root.node_type == NodeType.DOCUMENT_ROOT
        # 标题应挂到root下，正文应挂到标题下
        assert len(tree.root.children_ids) >= 1
        # 第一个子节点是标题
        first_child = tree.get(tree.root.children_ids[0])
        assert first_child is not None
        assert first_child.node_type == NodeType.HEADING
        assert first_child.global_level == 1

    def test_walk_returns_all(self) -> None:
        blocks = [
            _b("Title", page_id=1, x=0, y=100, block_type=BlockType.TITLE, local_level=1),
            _b("Para", page_id=1, x=0, y=200),
        ]
        tree = build_document_tree(blocks)
        walked = tree.walk()
        assert len(walked) >= 2  # root + at least one child

    def test_native_provenance_for_mock(self) -> None:
        blocks = [
            _b("text", page_id=1, x=0, y=100),
        ]
        blocks[0].vlm_model_version = "mock-0.1.0"
        tree = build_document_tree(blocks)
        # 找到非root节点
        for cid in tree.root.children_ids:
            child = tree.get(cid)
            assert child is not None
            if child.node_type == NodeType.PARAGRAPH:
                assert child.native_provenance.value == "PDF文本层"
                break

    def test_chapter_chain(self) -> None:
        """多级标题的章节链构建。"""
        blocks = [
            _b("第一章 总论", page_id=1, x=0, y=100, block_type=BlockType.TITLE, local_level=1),
            _b("1.1 概述", page_id=1, x=0, y=200, block_type=BlockType.TITLE, local_level=2),
            _b("正文段落", page_id=1, x=0, y=300),
        ]
        tree = build_document_tree(blocks, document_id="d2")
        # 找到所有HEADING
        headings = [n for n in tree.nodes.values() if n.node_type == NodeType.HEADING]
        assert len(headings) == 2
        # 二级标题parent是一级标题
        h2 = [h for h in headings if h.global_level == 2][0]
        h1 = [h for h in headings if h.global_level == 1][0]
        assert h2.parent_id == h1.node_id

    def test_table_attach_to_chapter(self) -> None:
        """表格应挂到所属章节。"""
        blocks = [
            _b("第一章", page_id=1, x=0, y=100, block_type=BlockType.TITLE, local_level=1),
            _b("Table content", page_id=1, x=0, y=200, block_type=BlockType.TABLE),
        ]
        tree = build_document_tree(blocks)
        # 找到TABLE节点
        tables = [n for n in tree.nodes.values() if n.node_type == NodeType.TABLE]
        assert len(tables) == 1
        # TABLE的parent应是HEADING
        assert tables[0].parent_id is not None
        parent = tree.get(tables[0].parent_id)
        assert parent is not None
        assert parent.node_type == NodeType.HEADING


class TestCrossPageListMerge:
    def test_detect_arabic_list(self) -> None:
        blocks = [
            _b("1. 第一项", page_id=1, x=0, y=100),
            _b("2. 第二项", page_id=1, x=0, y=200),
            _b("3. 第三项", page_id=1, x=0, y=300),
            _b("4. 第四项跨页", page_id=2, x=0, y=100),  # 编号连续
        ]
        pairs = detect_cross_page_lists(blocks)
        assert len(pairs) == 1
        assert pairs[0][0].text == "3. 第三项"
        assert pairs[0][1].text == "4. 第四项跨页"

    def test_no_merge_when_discontinuous(self) -> None:
        blocks = [
            _b("1. 第一项", page_id=1, x=0, y=100),
            _b("5. 跳号", page_id=2, x=0, y=100),  # 不连续
        ]
        pairs = detect_cross_page_lists(blocks)
        assert len(pairs) == 0


class TestCrossPageTableMerge:
    def test_detect_same_table(self) -> None:
        from docanchor.common.idgen import new_object_id
        from docanchor.common.schema import BoundingBox, PdfObjectRef

        tables = [
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TABLE,
                page_id=1,
                bbox=BoundingBox(x1=0, y1=0, x2=500, y2=100),
                row_count=3,
                col_count=3,
                cell_matrix=[
                    ["阶段", "周期", "交付物"],
                    ["阶段1", "2周", "POC"],
                    ["阶段2", "2周", "闭环"],
                ],
            ),
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TABLE,
                page_id=2,
                bbox=BoundingBox(x1=0, y1=0, x2=500, y2=100),
                row_count=2,
                col_count=3,
                cell_matrix=[
                    ["阶段", "周期", "交付物"],
                    ["阶段3", "1周", "验收"],
                ],
            ),
        ]
        pairs = detect_cross_page_tables([], tables)
        assert len(pairs) == 1

    def test_no_merge_different_columns(self) -> None:
        from docanchor.common.idgen import new_object_id
        from docanchor.common.schema import BoundingBox, PdfObjectRef

        tables = [
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TABLE,
                page_id=1,
                bbox=BoundingBox(x1=0, y1=0, x2=500, y2=100),
                row_count=2,
                col_count=3,
                cell_matrix=[["a", "b", "c"], ["1", "2", "3"]],
            ),
            PdfObjectRef(
                object_id=new_object_id(),
                kind=PdfObjectKind.TABLE,
                page_id=2,
                bbox=BoundingBox(x1=0, y1=0, x2=500, y2=100),
                row_count=2,
                col_count=2,
                cell_matrix=[["x", "y"], ["4", "5"]],
            ),
        ]
        pairs = detect_cross_page_tables([], tables)
        assert len(pairs) == 0