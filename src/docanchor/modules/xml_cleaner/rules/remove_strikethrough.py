"""规则3：删除删除线文本（3.1.3）。

非修订模式的手动删除线 — 即 rPr 中含 w:strike 或 w:dstrike 的 run。
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.docx_utils import W, load_docx_xml, save_docx_xml

logger = get_logger("xml_cleaner.remove_strikethrough")


def remove_strikethrough(input_path: Path, output_path: Path) -> int:
    """删除所有手动删除线 run。"""
    from docanchor.modules.xml_cleaner.rules.accept_revisions import _list_text_parts

    changes = 0
    modifications: dict[str, etree._ElementTree] = {}

    for part in _list_text_parts(input_path):
        try:
            tree = load_docx_xml(input_path, part)
        except KeyError:
            continue
        root = tree.getroot()
        changes += _process_tree(root)
        modifications[part] = tree

    if modifications:
        save_docx_xml(input_path, output_path, modifications)
    return changes


def _process_tree(root: etree._Element) -> int:
    """遍历所有 w:r，若 rPr 含 w:strike / w:dstrike 则删除整个 run。"""
    changes = 0
    runs_to_remove: list[etree._Element] = []
    for run in root.iter(f"{W}r"):
        rpr = run.find(f"{W}rPr")
        if rpr is None:
            continue
        if rpr.find(f"{W}strike") is not None or rpr.find(f"{W}dstrike") is not None:
            runs_to_remove.append(run)
    for run in runs_to_remove:
        parent = run.getparent()
        if parent is not None:
            parent.remove(run)
            changes += 1
    return changes


__all__ = ["remove_strikethrough"]