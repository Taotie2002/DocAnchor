#!/usr/bin/env python
"""切片PDF为前N页（仅文本，去除图片以减小文件）。"""
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

    # 取前20页，去除图片
    pdf = out / "测试文档1_20p_text.pdf"
    doc = fitz.open(src)
    sliced = fitz.open()
    for i in range(min(20, len(doc))):
        # 创建新页（不带图片）
        new_page = sliced.new_page(width=doc[i].rect.width, height=doc[i].rect.height)
        new_page.insert_text(
            (50, 50),
            f"=== Page {i+1} ===",
            fontsize=10,
        )
        # 提取原页文本
        text = doc[i].get_text()
        # 简单分块写入
        lines = text.split("\n")
        y = 80
        for line in lines:
            if y > doc[i].rect.height - 30:
                break
            new_page.insert_text((50, y), line[:80], fontsize=8)
            y += 12
    sliced.save(pdf)
    sliced.close()
    doc.close()
    print(f"Text-only 20 pages: {pdf} ({pdf.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
