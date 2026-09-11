"""评测报告：批量汇总+分脏度统计。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from docanchor.common.logger import get_logger
from docanchor.eval.runner import EvalResult

logger = get_logger("eval.report")


def build_report(results: list[EvalResult], output_path: Path | None = None) -> dict[str, Any]:
    """汇总批量评测结果，按脏度分桶统计。

    Args:
        results: 单篇评测结果列表。
        output_path: 可选，输出报告JSON路径。

    Returns:
        报告字典。
    """
    if not results:
        return {"summary": "无评测结果"}

    by_level: dict[str, list[EvalResult]] = defaultdict(list)
    for r in results:
        by_level[r.dirt_level].append(r)

    summary: dict[str, Any] = {
        "total": len(results),
        "by_dirt_level": {},
    }

    for level, rs in by_level.items():
        if not rs:
            continue
        n = len(rs)

        def _avg(metric_name: str, default: float = 0.0) -> float:
            """聚合 metric（兼容 dict 与 scalar）。"""
            vals = []
            for r in rs:
                v = r.metrics.get(metric_name, default)
                if isinstance(v, dict):
                    v = v.get("f1", default)
                vals.append(v)
            return sum(vals) / n

        avg = {
            "heading_level_accuracy": _avg("heading_level_accuracy"),
            "parent_child_f1": _avg("parent_child_f1"),
            "reading_order_kendall_tau": _avg("reading_order_kendall_tau"),
            "table_cell_f1": _avg("table_cell_f1"),
            "text_cer": _avg("text_cer"),
            "review_ratio": _avg("review_ratio"),
        }
        summary["by_dirt_level"][level] = {
            "count": n,
            "metrics_avg": avg,
            "badcase_total": sum(r.badcase_count for r in rs),
        }

    # 写文件
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"评测报告: {output_path}")

    return summary


__all__ = ["build_report"]