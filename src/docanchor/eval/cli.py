"""评测批量执行器（CLI入口辅助函数）。

提供：
- run_corpus_evaluation(corpus_dir, annotation_dir, output_dir)：批量跑评测
- generate_badcase_classification(eval_results)：按指标异常分类badcase
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from docanchor.common.logger import get_logger
from docanchor.eval.report import build_report
from docanchor.eval.runner import EvalResult, run_evaluation

logger = get_logger("eval.cli")


def run_corpus_evaluation(
    corpus_dir: Path,
    annotation_dir: Path,
    output_dir: Path,
) -> list[EvalResult]:
    """对整个语料库跑评测。

    Args:
        corpus_dir: 包含 docx 文件的目录（命名：dirty_{level}.docx）。
        annotation_dir: 包含标注JSON的目录（命名：dirty_{level}_annotations.json）。
        output_dir: 评测结果输出目录。

    Returns:
        EvalResult列表。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[EvalResult] = []
    for docx_path in sorted(corpus_dir.glob("*.docx")):
        stem = docx_path.stem  # e.g., dirty_light
        ann_path = annotation_dir / f"{stem}_annotations.json"
        if not ann_path.exists():
            logger.warning(f"未找到标注: {ann_path}, 跳过 {docx_path.name}")
            continue
        annotation = json.loads(ann_path.read_text(encoding="utf-8"))
        out_dir = output_dir / docx_path.stem
        logger.info(f"评测: {docx_path.name}")
        try:
            result = run_evaluation(docx_path, annotation, output_dir=out_dir)
            results.append(result)
        except Exception as e:  # noqa: BLE001
            logger.error(f"评测失败 {docx_path.name}: {e}")
    return results


def generate_badcase_classification(
    eval_results: list[EvalResult],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """按模块维度分类badcase。

    分类：
    - heading_recall_loss：标题召回损失（heading_level_accuracy<0.8）
    - parent_child_disorder：父子关系错乱（parent_child_f1<0.7）
    - reading_order_error：阅读顺序错乱（kendall_tau<0.7）
    - table_structure_damage：表格结构损坏（table_cell_f1<0.7）
    - text_recognition_error：文字识别错误（text_cer>0.10）
    - review_overload：人工复核占比过高（review_ratio>0.20）

    Args:
        eval_results: 评测结果列表。
        output_path: 可选，输出JSON路径。

    Returns:
        分类汇总。
    """
    badcase_types = {
        "heading_recall_loss": lambda m: m.get("heading_level_accuracy", 1) < 0.8,
        "parent_child_disorder": lambda m: _f1(m.get("parent_child_f1")) < 0.7,
        "reading_order_error": lambda m: m.get("reading_order_kendall_tau", 1) < 0.7,
        "table_structure_damage": lambda m: m.get("table_cell_f1", 1) < 0.7,
        "text_recognition_error": lambda m: m.get("text_cer", 0) > 0.10,
        "review_overload": lambda m: m.get("review_ratio", 0) > 0.20,
    }

    classification: dict[str, list[dict]] = defaultdict(list)
    for r in eval_results:
        # 把dict类型的f1标准化
        normalized_metrics = dict(r.metrics)
        pc = normalized_metrics.get("parent_child_f1")
        if isinstance(pc, dict):
            normalized_metrics["parent_child_f1_f1"] = pc.get("f1", 0)
        for bc_type, predicate in badcase_types.items():
            if predicate(r.metrics):
                classification[bc_type].append(
                    {
                        "document_id": r.document_id,
                        "dirt_level": r.dirt_level,
                        "metrics": r.metrics,
                    }
                )

    summary = {
        "total_documents": len(eval_results),
        "badcase_categories": {
            bc_type: len(items) for bc_type, items in classification.items()
        },
        "details": dict(classification),
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"Badcase分类: {output_path}")

    return summary


def _f1(metric_value: Any) -> float:
    """获取dict的f1，否则原值。"""
    if isinstance(metric_value, dict):
        return metric_value.get("f1", 0)
    return metric_value if isinstance(metric_value, (int, float)) else 0


__all__ = ["run_corpus_evaluation", "generate_badcase_classification"]