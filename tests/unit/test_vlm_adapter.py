"""VLM Adapter 单测。"""

from __future__ import annotations

from pathlib import Path

import fitz

from docanchor.common.idgen import reset_counters
from docanchor.common.schema import Block, BlockType, BoundingBox
from docanchor.modules.vlm_adapter.coordinate_align import align_coordinates, normalize_bbox
from docanchor.modules.vlm_adapter.filter import filter_blocks
from docanchor.modules.vlm_adapter.normalizer import normalize_block_type
from docanchor.modules.vlm_adapter.validator import validate_blocks


def _make_test_pdf(tmp_path: Path) -> Path:
    """生成2页测试PDF。"""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    try:
        for i in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((100, 100), f"Page {i + 1}")
        doc.save(pdf_path)
    finally:
        doc.close()
    return pdf_path


class TestMockVLMProvider:
    def setup_method(self) -> None:
        reset_counters()

    def test_parse_returns_pages(self, tmp_path: Path) -> None:
        from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider

        pdf = _make_test_pdf(tmp_path)
        provider = MockVLMProvider()
        pages = provider.parse(pdf)
        assert len(pages) == 2
        for page_blocks in pages:
            assert len(page_blocks) >= 1
            assert page_blocks[0].block_type == BlockType.PARAGRAPH

    def test_version(self) -> None:
        from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider

        v = MockVLMProvider().version()
        assert v.startswith("mock-")


class TestNormalizer:
    def test_known_types(self) -> None:
        assert normalize_block_type("text") == BlockType.PARAGRAPH
        assert normalize_block_type("title") == BlockType.TITLE
        assert normalize_block_type("table") == BlockType.TABLE
        assert normalize_block_type("figure") == BlockType.IMAGE

    def test_fuzzy_match(self) -> None:
        # 包含子串也能匹配
        assert normalize_block_type("text_block") == BlockType.PARAGRAPH
        assert normalize_block_type("figure_caption") == BlockType.CAPTION

    def test_unknown_defaults_to_paragraph(self) -> None:
        assert normalize_block_type("weird_type") == BlockType.PARAGRAPH
        assert normalize_block_type("") == BlockType.PARAGRAPH

    def test_case_insensitive(self) -> None:
        assert normalize_block_type("TITLE") == BlockType.TITLE
        assert normalize_block_type("Table") == BlockType.TABLE


class TestCoordinateAlign:
    def test_already_aligned(self) -> None:
        bbox = [100.0, 200.0, 300.0, 400.0]
        aligned = align_coordinates(bbox, page_size=(595, 842))
        assert aligned == [100.0, 200.0, 300.0, 400.0]

    def test_percentage_to_points(self) -> None:
        bbox = [0.1, 0.2, 0.5, 0.4]
        aligned = align_coordinates(bbox, page_size=(600, 800))
        assert aligned == [60.0, 160.0, 300.0, 320.0]

    def test_swap_axes(self) -> None:
        # top-left 原点：y1=100（在顶部）, y2=300（更靠下）
        bbox = [100.0, 100.0, 300.0, 300.0]
        aligned = align_coordinates(bbox, page_size=(595, 842))
        # y轴应翻转：原y1=100(顶) -> 翻后y1=842-100=742, y2=842-300=542
        # 翻转后 y1 > y2, 应当再swap使 y1 < y2
        assert aligned[1] < aligned[3]

    def test_clip_to_page(self) -> None:
        bbox = [-100.0, -100.0, 1000.0, 1000.0]
        aligned = align_coordinates(bbox, page_size=(595, 842))
        assert aligned[0] >= 0
        assert aligned[1] >= 0
        assert aligned[2] <= 595
        assert aligned[3] <= 842

    def test_swap_left_right(self) -> None:
        bbox = [300.0, 100.0, 100.0, 200.0]  # x1 > x2
        aligned = align_coordinates(bbox, page_size=(595, 842))
        assert aligned[0] < aligned[2]

    def test_normalize_bbox_returns_dataclass(self) -> None:
        bb = normalize_bbox([0.1, 0.2, 0.5, 0.4], page_size=(600, 800))
        assert isinstance(bb, BoundingBox)
        assert bb.x1 == 60.0


class TestValidator:
    def test_title_needs_local_level(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=20),
            block_type=BlockType.TITLE,
            local_level=None,
        )
        result = validate_blocks([b])
        assert len(result) == 1
        # local_level被强制设置为1，confidence降低
        assert result[0].local_level == 1
        assert result[0].confidence <= 0.5

    def test_filter_invalid_bbox(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=0, y2=0),  # 零面积
            block_type=BlockType.PARAGRAPH,
            text="x",
        )
        result = validate_blocks([b])
        assert len(result) == 0

    def test_deduplication(self) -> None:
        bb = BoundingBox(x1=10, y1=10, x2=100, y2=20)
        b1 = Block(page_id=1, block_id="a", bbox=bb, block_type=BlockType.PARAGRAPH, text="t")
        b2 = Block(page_id=1, block_id="b", bbox=bb, block_type=BlockType.PARAGRAPH, text="t")
        result = validate_blocks([b1, b2])
        assert len(result) == 1


