"""规则5：域代码静态化（3.1.3）。

- 将所有 w:fldSimple 的内容替换为其展示结果（w:t中的文本）
- 对 w:fldChar 复杂域：用 fldChar(begin) ... instrText ... fldChar(separate) result fldChar(end) 模式
  保留 separate 与 end 之间的文本（结果），丢弃 begin 与 separate 之间的 instrText
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.docx_utils import W, load_docx_xml, save_docx_xml

logger = get_logger("xml_cleaner.freeze_fields")


def freeze_fields(input_path: Path, output_path: Path) -> int:
    """将所有域固化为结果文本。"""
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
    """处理 w:fldSimple 与 w:fldChar 复杂域。"""
    changes = 0

    # 1) fldSimple：直接替换为其内容
    for fld in list(root.iter(f"{W}fldSimple")):
        parent = fld.getparent()
        if parent is None:
            continue
        idx = parent.index(fld)
        for i, child in enumerate(list(fld)):
            parent.insert(idx + i, child)
        parent.remove(fld)
        changes += 1

    # 2) fldChar 复杂域：保留 separate 与 end 之间的结果文本
    # 收集所有 fldChar，按 run 顺序扫描
    runs = list(root.iter(f"{W}r"))
    i = 0
    while i < len(runs):
        fldchar = _find_child(runs[i], f"{W}fldChar")
        if fldchar is not None and fldchar.get(f"{W}fldCharType") == "begin":
            # 找到匹配的 end
            j = i + 1
            depth = 1
            separate_idx: int | None = None
            while j < len(runs) and depth > 0:
                fc = _find_child(runs[j], f"{W}fldChar")
                if fc is not None:
                    ftype = fc.get(f"{W}fldCharType")
                    if ftype == "begin":
                        depth += 1
                    elif ftype == "separate":
                        separate_idx = j
                    elif ftype == "end":
                        depth -= 1
                j += 1

            if depth != 0 or separate_idx is None:
                i = j
                continue

            # 删除 begin .. separate 之间的runs（含instrText）
            for k in range(i, separate_idx):
                parent = runs[k].getparent()
                if parent is not None:
                    parent.remove(runs[k])
            # 删除 end run（含fldChar end）
            end_run = runs[j - 1]
            parent = end_run.getparent()
            if parent is not None:
                parent.remove(end_run)

            changes += 1
            i = j  # 跳过已处理范围
        else:
            i += 1
    return changes


def _find_child(run: etree._Element, tag: str) -> etree._Element | None:
    """在run中找指定tag的子元素。"""
    return run.find(tag)


__all__ = ["freeze_fields"]