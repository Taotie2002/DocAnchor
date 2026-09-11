"""LLM 任务契约（3.6）。"""

from docanchor.llm.tasks.cross_page_table import judge_cross_page_table
from docanchor.llm.tasks.heading_level import normalize_heading_levels
from docanchor.llm.tasks.semantic_check import semantic_check_text

__all__ = [
    "judge_cross_page_table",
    "normalize_heading_levels",
    "semantic_check_text",
]