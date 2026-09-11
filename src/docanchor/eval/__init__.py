"""评测框架（8.1/8.2/8.3）。"""

from docanchor.eval.metrics import (
    cer,
    heading_level_accuracy,
    parent_child_f1,
    reading_order_kendall_tau,
    table_cell_f1,
)
from docanchor.eval.runner import run_evaluation
from docanchor.eval.report import build_report

__all__ = [
    "cer",
    "heading_level_accuracy",
    "parent_child_f1",
    "reading_order_kendall_tau",
    "table_cell_f1",
    "run_evaluation",
    "build_report",
]