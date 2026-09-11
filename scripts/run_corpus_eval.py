#!/usr/bin/env python
"""批量评测脚本：跑全语料库并生成报告与badcase分类。

用法：
    PYTHONPATH=src .venv/bin/python scripts/run_corpus_eval.py \
        --corpus tests/fixtures/corpus \
        --annotations tests/fixtures/annotations \
        --output eval_run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许脚本独立运行
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docanchor.eval.cli import (
    generate_badcase_classification,
    run_corpus_evaluation,
)
from docanchor.eval.report import build_report
from docanchor.common.logger import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="批量评测DOCX语料库")
    parser.add_argument("--corpus", type=Path, default=Path("tests/fixtures/corpus"))
    parser.add_argument("--annotations", type=Path, default=Path("tests/fixtures/annotations"))
    parser.add_argument("--output", type=Path, default=Path("eval_run"))
    args = parser.parse_args()

    setup_logging()
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.corpus.exists():
        print(f"错误: 语料目录不存在: {args.corpus}")
        return 1
    if not args.annotations.exists():
        print(f"错误: 标注目录不存在: {args.annotations}")
        return 1

    # 1) 跑评测
    results = run_corpus_evaluation(args.corpus, args.annotations, output_dir)
    if not results:
        print("无评测结果")
        return 1

    # 2) 生成汇总报告
    report = build_report(results, output_path=output_dir / "report.json")
    print("\n=== 汇总报告 ===")
    import json
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # 3) 生成badcase分类
    badcase = generate_badcase_classification(
        results, output_path=output_dir / "badcase.json"
    )
    print("\n=== Badcase分类 ===")
    print(json.dumps(badcase["badcase_categories"], indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())