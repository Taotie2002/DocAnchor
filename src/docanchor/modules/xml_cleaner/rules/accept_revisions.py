"""规则1：接受全部修订（3.1.3）。

- 移除 w:ins 包裹层，保留其内文本
- 移除 w:del 包裹层及其内文本
- 移除 w:moveFrom / w:moveTo 包裹层（moveFrom移除内容，moveTo保留内容）
- 移除 w:cellIns / w:cellDel / w:cellMerge 等表格修订标记
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.docx_utils import W, load_docx_xml, save_docx_xml

logger = get_logger("xml_cleaner.accept_revisions")

# 文档接收修订标签
_REVISION_TAGS_TO_UNWRAP = [
    f"{W}ins",       # 插入：解开包裹保留文本
    f"{W}moveTo",    # 移入：解开包裹保留文本
    f"{W}cellIns",   # 表格单元格插入：解开包裹
    f"{W}cellMerge", # 表格合并：解开包裹
]

_REVISION_TAGS_TO_REMOVE = [
    f"{W}del",       # 删除：删除整个元素
    f"{W}moveFrom",  # 移出：删除整个元素
    f"{W}cellDel",   # 表格单元格删除：删除整个元素
]

# pPrChange/rPrChange/tblPrChange 等属性修订：移除整个变更元素
_PROP_CHANGE_TAGS = [
    f"{W}pPrChange",
    f"{W}rPrChange",
    f"{W}tblPrChange",
    f"{W}tcPrChange",
    f"{W}trPrChange",
    f"{W}sectPrChange",
    f"{W}numberingChange",
]


def accept_all_revisions(input_path: Path, output_path: Path) -> int:
    """接受全部修订。

    Returns:
        变更数量（解开包裹+删除元素总数）。
    """
    changes = 0
    modifications: dict[str, etree._ElementTree] = {}

    # 处理 document.xml、header*.xml、footer*.xml、footnotes.xml、endnotes.xml
    parts = _list_text_parts(input_path)
    for part in parts:
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


def _list_text_parts(docx_path: Path) -> list[str]:
    """列出所有含文本内容的XML part。"""
    import zipfile

    parts = ["word/document.xml"]
    with zipfile.ZipFile(docx_path, "r") as z:
        for name in z.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                base = name[len("word/"):]
                if any(
                    base.startswith(prefix)
                    for prefix in ("header", "footer", "footnotes", "endnotes")
                ):
                    parts.append(name)
    return parts


def _process_tree(root: etree._Element) -> int:
    """遍历树，处理所有修订标记。"""
    changes = 0
    for tag in _REVISION_TAGS_TO_UNWRAP:
        for elem in root.iter(tag):
            _unwrap(elem)
            changes += 1
    for tag in _REVISION_TAGS_TO_REMOVE:
        for elem in list(root.iter(tag)):
            _remove_with_text(elem)
            changes += 1
    for tag in _PROP_CHANGE_TAGS:
        for elem in list(root.iter(tag)):
            elem.getparent().remove(elem)
            changes += 1
    return changes


def _unwrap(elem: etree._Element) -> None:
    """解开包裹层：把elem的所有子节点提升到父节点位置。"""
    parent = elem.getparent()
    if parent is None:
        return
    idx = parent.index(elem)
    for i, child in enumerate(list(elem)):
        parent.insert(idx + i, child)
    parent.remove(elem)


def _remove_with_text(elem: etree._Element) -> None:
    """删除整个元素（连带其内文本）。"""
    parent = elem.getparent()
    if parent is not None:
        parent.remove(elem)


__all__ = ["accept_all_revisions"]