"""XML清洗模块单测（3.1.3）。

覆盖：
- accept_revisions: 接受ins/del/moveFrom/moveTo
- remove_vanish: 删除隐藏文字
- remove_strikethrough: 删除删除线文本
- strip_comments: 清除批注
- freeze_fields: 域代码静态化
- strip_macros: 清除宏

通过构造含脏数据的合成DOCX验证规则命中。
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from docanchor.modules.xml_cleaner import clean_docx
from docanchor.modules.xml_cleaner.rules import (
    accept_all_revisions,
    freeze_fields,
    remove_strikethrough,
    remove_vanish,
    strip_comments,
    strip_macros,
)


def _build_minimal_docx(
    tmp_path: Path,
    *,
    document_xml: str,
    extra_parts: dict[str, str] | None = None,
) -> Path:
    """构造最小DOCX（含word/document.xml）。"""
    import shutil

    docx_path = tmp_path / "test.docx"
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    parts = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": rels,
        "word/document.xml": document_xml,
    }
    if extra_parts:
        parts.update(extra_parts)
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
    return docx_path


W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


class TestAcceptRevisions:
    def test_unwrap_ins(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:ins w:id="1"><w:r><w:t>inserted</w:t></w:r></w:ins>
<w:r><w:t>normal</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = accept_all_revisions(src, dst)
        assert changes >= 1
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "<w:ins " not in out
        assert "inserted" in out
        assert "normal" in out

    def test_remove_del(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:del w:id="1"><w:r><w:delText>deleted</w:delText></w:r></w:del>
<w:r><w:t>kept</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = accept_all_revisions(src, dst)
        assert changes >= 1
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "<w:del " not in out
        assert "deleted" not in out
        assert "kept" in out

    def test_remove_prop_change(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:pPr>
<w:pPrChange w:id="1"><w:pPr/></w:pPrChange>
<w:rPr><w:sz w:val="24"/></w:rPr>
</w:pPr>
<w:r><w:t>text</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        accept_all_revisions(src, dst)
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "pPrChange" not in out


class TestRemoveVanish:
    def test_removes_vanish_run(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:r><w:rPr><w:vanish/></w:rPr><w:t>hidden</w:t></w:r>
<w:r><w:t>visible</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = remove_vanish(src, dst)
        assert changes == 1
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "hidden" not in out
        assert "visible" in out


class TestRemoveStrikethrough:
    def test_removes_strike_run(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:r><w:rPr><w:strike/></w:rPr><w:t>crossed</w:t></w:r>
<w:r><w:t>kept</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = remove_strikethrough(src, dst)
        assert changes == 1
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "crossed" not in out

    def test_removes_dstrike_run(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:r><w:rPr><w:dstrike/></w:rPr><w:t>doublecrossed</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = remove_strikethrough(src, dst)
        assert changes == 1


class TestStripComments:
    def test_removes_inline_and_part(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:commentRangeStart w:id="1"/>
<w:r><w:t>commented</w:t></w:r>
<w:commentRangeEnd w:id="1"/>
<w:r><w:commentReference w:id="1"/></w:r>
</w:p>
</w:body>
</w:document>"""
        comments_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments {W_NS}>
<w:comment w:id="1"><w:p><w:r><w:t>review</w:t></w:r></w:p></w:comment>
</w:comments>"""
        src = _build_minimal_docx(
            tmp_path,
            document_xml=doc_xml,
            extra_parts={"word/comments.xml": comments_xml},
        )
        dst = tmp_path / "out.docx"
        changes = strip_comments(src, dst)
        assert changes >= 1
        with zipfile.ZipFile(dst, "r") as z:
            names = z.namelist()
            out_doc = z.read("word/document.xml").decode("utf-8")
        assert "word/comments.xml" not in names
        assert "commentRangeStart" not in out_doc


class TestFreezeFields:
    def test_freezes_fld_simple(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:fldSimple w:instr=" PAGE \\* MERGEFORMAT "><w:r><w:t>1</w:t></w:r></w:fldSimple>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = freeze_fields(src, dst)
        assert changes >= 1
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "<w:fldSimple " not in out
        assert "1" in out


class TestStripMacros:
    def test_no_vba_returns_zero(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p><w:r><w:t>clean</w:t></w:r></w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        changes = strip_macros(src, dst)
        assert changes == 0

    def test_removes_vba_part(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p><w:r><w:t>has macro</w:t></w:r></w:p>
</w:body>
</w:document>"""
        # 构造一个伪造的vbaProject.bin
        src = _build_minimal_docx(
            tmp_path,
            document_xml=doc_xml,
            extra_parts={"word/vbaProject.bin": "fake_vba_bytes"},
        )
        dst = tmp_path / "out.docx"
        changes = strip_macros(src, dst)
        assert changes == 1
        with zipfile.ZipFile(dst, "r") as z:
            assert "word/vbaProject.bin" not in z.namelist()


class TestCleanDocxPipeline:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS}>
<w:body>
<w:p>
<w:ins w:id="1"><w:r><w:t>inserted</w:t></w:r></w:ins>
<w:del w:id="2"><w:r><w:delText>removed</w:delText></w:r></w:del>
<w:r><w:rPr><w:vanish/></w:rPr><w:t>hidden</w:t></w:r>
<w:r><w:rPr><w:strike/></w:rPr><w:t>crossed</w:t></w:r>
<w:r><w:t>final</w:t></w:r>
</w:p>
</w:body>
</w:document>"""
        src = _build_minimal_docx(tmp_path, document_xml=doc_xml)
        dst = tmp_path / "out.docx"
        report = clean_docx(src, dst)
        assert report.total_changes >= 4
        with zipfile.ZipFile(dst, "r") as z:
            out = z.read("word/document.xml").decode("utf-8")
        assert "inserted" in out
        assert "removed" not in out
        assert "hidden" not in out
        assert "crossed" not in out
        assert "final" in out