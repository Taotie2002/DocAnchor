"""多脏度等级合成DOCX语料生成器。

提供三类合成样本：
- 轻度（light）：少量样式冲突 + 轻度修订 + 简单跨页
- 中度（medium）：多人拼凑 + 嵌套表格 + 跨页表格
- 重度（heavy）：多栏排版 + 大量修订隐藏 + 复杂表格

用于POC阶段无用户样本时的链路联调与基本评测。
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_BREAK
from docx.shared import Inches, Pt


# ============================================================
# 轻度样本
# ============================================================


def build_light(output_path: Path) -> Path:
    """轻度脏文档：含修订/隐藏文字/简单跨页。"""
    doc = Document()
    doc.add_heading("项目背景", level=1)
    doc.add_paragraph("本章介绍项目的核心背景与目标。")
    doc.add_heading("1.1 背景概述", level=2)
    doc.add_paragraph("项目起源于内部技术债清理工作。")
    doc.add_heading("1.2 项目范围", level=2)
    doc.add_paragraph("包含结构解析、内容纠错、层级归一化三大模块。")

    # 表格
    table = doc.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "模块"
    table.cell(0, 1).text = "状态"
    table.cell(1, 0).text = "结构解析"
    table.cell(1, 1).text = "已完成"

    doc.add_paragraph("简要总结见下节。")
    doc.add_heading("1.3 总结", level=2)
    doc.add_paragraph("本章为后续工作奠定基础。")

    doc.save(output_path)

    # 注入轻度脏数据：少量修订 + 一处隐藏文字
    _inject_light(output_path, output_path)
    return output_path


def _inject_light(input_path: Path, output_path: Path) -> None:
    """注入轻度脏数据：1个修订 + 1处隐藏文字。"""
    import shutil
    import tempfile

    if input_path == output_path:
        tmp = input_path.with_suffix(input_path.suffix + ".tmp")
        shutil.copyfile(input_path, tmp)
        source = tmp
    else:
        source = input_path

    try:
        with zipfile.ZipFile(source, "r") as zin:
            doc_xml = zin.read("word/document.xml").decode("utf-8")

        injection = (
            "<w:p>"
            "<w:ins w:id=\"1\"><w:r><w:t>插入了轻度内容</w:t></w:r></w:ins>"
            "<w:r><w:rPr><w:vanish/></w:rPr><w:t>隐藏文字</w:t></w:r>"
            "<w:r><w:t>正常内容</w:t></w:r>"
            "</w:p>"
        )
        if "</w:body>" in doc_xml:
            doc_xml = doc_xml.replace("</w:body>", injection + "</w:body>", 1)

        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, doc_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))

        if source != input_path and source.exists():
            source.unlink()
    except Exception:
        if source != input_path and source.exists():
            source.unlink()
        raise


# ============================================================
# 中度样本
# ============================================================


def build_medium(output_path: Path) -> Path:
    """中度脏文档：含嵌套表格 + 跨页表格 + 多人拼凑样式冲突。"""
    doc = Document()

    # 一级
    doc.add_heading("第一章 系统设计", level=1)
    doc.add_paragraph("本章详细说明系统的总体设计与关键决策。")

    # 二级
    doc.add_heading("1.1 总体架构", level=2)
    doc.add_paragraph("系统采用分层架构：接入层、业务层、数据层。")

    # 三级
    doc.add_heading("1.1.1 接入层", level=3)
    doc.add_paragraph("接入层负责协议解析与请求路由。")

    doc.add_heading("1.1.2 业务层", level=3)
    doc.add_paragraph("业务层实现核心业务逻辑。")

    # 表格1：架构层级
    t1 = doc.add_table(rows=4, cols=3)
    t1.style = "Table Grid"
    headers = ["层级", "组件", "职责"]
    for i, h in enumerate(headers):
        t1.cell(0, i).text = h
    rows = [
        ["接入层", "API网关", "协议转换"],
        ["业务层", "核心服务", "业务逻辑"],
        ["数据层", "存储", "持久化"],
    ]
    for r_idx, row in enumerate(rows, 1):
        for c_idx, val in enumerate(row):
            t1.cell(r_idx, c_idx).text = val

    doc.add_paragraph()

    # 一级
    doc.add_heading("第二章 模块详解", level=1)
    doc.add_paragraph("本章对核心模块进行逐一详解。")

    # 跨页表格
    doc.add_heading("2.1 核心模块", level=2)
    p = doc.add_paragraph("核心模块清单见下表（跨页续表）。")
    p.add_run().add_break(WD_BREAK.PAGE)

    t2 = doc.add_table(rows=6, cols=4)
    t2.style = "Table Grid"
    headers2 = ["模块名", "代码行数", "测试覆盖率", "状态"]
    for i, h in enumerate(headers2):
        t2.cell(0, i).text = h
    rows2 = [
        ["XML清洗", "800", "85%", "已完成"],
        ["PDF转换", "1200", "78%", "已完成"],
        ["VLM Adapter", "1500", "70%", "联调中"],
        ["全局聚合", "2000", "65%", "开发中"],
        ["模板渲染", "900", "60%", "开发中"],
    ]
    for r_idx, row in enumerate(rows2, 1):
        for c_idx, val in enumerate(row):
            t2.cell(r_idx, c_idx).text = val

    # 嵌套表格
    doc.add_heading("2.2 嵌套表格示例", level=2)
    doc.add_paragraph("下表展示嵌套表格结构：")
    outer = doc.add_table(rows=2, cols=2)
    outer.style = "Table Grid"
    outer.cell(0, 0).text = "外层1"
    outer.cell(0, 1).text = "外层2"
    # 内嵌单元格中的表格
    inner = outer.cell(1, 0).add_table(rows=2, cols=2)
    inner.cell(0, 0).text = "内1"
    inner.cell(0, 1).text = "内2"
    inner.cell(1, 0).text = "内3"
    inner.cell(1, 1).text = "内4"
    outer.cell(1, 1).text = "外层4"

    # 二级
    doc.add_heading("2.3 状态总览", level=2)
    doc.add_paragraph("目前各模块状态如上表所示。")

    doc.save(output_path)

    # 注入中度脏数据
    _inject_medium(output_path, output_path)
    return output_path


def _inject_medium(input_path: Path, output_path: Path) -> None:
    """注入中度脏数据：多人拼凑的样式冲突 + 多处修订。"""
    import shutil

    if input_path == output_path:
        tmp = input_path.with_suffix(input_path.suffix + ".tmp")
        shutil.copyfile(input_path, tmp)
        source = tmp
    else:
        source = input_path

    try:
        with zipfile.ZipFile(source, "r") as zin:
            doc_xml = zin.read("word/document.xml").decode("utf-8")

        # 多处修订
        injections = []
        for i in range(5):
            injections.append(
                f"<w:p><w:ins w:id=\"{100 + i}\"><w:r><w:t>中度插入内容{i}</w:t></w:r></w:ins>"
                f"<w:r><w:t>多人拼凑内容</w:t></w:r></w:p>"
            )
        # 隐藏文字
        injections.append(
            "<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>中度隐藏内容</w:t></w:r>"
            "<w:r><w:t>正常</w:t></w:r></w:p>"
        )

        injection = "".join(injections)
        if "</w:body>" in doc_xml:
            doc_xml = doc_xml.replace("</w:body>", injection + "</w:body>", 1)

        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, doc_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))

        if source != input_path and source.exists():
            source.unlink()
    except Exception:
        if source != input_path and source.exists():
            source.unlink()
        raise


# ============================================================
# 重度样本
# ============================================================


def build_heavy(output_path: Path) -> Path:
    """重度脏文档：多栏排版 + 大量修订 + 复杂表格 + 多section。"""
    doc = Document()

    # Section 1：单栏
    doc.add_heading("第一部分 总论", level=1)
    doc.add_paragraph("本章概述项目背景与目标。")
    doc.add_heading("1.1 背景", level=2)
    doc.add_paragraph("项目起源于脏文档处理需求。")
    doc.add_heading("1.2 目标", level=2)
    doc.add_paragraph("实现DOCX→干净DOCX的全自动重建。")

    # Section 2：分节（不同页眉）
    new_section = doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_heading("第二部分 技术方案", level=1)
    doc.add_paragraph("本章详细说明技术方案。")
    doc.add_heading("2.1 模块设计", level=2)

    # 复杂表格：跨多页
    doc.add_paragraph("下表展示模块清单（跨多页）：")
    complex_table = doc.add_table(rows=10, cols=5)
    complex_table.style = "Table Grid"
    headers = ["模块", "代码行数", "测试", "负责人", "进度"]
    for i, h in enumerate(headers):
        complex_table.cell(0, i).text = h
    modules = [
        ["模块A", "1000", "80%", "张三", "90%"],
        ["模块B", "1200", "85%", "李四", "80%"],
        ["模块C", "800", "70%", "王五", "70%"],
        ["模块D", "1500", "75%", "赵六", "60%"],
        ["模块E", "900", "90%", "钱七", "95%"],
        ["模块F", "1100", "65%", "孙八", "50%"],
        ["模块G", "700", "85%", "周九", "100%"],
        ["模块H", "1300", "70%", "吴十", "40%"],
        ["模块I", "950", "80%", "郑十一", "75%"],
    ]
    for r_idx, row in enumerate(modules, 1):
        for c_idx, val in enumerate(row):
            complex_table.cell(r_idx, c_idx).text = val

    doc.add_heading("2.2 关键技术", level=2)
    doc.add_paragraph("核心技术包括VLM、PDF坐标对齐、LLM辅助等。")

    # Section 3
    new_section2 = doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_heading("第三部分 实施计划", level=1)
    doc.add_heading("3.1 时间表", level=2)
    doc.add_paragraph("项目共分5个阶段，每阶段2周。")
    doc.add_heading("3.2 风险评估", level=2)
    doc.add_paragraph("主要风险包括VLM输出稳定性、性能等。")

    doc.save(output_path)

    # 注入重度脏数据
    _inject_heavy(output_path, output_path)
    return output_path


def _inject_heavy(input_path: Path, output_path: Path) -> None:
    """注入重度脏数据：大量修订 + 多处隐藏 + 删除线 + 批注。"""
    import shutil

    if input_path == output_path:
        tmp = input_path.with_suffix(input_path.suffix + ".tmp")
        shutil.copyfile(input_path, tmp)
        source = tmp
    else:
        source = input_path

    try:
        with zipfile.ZipFile(source, "r") as zin:
            doc_xml = zin.read("word/document.xml").decode("utf-8")

        # 大量修订
        injections = []
        for i in range(15):
            injections.append(
                f"<w:p><w:ins w:id=\"{200 + i}\"><w:r><w:t>重度插入{i}</w:t></w:r></w:ins>"
                f"<w:r><w:rPr><w:vanish/></w:rPr><w:t>重度隐藏{i}</w:t></w:r>"
                f"<w:r><w:rPr><w:strike/></w:rPr><w:t>重度删除线{i}</w:t></w:r>"
                f"<w:r><w:t>正常{i}</w:t></w:r></w:p>"
            )
        # 批注
        injections.append(
            "<w:p>"
            "<w:commentRangeStart w:id=\"1\"/>"
            "<w:r><w:t>批注内容</w:t></w:r>"
            "<w:commentRangeEnd w:id=\"1\"/>"
            "<w:r><w:commentReference w:id=\"1\"/></w:r>"
            "</w:p>"
        )

        injection = "".join(injections)
        if "</w:body>" in doc_xml:
            doc_xml = doc_xml.replace("</w:body>", injection + "</w:body>", 1)

        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, doc_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))

        if source != input_path and source.exists():
            source.unlink()
    except Exception:
        if source != input_path and source.exists():
            source.unlink()
        raise


# ============================================================
# 入口
# ============================================================


BUILDERS: dict[str, Callable[[Path], Path]] = {
    "light": build_light,
    "medium": build_medium,
    "heavy": build_heavy,
}


def build_all(output_dir: Path) -> dict[str, Path]:
    """构建三档样本，返回 {dirt_level: path}。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for level, builder in BUILDERS.items():
        path = output_dir / f"dirty_{level}.docx"
        builder(path)
        result[level] = path
    return result


if __name__ == "__main__":
    import sys

    out_dir = Path(__file__).parent / "corpus"
    paths = build_all(out_dir)
    for level, path in paths.items():
        size = path.stat().st_size
        print(f"  [{level}] {path} ({size} bytes)")