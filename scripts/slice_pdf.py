#!/usr/bin/env python
"""切片PDF为前N页。"""
import sys
import os
import shutil
from pathlib import Path

import fitz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    repo_root = Path(__file__).parent.parent
    src = repo_root / "samples" / "测试文档1.pdf"
    out = repo_root / "eval_real_test"
    out.mkdir(parents=True, exist_ok=True)

    pdf = out / "测试文档1_5p.pdf"
    doc = fitz.open(src)
    sliced = fitz.open()
    for i in range(min(5, len(doc))):
        sliced.insert_pdf(doc, from_page=i, to_page=i)
    sliced.save(pdf)
    sliced.close()
    doc.close()
    print(f"Sliced 10 pages: {pdf} ({pdf.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
