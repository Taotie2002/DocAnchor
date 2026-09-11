"""文档重建主入口（3.5）。

基于全局文档树 + 预置模板，输出干净DOCX。
"""

from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

from docx import Document

from docanchor.common.logger import get_logger
from docanchor.common.schema import DocumentTree, GlobalNode, NodeType
from docanchor.modules.template_render.docx_writer import render_node

logger = get_logger("template_render")


def _create_default_template(template_path: Path) -> Path:
    """创建默认预置DOCX模板（如不存在）。

    返回模板路径（新建的或已有的）。
    """
    if template_path.exists():
        return template_path
    template_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    # 设置默认页面
    section = doc.sections[0]
    section.page_height = docx_length_to_emu(842)  # A4
    section.page_width = docx_length_to_emu(595)
    section.top_margin = docx_length_to_emu(72)
    section.bottom_margin = docx_length_to_emu(72)
    section.left_margin = docx_length_to_emu(72)
    section.right_margin = docx_length_to_emu(72)
    # 默认样式：Normal
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = __import__("docx").shared.Pt(12)
    doc.save(str(template_path))
    logger.info(f"创建默认模板: {template_path}")
    return template_path


def docx_length_to_emu(pt_value: int) -> int:
    """Pt转EMU（用于python-docx的页面尺寸设置）。"""
    # 1 pt = 12700 EMU
    return pt_value * 12700


def render_document_tree(
    tree: DocumentTree,
    template_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """基于全局文档树输出干净DOCX。

    Args:
        tree: 全局文档树。
        template_path: 预置模板路径（None则使用内置默认）。
        output_path: 输出DOCX路径。

    Returns:
        实际写入的DOCX路径。
    """
    if output_path is None:
        output_path = Path("./output.docx").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建或加载模板
    if template_path is None:
        template_path = Path("./templates/default.docx").resolve()
    template_path = _create_default_template(template_path)

    # 加载模板
    doc = Document(str(template_path))

    # 递归遍历文档树，渲染每个节点
    _render_subtree(doc, tree, tree.root.node_id)

    # 保存
    doc.save(str(output_path))
    logger.info(f"文档重建完成: {output_path}")
    return output_path


def _render_subtree(doc, tree: DocumentTree, parent_id: str) -> None:
    """递归渲染子树。"""
    parent = tree.get(parent_id)
    if parent is None:
        return
    for child_id in parent.children_ids:
        child = tree.get(child_id)
        if child is None:
            continue
        # 渲染当前节点
        render_node(doc, child)
        # 递归渲染子树
        _render_subtree(doc, tree, child.node_id)


__all__ = ["render_document_tree"]