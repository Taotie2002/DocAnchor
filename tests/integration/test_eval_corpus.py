"""批量评测端到端集成测试。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from docanchor.eval.cli import (
    generate_badcase_classification,
    run_corpus_evaluation,
)
from docanchor.eval.report import build_report


class TestCorpusEvaluation:
    """对合成语料库跑完整评测流程。"""

    def test_run_corpus_evaluation(self, tmp_path: Path) -> None:
        corpus_dir = Path("tests/fixtures/corpus")
        ann_dir = Path("tests/fixtures/annotations")
        output_dir = tmp_path / "eval"

        if not corpus_dir.exists() or not ann_dir.exists():
            pytest.skip("合成语料库不存在，跳过")

        results = run_corpus_evaluation(corpus_dir, ann_dir, output_dir)
        assert len(results) >= 1
        for r in results:
            assert r.document_id != ""
            assert r.dirt_level in ("light", "medium", "heavy")

    def test_generate_badcase_classification(self, tmp_path: Path) -> None:
        corpus_dir = Path("tests/fixtures/corpus")
        ann_dir = Path("tests/fixtures/annotations")
        if not corpus_dir.exists() or not ann_dir.exists():
            pytest.skip("合成语料库不存在，跳过")

        results = run_corpus_evaluation(corpus_dir, ann_dir, tmp_path / "eval")
        bc_path = tmp_path / "badcase.json"
        summary = generate_badcase_classification(results, output_path=bc_path)
        assert "total_documents" in summary
        assert "badcase_categories" in summary
        assert bc_path.exists()

    def test_build_report(self, tmp_path: Path) -> None:
        corpus_dir = Path("tests/fixtures/corpus")
        ann_dir = Path("tests/fixtures/annotations")
        if not corpus_dir.exists() or not ann_dir.exists():
            pytest.skip("合成语料库不存在，跳过")

        results = run_corpus_evaluation(corpus_dir, ann_dir, tmp_path / "eval")
        report_path = tmp_path / "report.json"
        report = build_report(results, output_path=report_path)
        assert "total" in report
        assert "by_dirt_level" in report
        assert report["total"] == len(results)
        assert report_path.exists()