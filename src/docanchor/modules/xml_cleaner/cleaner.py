"""XML级元数据清洗主入口（3.1.3）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.rules import (
    ALL_RULES,
    accept_all_revisions,
    freeze_fields,
    remove_strikethrough,
    remove_vanish,
    strip_comments,
    strip_macros,
)

logger = get_logger("xml_cleaner")

RuleFn = Callable[[Path, Path], int]


@dataclass
class CleaningReport:
    """清洗报告：每条规则的命中数。"""

    input_path: str = ""
    output_path: str = ""
    total_changes: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


def default_rules() -> list[RuleFn]:
    """默认启用全部6条规则。

    返回新的列表，调用方可按需增删。
    """
    return list(ALL_RULES)


def clean_docx(
    input_path: Path,
    output_path: Path | None = None,
    *,
    rules: list[RuleFn] | None = None,
) -> CleaningReport:
    """清洗DOCX中的XML元数据。

    Args:
        input_path: 原始DOCX路径。
        output_path: 清洗后输出路径，默认覆盖输入。
        rules: 自定义规则列表，默认6条全开。

    Returns:
        CleaningReport：各规则命中统计。
    """
    import time

    start = time.time()
    if output_path is None:
        output_path = input_path

    if rules is None:
        rules = default_rules()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = CleaningReport(
        input_path=str(input_path),
        output_path=str(output_path),
    )

    current = input_path
    for rule in rules:
        try:
            changes = rule(current, output_path)
            report.by_rule[rule.__name__] = changes
            report.total_changes += changes
            current = output_path  # 后续规则基于上一步输出
            logger.info(f"规则 {rule.__name__} 命中 {changes} 处")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"规则 {rule.__name__} 执行异常，跳过: {e}")
            report.by_rule[rule.__name__] = 0

    report.elapsed_seconds = time.time() - start
    logger.info(
        f"清洗完成: 共 {report.total_changes} 处变更，"
        f"耗时 {report.elapsed_seconds:.2f}s"
    )
    return report


__all__ = [
    "CleaningReport",
    "RuleFn",
    "clean_docx",
    "default_rules",
    # 便捷重导出
    "accept_all_revisions",
    "freeze_fields",
    "remove_strikethrough",
    "remove_vanish",
    "strip_comments",
    "strip_macros",
]