class TestFilterBlocks:
    def test_keep_valid_block(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            block_type=BlockType.PARAGRAPH,
            text="hello",
        )
        result = filter_blocks([b], page_size=(595, 842))
        assert len(result) == 1

    def test_filter_out_of_bounds(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=1000, y1=1000, x2=1100, y2=1100),  # 越界
            block_type=BlockType.PARAGRAPH,
            text="x",
        )
        result = filter_blocks([b], page_size=(595, 842))
        assert len(result) == 0

    def test_filter_empty_text_non_special(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            block_type=BlockType.PARAGRAPH,
            text="",
        )
        result = filter_blocks([b], page_size=(595, 842))
        assert len(result) == 0  # 空文本paragraph被过滤

    def test_keep_empty_image(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            block_type=BlockType.IMAGE,
            text="",
        )
        result = filter_blocks([b], page_size=(595, 842))
        assert len(result) == 1  # 空文本image保留

    def test_filter_tiny_block(self) -> None:
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=0.1, y2=0.1),
            block_type=BlockType.PARAGRAPH,
            text="tiny",
        )
        result = filter_blocks([b], page_size=(595, 842), min_area=1.0)
        assert len(result) == 0

    def test_filter_title_invalid_level(self) -> None:
        # Block构造时local_level受Pydantic约束(1-6)，
        # 但filter_blocks应能过滤传入的非法值。
        # 这里通过Block构造不传local_level，构造后绕过Pydantic直接修改为None：
        b = Block(
            page_id=1,
            block_id="b1",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            block_type=BlockType.TITLE,
            local_level=1,
            text="bad title",
        )
        # 模拟Provider输出了非法local_level（None）
        object.__setattr__(b, "local_level", None)
        result = filter_blocks([b], page_size=(595, 842))
        assert len(result) == 0


class TestAdapterPipeline:
    def test_e2e_with_synthetic_pdf(self, tmp_path: Path) -> None:
        """端到端：PDF → VLM Adapter → 标准Block列表。"""
        from docanchor.modules.vlm_adapter import parse_pdf_with_vlm

        pdf = _make_test_pdf(tmp_path)
        pages = parse_pdf_with_vlm(pdf)
        assert len(pages) == 2
        total_blocks = sum(len(p) for p in pages)
        assert total_blocks >= 2

        for page_blocks in pages:
            for b in page_blocks:
                assert b.bbox.x1 >= 0
                assert b.bbox.y1 >= 0
                assert b.vlm_model_version.startswith(("mock-", "mineru-", "fallback-"))

    def test_e2e_with_url(self) -> None:
        """端到端：URL → VLM Adapter → 标准Block列表（mocked MinerU parse_url）。"""
        from docanchor.common.idgen import new_block_id
        from docanchor.common.schema import Block, BlockType, BoundingBox
        from docanchor.modules.vlm_adapter.adapter import VLMAdapter

        # 直接mock provider的parse_url返回预构造的Block列表
        def fake_parse_url(url):
            return [
                [
                    Block(
                        page_id=1,
                        block_id=new_block_id(),
                        bbox=BoundingBox(x1=100, y1=100, x2=500, y2=130),
                        block_type=BlockType.TITLE,
                        local_level=1,
                        text="Online Paper",
                        confidence=0.9,
                        vlm_model_version="mineru-vlm-api",
                    ),
                ],
                [
                    Block(
                        page_id=2,
                        block_id=new_block_id(),
                        bbox=BoundingBox(x1=100, y1=150, x2=500, y2=200),
                        block_type=BlockType.PARAGRAPH,
                        text="Body text",
                        confidence=0.9,
                        vlm_model_version="mineru-vlm-api",
                    ),
                ],
            ]

        # 构造一个stub provider
        class StubProvider:
            name = "stub"
            def parse(self, pdf_path):
                return []
            def version(self):
                return "stub-0.1.0"
            parse_url = staticmethod(fake_parse_url)

        adapter = VLMAdapter(StubProvider())
        pages = adapter.parse_pdf("https://example.com/paper.pdf")

        assert len(pages) == 2
        all_blocks = [b for p in pages for b in p]
        titles = [b for b in all_blocks if b.block_type.value == "title"]
        assert len(titles) == 1
        assert titles[0].text == "Online Paper"
        assert titles[0].local_level == 1
        assert titles[0].vlm_model_version == "mineru-vlm-api"