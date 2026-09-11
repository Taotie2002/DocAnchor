"""规则2：删除隐藏文字（3.1.3）。

- 移除所有 w:r/w:rPr/w:vanish 标记的 run（即 rPr 内有 w:vanish 的 w:r）
- 同时移除 w:rPr 内 vanish 元素（保持文档一致）
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from lxml import etree

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.docx_utils import W, load_docx_xml, save_docx_xml

logger = get_logger("xml_cleaner.remove_vanish")


def remove_vanish(input_path: Path, output_path: Path) -> int:
    """删除所有隐藏文字。"""
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
    """遍历所有 w:r，若其 rPr 含 w:vanish 则删除整个 run。"""
    changes = 0
    # 注意：先收集再删除，避免迭代时修改
    runs_to_remove: list[etree._Element] = []
    for run in root.iter(f"{W}r"):
        rpr = run.find(f"{W}rPr")
        if rpr is not None and rpr.find(f"{W}vanish") is not None:
            runs_to_remove.append(run)
    for run in runs_to_remove:
        parent = run.getparent()
        if parent is not None:
            parent.remove(run)
            changes += 1
    return changes


__all__ = ["remove_vanish"]