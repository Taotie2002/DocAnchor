"""评测模块单测。"""

from __future__ import annotations

from docanchor.eval.metrics import (
    cer,
    heading_level_accuracy,
    parent_child_f1,
    reading_order_kendall_tau,
    review_ratio,
    table_cell_f1,
)
from docanchor.eval.report import build_report
from docanchor.eval.runner import EvalResult


class TestCer:
    def test_identical(self) -> None:
        assert cer("hello", "hello") == 0.0

    def test_empty_reference(self) -> None:
        assert cer("hello", "") == 1.0

    def test_empty_prediction(self) -> None:
        assert cer("", "hello") == 1.0

    def test_one_char_diff(self) -> None:
        # "hello" -> "hallo" = 1 edit / 5 = 0.2
        assert cer("hallo", "hello") == pytest_approx(0.2)


def pytest_approx(val):
    class A:
        def __init__(self, v):
            self.v = v

        def __eq__(self, other):
            return abs(other - self.v) < 1e-6

    return A(val)


class TestHeadingLevelAccuracy:
    def test_perfect(self) -> None:
        gt = [
            {"id": "h1", "text": "t1", "parent_id_chain": []},
            {"id": "h2", "text": "t2", "parent_id_chain": ["h1"]},
        ]
        pred = [
            {"id": "h1", "text": "t1", "parent_id_chain": []},
            {"id": "h2", "text": "t2", "parent_id_chain": ["h1"]},
        ]
        assert heading_level_accuracy(pred, gt) == 1.0

    def test_partial(self) -> None:
        gt = [
            {"id": "h1", "text": "t1", "parent_id_chain": []},
            {"id": "h2", "text": "t2", "parent_id_chain": ["h1"]},
            {"id": "h3", "text": "t3", "parent_id_chain": ["h1", "h2"]},
        ]
        pred = [
            {"id": "h1", "text": "t1", "parent_id_chain": []},
            {"id": "h2", "text": "t2", "parent_id_chain": ["h1"]},
            {"id": "h3", "text": "t3", "parent_id_chain": ["h2"]},  # 错误
        ]
        acc = heading_level_accuracy(pred, gt)
        # h1 + h2 正确（2/3 = 0.667）
        assert 0.6 < acc < 0.7

    def test_no_match(self) -> None:
        """text完全不同则准确率=0。"""
        gt = [{"id": "h1", "text": "GT标题", "parent_id_chain": []}]
        pred = [{"id": "h1", "text": "预测标题", "parent_id_chain": []}]
        # text不匹配，无法对齐
        assert heading_level_accuracy(pred, gt) == 0.0


class TestParentChildF1:
    def test_perfect(self) -> None:
        pairs = [("a", "b"), ("b", "c")]
        result = parent_child_f1(pairs, pairs)
        assert result["f1"] == 1.0

    def test_no_match(self) -> None:
        result = parent_child_f1([("a", "b")], [("c", "d")])
        assert result["f1"] == 0.0

    def test_partial(self) -> None:
        pred = [("a", "b"), ("a", "c")]
        gt = [("a", "b"), ("a", "d")]
        result = parent_child_f1(pred, gt)
        # tp=1, p=1/2=0.5, r=1/2=0.5, f1=0.5
        assert abs(result["f1"] - 0.5) < 1e-6


class TestKendallTau:
    def test_identical(self) -> None:
        order = ["a", "b", "c"]
        assert reading_order_kendall_tau(order, order) == 1.0

    def test_reversed(self) -> None:
        order = ["a", "b", "c"]
        reversed_ = ["c", "b", "a"]
        assert reading_order_kendall_tau(order, reversed_) == -1.0

    def test_partial(self) -> None:
        order = ["a", "b", "c", "d"]
        gt = ["a", "b", "d", "c"]  # 一对错位
        # 计算：concordant=5, discordant=1, tau = (5-1)/(5+1) = 0.667
        result = reading_order_kendall_tau(order, gt)
        assert 0.5 < result < 0.8


class TestTableCellF1:
    def test_identical(self) -> None:
        matrix = [["a", "b"], ["c", "d"]]
        result = table_cell_f1(matrix, matrix)
        assert result["f1"] == 1.0

    def test_partial(self) -> None:
        matrix_a = [["a", "b"], ["c", "d"]]
        matrix_b = [["a", "b"], ["c", "e"]]
        # 4 cells, 3 match -> p=3/4=0.75, r=3/4=0.75, f1=0.75
        result = table_cell_f1(matrix_a, matrix_b)
        assert abs(result["f1"] - 0.75) < 1e-6


class TestReviewRatio:
    def test_no_review(self) -> None:
        # 空树无node：0
        class FakeTree:
            nodes = {}
        assert review_ratio(FakeTree()) == 0.0

    def test_some_review(self) -> None:
        from dataclasses import dataclass
        from typing import Any

        @dataclass
        class FakeNode:
            need_review: bool
            pass

        class FakeTree:
            nodes: dict[str, Any] = {
                "n1": FakeNode(False),
                "n2": FakeNode(True),
                "n3": FakeNode(False),
                "n4": FakeNode(True),
            }

        assert review_ratio(FakeTree()) == 0.5


class TestBuildReport:
    def test_empty(self) -> None:
        report = build_report([])
        assert "summary" in report

    def test_single(self) -> None:
        r = EvalResult(
            document_id="d1",
            dirt_level="medium",
            metrics={"heading_level_accuracy": 0.9},
            badcase_count=1,
        )
        report = build_report([r])
        assert report["total"] == 1
        assert "medium" in report["by_dirt_level"]

    def test_handles_dict_metrics(self) -> None:
        """parent_child_f1返回dict时report正确处理。"""
        r = EvalResult(
            document_id="d1",
            dirt_level="medium",
            metrics={
                "heading_level_accuracy": 0.9,
                "parent_child_f1": {"precision": 0.8, "recall": 0.7, "f1": 0.75},
            },
            badcase_count=0,
        )
        report = build_report([r])
        assert report["by_dirt_level"]["medium"]["metrics_avg"]["parent_child_f1"] == 0.75


class TestHeadingLevelAccuracyRootHandling:
    """测试 root 哨兵处理：gt用None作parent_id，pred用'root'。"""

    def test_root_normalization(self) -> None:
        # 构造pred: root->一级->二级
        pred = [
            {"id": "p1", "text": "h1", "global_level": 1, "parent_id_chain": ["root"]},
            {"id": "p2", "text": "h2", "global_level": 2, "parent_id_chain": ["root", "h1"]},
        ]
        # 构造gt: 同样的结构（应被正确对齐）
        gt = [
            {"id": "g1", "text": "h1", "global_level": 1, "parent_id_chain": ["root"]},
            {"id": "g2", "text": "h2", "global_level": 2, "parent_id_chain": ["root", "h1"]},
        ]
        assert heading_level_accuracy(pred, gt) == 1.0

    def test_chain_mismatch(self) -> None:
        pred = [
            {"id": "p1", "text": "h1", "global_level": 1, "parent_id_chain": ["root"]},
            {"id": "p2", "text": "h2", "global_level": 2, "parent_id_chain": ["root", "h1"]},
        ]
        gt = [
            {"id": "g1", "text": "h1", "global_level": 1, "parent_id_chain": ["root"]},
            # h2的父应该是h1但gt里说成h1.1（chain错位）
            {"id": "g2", "text": "h2", "global_level": 2, "parent_id_chain": ["root", "h1.1"]},
        ]
        # h1正确(1/2=0.5), h2 chain不一致
        assert heading_level_accuracy(pred, gt) == 0.5