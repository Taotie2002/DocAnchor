#!/usr/bin/env python
"""端到端运行Pipeline在真实样本上（前30页，避免内存问题）。"""
import sys
import os
import time
import json
import uuid
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path

import fitz

from docanchor.common.schema import DocumentTree
from docanchor.modules.vlm_adapter import parse_pdf_with_vlm
from docanchor.modules.pdf_extract import extract_pdf_objects
from docanchor.modules.global_aggregate.preprocessor import preprocess_blocks
from docanchor.modules.global_aggregate.doc_tree_builder import build_document_tree
from docanchor.modules.text_verify.aligner import align_vlm_with_pdf
from docanchor.modules.template_render.builder import render_document_tree


def main():
    repo_root = Path(__file__).parent.parent
    pdf_src = repo_root / "samples" / "测试文档1.pdf"
    out = repo_root / "eval_real_test"
    out.mkdir(parents=True, exist_ok=True)

    # 切片：取前30页，避免464页完整版内存超限
    print("[0s] 切片前30页...", flush=True)
    pdf = out / "测试文档1_30p.pdf"
    doc = fitz.open(pdf_src)
    sliced = fitz.open()
    for i in range(min(30, len(doc))):
        sliced.insert_pdf(doc, from_page=i, to_page=i)
    sliced.save(pdf)
    sliced.close()
    doc.close()
    print(f"  sliced PDF: {pdf} ({pdf.stat().st_size/1024:.1f} KB)", flush=True)

    start = time.time()
    print(f"[{time.time()-start:.0f}s] Step 1: VLM解析...", flush=True)
    vlm_pages = parse_pdf_with_vlm(pdf)
    all_blocks = [b for p in vlm_pages for b in p]
    print(f"[{time.time()-start:.0f}s]   blocks: {len(all_blocks)}", flush=True)

    print(f"[{time.time()-start:.0f}s] Step 2: PDF对象提取...", flush=True)
    pdf_objects = extract_pdf_objects(pdf, image_output_dir=out / "images")
    print(f"[{time.time()-start:.0f}s]   objects: {len(pdf_objects)}", flush=True)

    print(f"[{time.time()-start:.0f}s] Step 3: 预处理...", flush=True)
    preprocessed = preprocess_blocks(all_blocks)
    print(f"[{time.time()-start:.0f}s]   preprocessed: {len(preprocessed)}", flush=True)

    print(f"[{time.time()-start:.0f}s] Step 4: 文档树...", flush=True)
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    tree = build_document_tree(preprocessed, document_id=doc_id,
                                source_pdf=str(pdf), pdf_objects=pdf_objects)
    n_review = sum(1 for n in tree.nodes.values() if n.need_review)
    print(f"[{time.time()-start:.0f}s]   tree nodes: {len(tree.nodes)}, review: {n_review}",
          flush=True)

    print(f"[{time.time()-start:.0f}s] Step 5: 文字校验...", flush=True)
    alignment = align_vlm_with_pdf(preprocessed, pdf_objects)
    strong = sum(1 for a in alignment if a.level == "strong")
    print(f"[{time.time()-start:.0f}s]   alignment: {len(alignment)}, strong={strong}",
          flush=True)

    print(f"[{time.time()-start:.0f}s] Step 6: 序列化...", flush=True)
    tree_path = out / "tree.json"
    with tree_path.open("w", encoding="utf-8") as f:
        json.dump(tree.model_dump(mode="json", exclude_none=True), f,
                  ensure_ascii=False, indent=2)
    print(f"[{time.time()-start:.0f}s]   tree.json: {tree_path.stat().st_size/1024:.1f} KB",
          flush=True)

    print(f"[{time.time()-start:.0f}s] Step 7: 模板渲染...", flush=True)
    output_docx = out / "clean.docx"
    render_document_tree(tree, template_path=None, output_path=output_docx)
    print(f"[{time.time()-start:.0f}s]   clean.docx: {output_docx.stat().st_size/1024:.1f} KB",
          flush=True)

    print(f"\n[{time.time()-start:.0f}s] === 完成 ===", flush=True)
    from collections import Counter
    type_counter = Counter()
    for n in tree.nodes.values():
        type_counter[n.node_type.value] += 1
    for t, c in type_counter.most_common():
        print(f"  {t}: {c}", flush=True)

    # 统计
    headings = [n for n in tree.nodes.values() if n.node_type.value == "heading"]
    print(f"\n标题样例 (前10个):", flush=True)
    for h in headings[:10]:
        print(f"  L{h.global_level}: {h.text[:50]!r}", flush=True)


if __name__ == "__main__":
    main()
