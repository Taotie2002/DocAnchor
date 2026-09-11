"""合成脏DOCX生成器（用于POC阶段的Go/No-Go验证）。

基于python-docx生成一份模拟脏文档，包含：
- 多级标题（heading 1-3）
- 正文段落（含中英文混排）
- 普通表格（2x3）
- 简单列表
- 修订（接受前）
- 隐藏文字
- 简单格式

输出到 tests/fixtures/dirty_sample.docx
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Pt


def build(output_path: Path) -> Path:
    """构造一份合成脏DOCX并写入output_path。"""
    doc = Document()

    # 一级标题
    h1 = doc.add_heading("第一章 项目概述", level=1)

    # 正文
    doc.add_paragraph(
        "本章节介绍项目的核心目标、适用场景与设计取舍。"
        "原始DOCX文档可能含多人拼凑、样式混乱、XML结构崩坏等问题。"
    )

    # 二级标题
    doc.add_heading("1.1 核心目标", level=2)
    doc.add_paragraph(
        "针对多人拼凑的脏DOCX文档，实现全自动：文档结构解析、"
        "内容纠错、层级归一化、结构重建。"
    )

    # 三级标题
    doc.add_heading("1.1.1 子目标", level=3)
    doc.add_paragraph("进一步细化的子目标说明。")

    # 表格
    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    table.cell(0, 0).text = "阶段"
    table.cell(0, 1).text = "周期"
    table.cell(0, 2).text = "交付物"
    table.cell(1, 0).text = "阶段1"
    table.cell(1, 1).text = "2周"
    table.cell(1, 2).text = "技术预研POC"
    table.cell(2, 0).text = "阶段2"
    table.cell(2, 1).text = "2周"
    table.cell(2, 2).text = "单篇闭环"

    doc.add_paragraph()

    # 一级标题
    doc.add_heading("第二章 系统架构", level=1)
    doc.add_paragraph(
        "全流程固定顺序：DOCX源文件 → XML级元数据清洗 → "
        "LibreOffice headless转PDF → 双路并行解析 → 全局聚合 → "
        "文字双路校验 → 模板灌注与文档重建。"
    )

    # 二级标题
    doc.add_heading("2.1 核心双路机制", level=2)

    # 列表
    doc.add_paragraph("视觉结构路：VLM 基于PDF页面输出区块类型、层级、布局位置。")
    doc.add_paragraph("原生文本路：PyMuPDF 提取PDF原生文本层、图片、表格对象。")

    doc.add_paragraph("两路共享同一PDF页面坐标系，几何天然重合。")

    # 二级标题
    doc.add_heading("2.2 锚定PDF同源坐标系", level=2)
    doc.add_paragraph(
        "放弃对Word原始排版的还原义务，以PDF作为全系统统一坐标与内容基准，"
        "消灭跨引擎坐标对齐风险。"
    )

    # 模拟跨页：手动分页
    p = doc.add_paragraph("跨页测试段落第一段：本期主要交付物清单如下。")
    p.add_run().add_break(WD_BREAK.PAGE)
    doc.add_paragraph("跨页测试段落第二段：续上页内容。")

    # 三级标题
    doc.add_heading("2.2.1 视图配置", level=3)
    doc.add_paragraph(
        "关闭修订标记、关闭隐藏文字、关闭批注显示；"
        "嵌入所有字体、固定页边距、固定DPI输出。"
    )

    doc.save(output_path)

    # 注入脏数据：修订/隐藏文字
    _inject_dirty_data(output_path, output_path)

    return output_path


def _inject_dirty_data(input_path: Path, output_path: Path) -> None:
    """在已保存的DOCX中注入修订、隐藏文字等脏数据。"""
    import shutil
    import tempfile

    if input_path == output_path:
        with tempfile.NamedTemporaryFile(
            suffix=".docx", delete=False, dir=output_path.parent
        ) as tmp:
            tmp_path = Path(tmp.name)
        shutil.copyfile(output_path, tmp_path)
    else:
        tmp_path = output_path

    try:
        # 读document.xml
        with zipfile.ZipFile(tmp_path, "r") as z:
            with z.open("word/document.xml") as f:
                doc_xml = f.read().decode("utf-8")

        # 注入一段<w:ins>和<w:vanish>
        injection = (
            "<w:p>"
            "<w:ins w:id=\"100\"><w:r><w:t>插入内容</w:t></w:r></w:ins>"
            "<w:del w:id=\"101\"><w:r><w:delText>删除内容</w:delText></w:r></w:del>"
            "<w:r><w:rPr><w:vanish/></w:rPr><w:t>隐藏文字</w:t></w:r>"
            "<w:r><w:t>正常内容</w:t></w:r>"
            "</w:p>"
        )
        # 插入到</w:body>前
        if "</w:body>" in doc_xml:
            doc_xml = doc_xml.replace("</w:body>", injection + "</w:body>", 1)

        # 重写zip
        with zipfile.ZipFile(tmp_path, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, doc_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))

        if input_path == output_path and tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        if input_path == output_path and tmp_path.exists():
            tmp_path.unlink()
        raise


if __name__ == "__main__":
    out = Path(__file__).parent / "dirty_sample.docx"
    build(out)
    print(f"合成脏DOCX: {out} ({out.stat().st_size} bytes)")