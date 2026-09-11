"""评测驱动：对单篇DOCX跑Pipeline，对比标注，计算指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docanchor.common.logger import get_logger
from docanchor.eval.metrics import (
    cer,
    heading_level_accuracy,
    parent_child_f1,
    reading_order_kendall_tau,
    review_ratio,
    table_cell_f1,
)
from docanchor.pipeline import PipelineResult, run_pipeline

logger = get_logger("eval.runner")


@dataclass
class EvalResult:
    """单篇评测结果。"""

    document_id: str
    dirt_level: str
    metrics: dict[str, float] = field(default_factory=dict)
    badcase_count: int = 0
    pipeline_result: dict[str, Any] | None = None


def run_evaluation(
    docx_path: Path,
    annotation: dict[str, Any],
    output_dir: Path | None = None,
) -> EvalResult:
    """对单篇DOCX跑Pipeline并与标注对比。

    Args:
        docx_path: 输入DOCX。
        annotation: 用户标注JSON（评测格式）。
        output_dir: Pipeline产物输出目录（None则使用临时目录）。

    Returns:
        EvalResult：含各指标值与badcase计数。
    """
    if output_dir is None:
        output_dir = docx_path.parent / f"{docx_path.stem}_eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 跑Pipeline
    pipeline_result: PipelineResult = run_pipeline(docx_path, output_dir)
    tree = pipeline_result.document_tree
    if tree is None:
        logger.error(f"Pipeline未生成文档树: {docx_path}")
        return EvalResult(
            document_id=annotation.get("document_id", ""),
            dirt_level=annotation.get("dirt_level", "unknown"),
            metrics={"error": 1.0},
        )

    metrics: dict[str, float] = {}

    # 2) 标题层级准确率（按文本内容匹配，而非ID）
    pred_heading_map: dict[str, dict] = {}
    pred_id_to_text: dict[str, str] = {}
    for n in tree.nodes.values():
        if n.node_type.value == "heading":
            key = (n.text or "").strip()
            if not key:
                continue
            chain = _build_chain(n, tree)
            # 把chain里的id转换为text
            chain_text = [pred_id_to_text.get(pid, pid) for pid in chain]
            pred_heading_map[key] = {
                "id": n.node_id,
                "text": key,
                "global_level": n.global_level,
                "parent_id_chain": chain_text,
            }
            pred_id_to_text[n.node_id] = key

    gt_id_to_parent = {
        a.get("id"): a.get("parent_id") for a in annotation.get("annotations", [])
    }
    gt_id_to_text: dict[str, str] = {}
    gt_heading_map: dict[str, dict] = {}
    for a in annotation.get("annotations", []):
        if a.get("type") != "heading":
            continue
        text = (a.get("text") or "").strip()
        if not text:
            continue
        # 先建立 id->text 映射（占位用id本身）
        gt_id_to_text[a.get("id")] = text
    for a in annotation.get("annotations", []):
        if a.get("type") != "heading":
            continue
        text = (a.get("text") or "").strip()
        # chain 与pipeline格式一致：['root', 'parent1_text', 'parent2_text', ...]
        chain_ids: list[str] = []
        cur = a.get("parent_id")
        # 从parent_id向上递归收集所有祖先id
        ancestors: list[str] = []
        while cur:
            ancestors.append(cur)
            cur = gt_id_to_parent.get(cur)
        # ancestors = [parent, grandparent, ..., top]
        ancestors.reverse()
        # chain = [root] + ancestors
        chain_ids = ["root"] + ancestors
        # id -> text
        chain_text = [gt_id_to_text.get(pid, pid) for pid in chain_ids]
        gt_heading_map[text] = {
            "id": a.get("id"),
            "text": text,
            "global_level": a.get("global_level"),
            "parent_id_chain": chain_text,
        }

    pred_headings = list(pred_heading_map.values())
    gt_headings = list(gt_heading_map.values())
    metrics["heading_level_accuracy"] = heading_level_accuracy(
        pred_headings, gt_headings
    )

    # 3) 章节父子关系F1（基于文本匹配）
    pred_pairs_text: list[tuple[str, str]] = []
    for child_text, child in pred_heading_map.items():
        if child["parent_id_chain"]:
            # parent_id_chain[0] 是直接父标题的text
            parent_text = child["parent_id_chain"][0]
            pred_pairs_text.append((parent_text, child_text))

    gt_pairs_text: list[tuple[str, str]] = []
    for child_text, child in gt_heading_map.items():
        if child.get("parent_id_chain"):
            # parent_id_chain[0] 是直接父标题的text
            parent_text = child["parent_id_chain"][0]
            gt_pairs_text.append((parent_text, child_text))

    # 简化：只看是否有匹配的parent-child对
    metrics["parent_child_f1"] = parent_child_f1(pred_pairs_text, gt_pairs_text)

    # 4) 阅读顺序Kendall τ（基于文本）
    pred_order: list[str] = []
    _flatten_order_text(tree.root, tree, pred_order)
    gt_order = [
        (a.get("text") or a.get("id") or "")
        for a in annotation.get("annotations", [])
    ]
    # 同时去除非heading/paragraph的（如table行）
    metrics["reading_order_kendall_tau"] = reading_order_kendall_tau(
        pred_order, gt_order
    )

    # 5) 表格F1（按内容相似度配对，避免嵌套表顺序错位）
    pred_tables = [
        n.table.cell_matrix
        for n in tree.nodes.values()
        if n.node_type.value == "table" and n.table and n.table.cell_matrix
    ]
    gt_tables = [
        a.get("cell_matrix")
        for a in annotation.get("annotations", [])
        if a.get("type") == "table" and a.get("cell_matrix")
    ]

    if not pred_tables and not gt_tables:
        metrics["table_cell_f1"] = 1.0
    elif not pred_tables or not gt_tables:
        metrics["table_cell_f1"] = 0.0
    else:
        # 用首行文本做配对key
        def _table_key(matrix: list[list[str]]) -> str:
            if not matrix or not matrix[0]:
                return ""
            return "|".join(matrix[0]).strip()

        pred_by_key: dict[str, list[list[str]]] = {}
        for t in pred_tables:
            k = _table_key(t)
            pred_by_key.setdefault(k, []).append(t)
        gt_by_key: dict[str, list[list[str]]] = {}
        for t in gt_tables:
            k = _table_key(t)
            gt_by_key.setdefault(k, []).append(t)

        # 配对：相同key优先
        matched_f1 = 0.0
        matched_count = 0
        for k in list(gt_by_key.keys()):
            if k in pred_by_key:
                gt_list = gt_by_key.pop(k)
                pred_list = pred_by_key.pop(k)
                n = min(len(gt_list), len(pred_list))
                for i in range(n):
                    f1 = table_cell_f1(pred_list[i], gt_list[i])["f1"]
                    matched_f1 += f1
                    matched_count += 1
        # 未匹配的pred/gt按相似度找最佳匹配
        remaining_pred = [t for lst in pred_by_key.values() for t in lst]
        remaining_gt = [t for lst in gt_by_key.values() for t in lst]
        unmatched = max(len(remaining_pred), len(remaining_gt))
        # 简化：未匹配的算0分
        total = matched_count + unmatched
        metrics["table_cell_f1"] = matched_f1 / total if total > 0 else 1.0

    # 6) 关键字段准确率（简化：用annotation中的type计数对比）
    pred_text = " ".join(n.text for n in tree.nodes.values() if n.text)
    gt_text = " ".join(
        a.get("text", "") for a in annotation.get("annotations", [])
    )
    metrics["text_cer"] = cer(pred_text, gt_text) if gt_text else 0.0

    # 7) 复核占比
    metrics["review_ratio"] = review_ratio(tree)

    # 8) badcase计数（粗略：headings准确率<1 + 父子F1<1 + 表格F1<1 视为badcase）
    badcase = 0
    if metrics["heading_level_accuracy"] < 1.0:
        badcase += 1
    if isinstance(metrics["parent_child_f1"], dict):
        if metrics["parent_child_f1"].get("f1", 0) < 1.0:
            badcase += 1
    elif metrics["parent_child_f1"] < 1.0:
        badcase += 1
    if metrics["table_cell_f1"] < 1.0:
        badcase += 1
    if metrics["text_cer"] > 0.05:
        badcase += 1

    return EvalResult(
        document_id=annotation.get("document_id", pipeline_result.document_id),
        dirt_level=annotation.get("dirt_level", "unknown"),
        metrics=metrics,
        badcase_count=badcase,
        pipeline_result=pipeline_result.to_dict(),
    )


def _build_chain(node, tree) -> list[str]:
    """构建从根到当前节点的id链。"""
    chain: list[str] = []
    cur = node
    while cur and cur.parent_id is not None:
        chain.append(cur.parent_id)
        cur = tree.get(cur.parent_id)
    chain.reverse()
    return chain


def _flatten_order(node, tree, out: list[str]) -> None:
    """深度优先遍历填充节点id列表。"""
    for child_id in node.children_ids:
        out.append(child_id)
        child = tree.get(child_id)
        if child:
            _flatten_order(child, tree, out)


def _flatten_order_text(node, tree, out: list[str]) -> None:
    """深度优先遍历填充节点text列表。"""
    for child_id in node.children_ids:
        child = tree.get(child_id)
        if child:
            if child.text:
                out.append(child.text)
            _flatten_order_text(child, tree, out)


__all__ = ["EvalResult", "run_evaluation"]