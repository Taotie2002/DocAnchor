"""DOCX底层工具：lxml直接操作OOXML，避免python-docx抽象层。"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

# OOXML命名空间
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "v": "urn:schemas-microsoft-com:vml",
    "w10": "urn:schemas-microsoft-com:office:word",
    "o": "urn:schemas-microsoft-com:office:office",
}

W = "{%s}" % NS["w"]


def w(tag: str) -> str:
    """快捷获取 w:tag 的完整限定名。"""
    return f"{W}{tag}"


def load_docx_xml(docx_path: Path, part: str) -> etree._ElementTree:
    """加载DOCX中某个XML part。

    Args:
        docx_path: DOCX路径。
        part: 例如 "word/document.xml"、"word/comments.xml"。

    Returns:
        ElementTree 根。
    """
    import zipfile

    with zipfile.ZipFile(docx_path, "r") as z:
        with z.open(part) as f:
            return etree.parse(f)


def save_docx_xml(
    docx_path: Path,
    output_path: Path,
    modifications: dict[str, etree._ElementTree],
) -> None:
    """将修改后的XML part写回DOCX。

    Args:
        docx_path: 原始DOCX。
        output_path: 输出DOCX。
        modifications: {part路径: 修改后的Tree}。
    """
    import shutil
    import zipfile

    if output_path == docx_path:
        # 覆盖模式：先复制到临时文件，再原子替换
        tmp = docx_path.with_suffix(docx_path.suffix + ".tmp")
        shutil.copyfile(docx_path, tmp)
        source = tmp
    else:
        source = docx_path

    try:
        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename in modifications:
                    tree = modifications[item.filename]
                    zout.writestr(item, etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True))
                else:
                    zout.writestr(item, zin.read(item.filename))
        if source != docx_path and source.exists():
            source.unlink()
    except Exception:
        if source != docx_path and source.exists():
            source.unlink()
        raise


__all__ = ["NS", "W", "w", "load_docx_xml", "save_docx_xml"]