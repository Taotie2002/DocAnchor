"""合成样本标注自动生成器。

为 build_dirty_corpus 生成的合成DOCX样本生成对应的标注JSON。
标注策略：从原始DOCX解析章节结构，提取真实标题层级/段落归属/表格行列。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lxml import etree

from docanchor.common.idgen import new_block_id

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_annotations_from_docx(
    docx_path: Path,
    dirt_level: str,
) -> dict[str, Any]:
    """从DOCX提取标注ground truth。

    提取**所有段落和表格**，包括：
    - 正常段落
    - 标题
    - 表格
    - 修订包裹的段落（取 innerText，与pipeline清洗后内容一致）
    - **不**过滤vanish/strike（这些规则默认不在生成器中注入到vanish run）

    Args:
        docx_path: DOCX文件路径。
        dirt_level: 脏度等级。

    Returns:
        标注JSON（与评测格式兼容）。
    """
    import zipfile

    with zipfile.ZipFile(docx_path, "r") as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")

    root = etree.fromstring(doc_xml.encode("utf-8"))

    annotations: list[dict[str, Any]] = []
    parent_stack: list[str] = []  # 用于构建章节链
    block_counter = 0

    for elem in root.iter():
        tag = elem.tag

        if tag == f"{W_NS}p":
            # 判断段落类型
            pPr = elem.find(f"{W_NS}pPr")
            is_heading = False
            level = 0
            if pPr is not None:
                pStyle = pPr.find(f"{W_NS}pStyle")
                if pStyle is not None:
                    style_val = pStyle.get(f"{W_NS}val", "")
                    if style_val.startswith("Heading") or style_val in ("1", "2", "3"):
                        try:
                            level = int(style_val[-1]) if style_val[-1].isdigit() else 0
                        except (ValueError, IndexError):
                            level = 0
                        if level > 0:
                            is_heading = True

            # 提取段落文本：取所有<w:t>内容（pipeline XML清洗后会保留这些）
            # 对合成样本，注入的脏数据已直接出现在普通run里（w:t），无vanish包裹
            texts = elem.findall(f".//{W_NS}t")
            full_text = "".join(t.text or "" for t in texts).strip()

            # 跳过空段落
            if not full_text:
                continue

            block_id = f"synthetic-b{block_counter:04d}"
            block_counter += 1

            if is_heading:
                while parent_stack and len(parent_stack) >= level:
                    parent_stack.pop()
                parent_id = parent_stack[-1] if parent_stack else None
                annotations.append(
                    {
                        "id": block_id,
                        "type": "heading",
                        "page": 1,
                        "global_level": level,
                        "parent_id": parent_id,
                        "sort_key": block_counter,
                        "table_dims": None,
                        "cross_page_pair": None,
                        "text": full_text,
                    }
                )
                parent_stack.append(block_id)
            else:
                parent_id = parent_stack[-1] if parent_stack else None
                annotations.append(
                    {
                        "id": block_id,
                        "type": "paragraph",
                        "page": 1,
                        "global_level": None,
                        "parent_id": parent_id,
                        "sort_key": block_counter,
                        "table_dims": None,
                        "cross_page_pair": None,
                        "text": full_text,
                    }
                )

        elif tag == f"{W_NS}tbl":
            rows = list(elem.findall(f".//{W_NS}tr"))
            n_rows = len(rows)
            n_cols = len(list(rows[0].findall(f".//{W_NS}tc"))) if rows else 0

            block_id = f"synthetic-t{block_counter:04d}"
            block_counter += 1

            cell_matrix: list[list[str]] = []
            for tr in rows:
                row_cells: list[str] = []
                for tc in tr.findall(f".//{W_NS}tc"):
                    direct_texts = []
                    for t in tc.findall(f".//{W_NS}t"):
                        direct_texts.append(t.text or "")
                    row_cells.append("".join(direct_texts).strip())
                cell_matrix.append(row_cells)

            annotations.append(
                {
                    "id": block_id,
                    "type": "table",
                    "page": 1,
                    "global_level": None,
                    "parent_id": parent_stack[-1] if parent_stack else None,
                    "sort_key": block_counter,
                    "table_dims": {"rows": n_rows, "cols": n_cols},
                    "cell_matrix": cell_matrix,
                    "cross_page_pair": None,
                }
            )

    return {
        "document_id": f"synthetic-{dirt_level}",
        "docx_path": str(docx_path),
        "dirt_level": dirt_level,
        "annotations": annotations,
        "review_metadata": {
            "reviewer": "auto-generated from synthetic DOCX",
            "review_time": None,
            "notes": "由 tests/fixtures/generate_synthetic_annotations.py 自动生成",
        },
    }


def generate_all(corpus_dir: Path, output_dir: Path) -> dict[str, Path]:
    """为整个语料库生成标注。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for level in ("light", "medium", "heavy"):
        docx = corpus_dir / f"dirty_{level}.docx"
        if not docx.exists():
            print(f"  跳过: {docx} 不存在")
            continue
        ann = extract_annotations_from_docx(docx, level)
        out_path = output_dir / f"dirty_{level}_annotations.json"
        out_path.write_text(
            json.dumps(ann, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result[level] = out_path
        n = len(ann["annotations"])
        print(f"  [{level}] {n} 条标注 -> {out_path}")
    return result


if __name__ == "__main__":
    corpus_dir = Path(__file__).parent / "corpus"
    out_dir = Path(__file__).parent / "annotations"
    paths = generate_all(corpus_dir, out_dir)
    print(f"\\n共生成 {len(paths)} 份标注")