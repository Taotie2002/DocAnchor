"""schema 模块单测：BoundingBox/Block/GlobalNode/DocumentTree。"""

from __future__ import annotations

import pytest

from docanchor.common.schema import (
    Block,
    BlockType,
    BoundingBox,
    DocumentTree,
    GlobalNode,
    ImageExtension,
    ListExtension,
    NativeProvenance,
    NodeType,
    PdfObjectKind,
    PdfObjectRef,
    QaResult,
    ReviewResolution,
    SchemaVersion,
    TableExtension,
)


class TestBoundingBox:
    def test_width_height(self) -> None:
        bb = BoundingBox(x1=0, y1=0, x2=10, y2=20)
        assert bb.width == 10
        assert bb.height == 20
        assert bb.center == (5, 10)

    def test_iou_full_overlap(self) -> None:
        a = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        b = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        assert a.iou(b) == pytest.approx(1.0)

    def test_iou_no_overlap(self) -> None:
        a = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        b = BoundingBox(x1=20, y1=20, x2=30, y2=30)
        assert a.iou(b) == 0.0

    def test_iou_partial(self) -> None:
        a = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        b = BoundingBox(x1=5, y1=5, x2=15, y2=15)
        # inter=5*5=25, union=100+100-25=175
        assert a.iou(b) == pytest.approx(25 / 175)

    def test_overlaps(self) -> None:
        a = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        b = BoundingBox(x1=5, y1=5, x2=15, y2=15)
        assert a.overlaps(b)
        c = BoundingBox(x1=20, y1=0, x2=30, y2=10)
        assert not a.overlaps(c)

    def test_to_list(self) -> None:
        bb = BoundingBox(x1=1, y1=2, x2=3, y2=4)
        assert bb.to_list() == [1, 2, 3, 4]

    def test_frozen(self) -> None:
        bb = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        with pytest.raises(Exception):
            bb.x1 = 5  # type: ignore[misc]


class TestBlock:
    def test_minimal_block(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
            block_type=BlockType.PARAGRAPH,
        )
        assert b.confidence == 0.0
        assert b.text == ""
        assert b.to_source_bbox() == [0, 0, 10, 10]


class TestGlobalNode:
    def test_creation_with_defaults(self) -> None:
        n = GlobalNode(node_id="n1", node_type=NodeType.PARAGRAPH, text="hello")
        assert n.schema_version == SchemaVersion.CURRENT
        assert n.content_hash == ""
        assert n.need_review is False
        assert n.children_ids == []
        assert n.merge_history == []

    def test_recompute_content_hash(self) -> None:
        n = GlobalNode(node_id="n1", node_type=NodeType.PARAGRAPH, text="hello")
        n.recompute_content_hash()
        assert len(n.content_hash) == 16

    def test_record_merge(self) -> None:
        n = GlobalNode(node_id="n1", node_type=NodeType.PARAGRAPH)
        n.record_merge(["b1", "b2"], "cross_page_paragraph")
        assert len(n.merge_history) == 1
        assert "b1" in n.merge_history[0]

    def test_mark_review(self) -> None:
        n = GlobalNode(node_id="n1", node_type=NodeType.PARAGRAPH)
        n.mark_review("low_confidence")
        assert n.need_review
        assert n.review_reason == "low_confidence"

    def test_table_extension(self) -> None:
        n = GlobalNode(
            node_id="t1",
            node_type=NodeType.TABLE,
            table=TableExtension(row_count=2, col_count=2),
        )
        assert n.table is not None
        assert n.table.row_count == 2

    def test_list_extension(self) -> None:
        n = GlobalNode(
            node_id="l1",
            node_type=NodeType.LIST,
            list_ext=ListExtension(list_type="ordered", start_number=1),
        )
        assert n.list_ext is not None
        assert n.list_ext.start_number == 1


class TestDocumentTree:
    def test_walk(self) -> None:
        root = GlobalNode(node_id="root", node_type=NodeType.DOCUMENT_ROOT)
        c1 = GlobalNode(node_id="c1", node_type=NodeType.HEADING)
        c2 = GlobalNode(node_id="c2", node_type=NodeType.HEADING)
        c1.children_ids = ["gc1"]
        gc1 = GlobalNode(node_id="gc1", node_type=NodeType.PARAGRAPH)
        root.children_ids = ["c1", "c2"]

        tree = DocumentTree(
            document_id="d1",
            root=root,
            nodes={"root": root, "c1": c1, "c2": c2, "gc1": gc1},
        )
        walked = tree.walk()
        ids = [n.node_id for n in walked]
        assert "root" in ids
        assert "c1" in ids
        assert "c2" in ids
        assert "gc1" in ids

    def test_tree_hash(self) -> None:
        root = GlobalNode(node_id="root", node_type=NodeType.DOCUMENT_ROOT)
        tree = DocumentTree(document_id="d1", root=root, nodes={"root": root})
        h = tree.tree_hash()
        assert len(h) == 16