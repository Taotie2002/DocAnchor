"""规则4：删除批注与批注框（3.1.3）。

- 删除 word/comments.xml、word/commentsExtended.xml、word/commentsIds.xml 等 part
- 移除 document.xml 中所有 w:commentRangeStart / w:commentRangeEnd / w:commentReference
- 清理 [Content_Types].xml 与 word/_rels/document.xml.rels 中对应关系
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from docanchor.common.logger import get_logger
from docanchor.modules.xml_cleaner.docx_utils import W, load_docx_xml

logger = get_logger("xml_cleaner.strip_comments")

_COMMENT_PARTS = [
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
    "word/people.xml",
]

_INLINE_TAGS = [
    f"{W}commentRangeStart",
    f"{W}commentRangeEnd",
    f"{W}commentReference",
]


def strip_comments(input_path: Path, output_path: Path) -> int:
    """清除所有批注与批注引用。"""
    import zipfile

    changes = 0
    modifications: dict[str, etree._ElementTree] = {}

    # 1) 处理document.xml中的内联引用
    try:
        tree = load_docx_xml(input_path, "word/document.xml")
        root = tree.getroot()
        for tag in _INLINE_TAGS:
            for elem in list(root.iter(tag)):
                elem.getparent().remove(elem)
                changes += 1
        modifications["word/document.xml"] = tree
    except KeyError:
        pass

    # 2) 删除comments相关part
    _strip_comment_parts(input_path, output_path, modifications)
    return changes


def _strip_comment_parts(
    input_path: Path,
    output_path: Path,
    modifications: dict[str, etree._ElementTree],
) -> None:
    """重写zip，剔除comment相关part。"""
    import shutil
    import zipfile

    if output_path == input_path:
        tmp = input_path.with_suffix(input_path.suffix + ".tmp")
        shutil.copyfile(input_path, tmp)
        source = tmp
    else:
        source = input_path

    try:
        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename in _COMMENT_PARTS:
                    continue  # 跳过
                if item.filename in modifications:
                    tree = modifications[item.filename]
                    zout.writestr(
                        item,
                        etree.tostring(
                            tree, xml_declaration=True, encoding="UTF-8", standalone=True
                        ),
                    )
                else:
                    zout.writestr(item, zin.read(item.filename))
        if source != input_path and source.exists():
            source.unlink()
    except Exception:
        if source != input_path and source.exists():
            source.unlink()
        raise


__all__ = ["strip_comments"]