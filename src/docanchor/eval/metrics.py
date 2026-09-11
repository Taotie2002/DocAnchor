"""评测指标实现（8.2指标计算口径）。

指标：
1. 标题层级准确率（heading_level_accuracy）
2. 章节父子关系F1（parent_child_f1）
3. 阅读顺序Kendall τ（reading_order_kendall_tau）
4. 表格单元格F1（table_cell_f1）
5. 普通文本CER（cer）
6. 人工复核占比（review_ratio）
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any


def heading_level_accuracy(
    predicted: list[dict],
    ground_truth: list[dict],
) -> float:
    """标题层级准确率：全链路径一致（从根到当前标题完整路径匹配）。

    按text匹配（而非id），id在pipeline生成时不可控。

    Args:
        predicted: 预测标题列表，每项含 text, parent_id_chain
        ground_truth: ground truth标题列表，每项含 text, parent_id_chain

    Returns:
        0-1之间的准确率。
    """
    if not ground_truth:
        return 1.0

    # text -> chain
    gt_chains = {h.get("text", ""): h.get("parent_id_chain", []) for h in ground_truth}
    pred_chains = {h.get("text", ""): h.get("parent_id_chain", []) for h in predicted}

    # parent_id_chain 中的元素也是id，需要转换为text
    def _resolve_chain(chain: list[str], id_to_text: dict[str, str]) -> list[str]:
        return [id_to_text.get(pid, pid) for pid in chain]

    # id -> text映射
    pred_id_to_text = {h.get("id", ""): h.get("text", "") for h in predicted}
    gt_id_to_text = {h.get("id", ""): h.get("text", "") for h in ground_truth}

    # 把所有chain转换为text序列
    gt_chains_text = {
        text: _resolve_chain(chain, gt_id_to_text)
        for text, chain in gt_chains.items()
    }
    pred_chains_text = {
        text: _resolve_chain(chain, pred_id_to_text)
        for text, chain in pred_chains.items()
    }

    correct = 0
    for gt_text, gt_chain in gt_chains_text.items():
        if gt_text in pred_chains_text and pred_chains_text[gt_text] == gt_chain:
            correct += 1
    return correct / len(gt_chains_text) if gt_chains_text else 1.0


def parent_child_f1(
    predicted: list[tuple[str, str]],
    ground_truth: list[tuple[str, str]],
) -> dict[str, float]:
    """章节父子关系F1。

    Args:
        predicted: 预测的(parent_id, child_id)对。
        ground_truth: ground truth(parent_id, child_id)对。

    Returns:
        {"precision", "recall", "f1"}
    """
    p_set = set(predicted)
    g_set = set(ground_truth)

    if not p_set and not g_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    tp = len(p_set & g_set)
    precision = tp / len(p_set) if p_set else 0.0
    recall = tp / len(g_set) if g_set else 0.0
    f1 = (
 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def reading_order_kendall_tau(
    predicted: list[str],
    ground_truth: list[str],
) -> float:
    """阅读顺序Kendall τ秩相关系数。

    Args:
        predicted: 预测的节点id序列。
        ground_truth: ground truth节点id序列。

    Returns:
        Kendall τ（-1到1，越接近1表示顺序越一致）。
    """
    # 仅在两者都包含的节点上计算
    common = set(predicted) & set(ground_truth)
    if len(common) < 2:
        return 1.0

    gt_rank = {nid: i for i, nid in enumerate(ground_truth) if nid in common}
    pred_order = [nid for nid in predicted if nid in common]

    # 计算Kendall τ：concordant-discordant对数 / 总对数
    concordant = 0
    discordant = 0
    for a, b in combinations(pred_order, 2):
        if a not in gt_rank or b not in gt_rank:
            continue
        gt_a, gt_b = gt_rank[a], gt_rank[b]
        if gt_a < gt_b:
            # GT中a在b前，预测也是a在b前 → concordant
            if pred_order.index(a) < pred_order.index(b):
                concordant += 1
            else:
                discordant += 1
        else:
            if pred_order.index(a) > pred_order.index(b):
                concordant += 1
            else:
                discordant += 1

    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / total


def table_cell_f1(
    predicted: list[list[str]],
    ground_truth: list[list[str]],
) -> dict[str, float]:
    """表格单元格F1（含合并单元格/空单元格）。"""
    pred_cells = _flatten_cells(predicted)
    gt_cells = _flatten_cells(ground_truth)

    if not pred_cells and not gt_cells:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred_cells or not gt_cells:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    # 用Counter统计
    pred_counter = Counter(pred_cells)
    gt_counter = Counter(gt_cells)

    tp = sum((pred_counter & gt_counter).values())
    precision = tp / len(pred_cells)
    recall = tp / len(gt_cells)
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def _flatten_cells(matrix: list[list[str]]) -> list[str]:
    """展平表格矩阵为单元格列表。"""
    cells = []
    for row in matrix:
        for cell in row:
            # 归一化：合并连续空白（处理"API 网关" vs "API网关"）
            normalized = " ".join(cell.split())
            cells.append(normalized.strip())
    return cells


def _normalize_text_for_cer(text: str) -> str:
    """归一化文本用于CER：全角→半角、统一空白等。"""
    import unicodedata

    # 全角→半角映射
    fullwidth_to_halfwidth = {
        "，": ",", "。": ".", "！": "!", "？": "?",
        "；": ";", "：": ":", "（": "(", "）": ")",
        "【": "[", "】": "]", "「": '"', "」": '"',
        "、": ",", "～": "~", "　": " ",  # 全角空格→半角空格
    }
    out = []
    for ch in text:
        # 全角字符（U+FF01-U+FF5E）→ 半角（U+0021-U+007E）
        if "\uff01" <= ch <= "\uff5e":
            out.append(chr(ord(ch) - 0xFEE0))
        elif ch in fullwidth_to_halfwidth:
            out.append(fullwidth_to_halfwidth[ch])
        else:
            out.append(ch)
    # 合并连续空白
    return " ".join("".join(out).split())


def cer(predicted: str, ground_truth: str) -> float:
    """中文字符粒度CER（Character Error Rate）。

    使用编辑距离/参考长度。在比较前对两个文本做全半角归一化。
    """
    if not ground_truth:
        return 1.0 if predicted else 0.0
    if not predicted:
        return 1.0

    # 全半角归一化
    p_norm = _normalize_text_for_cer(predicted)
    g_norm = _normalize_text_for_cer(ground_truth)

    # 动态规划计算编辑距离
    m, n = len(p_norm), len(g_norm)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if p_norm[i - 1] == g_norm[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],  # 删除
                    dp[i][j - 1],  # 插入
                    dp[i - 1][j - 1],  # 替换
                )
    return dp[m][n] / n


def review_ratio(
    predicted_tree,
) -> float:
    """人工复核占比：need_review节点数 / 总节点数。"""
    if not predicted_tree or not predicted_tree.nodes:
        return 0.0
    total = len(predicted_tree.nodes)
    review = sum(1 for n in predicted_tree.nodes.values() if n.need_review)
    return review / total


__all__ = [
    "heading_level_accuracy",
    "parent_child_f1",
    "reading_order_kendall_tau",
    "table_cell_f1",
    "cer",
    "review_ratio",
]