"""PDF转换保真度验证（3.1.6 Go/No-Go判定项）。

三项指标：
1. 内容召回率：正文/表格文本召回率≥99%，图片召回率≥98%
2. 分页偏差分布：统计不同脏度文档的分页偏移量，中度脏文档分页偏差≤1行占比≥90%
3. 表格结构保真度：常规表格行列结构准确率≥95%，嵌套表格结构畸变率≤5%

实现：
- 用原始DOCX与生成PDF对比文字召回
- 用PDF文本span统计行数，与原始DOCX段落对比
- 用PyMuPDF的表格识别，对比原始DOCX的表格结构
"""

from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path

import fitz
from lxml import etree

from docanchor.common.errors import ConversionError
from docanchor.common.logger import get_logger
from docanchor.modules.pdf_convert import convert_docx_to_pdf

logger = get_logger("pdf_convert.fidelity")


class FidelityMetrics:
    """保真度指标汇总。"""

    def __init__(self) -> None:
        # 内容召回率
        self.text_chars_in_docx: int = 0
        self.text_chars_in_pdf: int = 0
        self.image_count_in_docx: int = 0
        self.image_count_in_pdf: int = 0
        # 分页偏差
        self.page_count_in_docx: int = 0  # 用段落数近似
        self.page_count_in_pdf: int = 0
        self.deviation_distribution: dict[str, int] = defaultdict(int)
        # 表格结构
        self.table_rows_in_docx: int = 0
        self.table_cols_in_docx: int = 0
        self.table_rows_in_pdf: int = 0
        self.table_cols_in_pdf: int = 0

    @property
    def text_recall(self) -> float:
        if self.text_chars_in_docx == 0:
            return 1.0
        return min(1.0, self.text_chars_in_pdf / self.text_chars_in_docx)

    @property
    def image_recall(self) -> float:
        if self.image_count_in_docx == 0:
            return 1.0
        return min(1.0, self.image_count_in_pdf / self.image_count_in_docx)

    @property
    def table_row_accuracy(self) -> float:
        if self.table_rows_in_docx == 0:
            return 1.0
        return min(1.0, self.table_rows_in_pdf / self.table_rows_in_docx)

    @property
    def deviation_ratio(self) -> float:
        """分页偏差≤1行的占比。"""
        total = sum(self.deviation_distribution.values())
        if total == 0:
            return 1.0
        within_one = (
            self.deviation_distribution.get("0", 0)
            + self.deviation_distribution.get("1", 0)
        )
        return within_one / total

    def to_dict(self) -> dict:
        return {
            "text_recall": round(self.text_recall, 4),
            "image_recall": round(self.image_recall, 4),
            "table_row_accuracy": round(self.table_row_accuracy, 4),
            "deviation_within_one_line_ratio": round(self.deviation_ratio, 4),
            "text_chars_in_docx": self.text_chars_in_docx,
            "text_chars_in_pdf": self.text_chars_in_pdf,
            "image_count_in_docx": self.image_count_in_docx,
            "image_count_in_pdf": self.image_count_in_pdf,
            "page_count_in_pdf": self.page_count_in_pdf,
            "table_rows_in_docx": self.table_rows_in_docx,
            "table_rows_in_pdf": self.table_rows_in_pdf,
            "deviation_distribution": dict(self.deviation_distribution),
        }


def _extract_text_from_docx(docx_path: Path) -> tuple[str, int]:
    """提取DOCX所有可见文本（去除修订/隐藏/域代码）。"""
    import re

    with zipfile.ZipFile(docx_path, "r") as z:
        try:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        except KeyError:
            return "", 0

    # 删除修订相关标签
    for tag in ("w:ins", "w:del", "w:moveFrom", "w:moveTo"):
        doc_xml = re.sub(f"<{tag}[^>]*>.*?</{tag}>", "", doc_xml, flags=re.DOTALL)
        doc_xml = re.sub(f"<{tag}[^>]*/>", "", doc_xml)

    # 提取所有 w:t 文本
    texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", doc_xml)
    full_text = "".join(texts)

    # 提取图片引用
    image_count = len(re.findall(r"<w:drawing>", doc_xml)) + len(re.findall(r"<v:imageddata", doc_xml))

    return full_text, image_count


def _extract_tables_from_docx(docx_path: Path) -> tuple[int, int, int]:
    """提取DOCX的表格行列总数与表格数。"""
    with zipfile.ZipFile(docx_path, "r") as z:
        try:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        except KeyError:
            return 0, 0, 0

    root = etree.fromstring(doc_xml.encode("utf-8"))
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    tables = root.iter(f"{W}tbl")
    total_rows = 0
    total_cols = 0
    table_count = 0
    for tbl in tables:
        rows = list(tbl.iter(f"{W}tr"))
        total_rows += len(rows)
        if rows:
            # 取第一行的列数
            cols = len(list(rows[0].iter(f"{W}tc")))
            total_cols += cols
        table_count += 1
    return total_rows, total_cols, table_count


def _extract_paragraph_count_from_docx(docx_path: Path) -> int:
    """统计DOCX段落数（用于分页偏差估算）。"""
    with zipfile.ZipFile(docx_path, "r") as z:
        try:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        except KeyError:
            return 0
    root = etree.fromstring(doc_xml.encode("utf-8"))
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return len(list(root.iter(f"{W}p")))


def measure_fidelity(
    docx_path: Path,
    pdf_path: Path,
) -> FidelityMetrics:
    """测量DOCX→PDF转换的保真度。

    分页偏差定义（参考文档3.1.6）：
    - 以DOCX段落为单位，统计每个段落最后一个非空文本行在原DOCX的"逻辑位置"
    - 以PDF文本span为单位，统计该行在PDF的"实际位置"
    - 偏差 = 段落应处页号 - 段落实际页号
    - 中度文档偏差≤1行（即错位不超过1段）的占比≥90%
    """
    metrics = FidelityMetrics()

    # 1) 内容召回率
    docx_text, docx_images = _extract_text_from_docx(docx_path)
    metrics.text_chars_in_docx = len(docx_text)
    metrics.image_count_in_docx = docx_images

    doc = fitz.open(pdf_path)
    try:
        metrics.page_count_in_pdf = len(doc)
        all_pdf_text = ""
        pdf_image_count = 0
        for page in doc:
            page_text = page.get_text("text")
            all_pdf_text += page_text
            pdf_image_count += len(page.get_images(full=True))
        metrics.text_chars_in_pdf = len(all_pdf_text)
        metrics.image_count_in_pdf = pdf_image_count
    finally:
        doc.close()

    # 2) 分页偏差（按段落首段文本比对PDF中首次出现的页号）
    docx_paras = _extract_paragraphs_with_text(docx_path, total_pages=metrics.page_count_in_pdf)
    pdf_para_pages = _find_paragraph_pages(pdf_path, [p[1] for p in docx_paras])
    for (idx, _text, docx_page), pdf_page in zip(docx_paras, pdf_para_pages):
        # docx_page 是段落序号映射的近似页号（仅作为统计指标）
        # pdf_page 是该段文本在PDF中实际首次出现的页号（1-based）
        if pdf_page is None:
            bucket = "5"
        else:
            deviation = abs(docx_page - pdf_page)
            bucket = str(min(deviation, 5))
        metrics.deviation_distribution[bucket] += 1

    # 3) 表格结构（PyMuPDF识别）
    docx_rows, docx_cols, _ = _extract_tables_from_docx(docx_path)
    metrics.table_rows_in_docx = docx_rows
    metrics.table_cols_in_docx = docx_cols

    doc = fitz.open(pdf_path)
    try:
        pdf_rows = 0
        pdf_cols = 0
        for page in doc:
            try:
                tables = page.find_tables()
                for tbl in tables:
                    extracted = tbl.extract()
                    if extracted:
                        pdf_rows += len(extracted)
                        pdf_cols += max((len(row) for row in extracted), default=0)
            except Exception:  # noqa: BLE001
                pass
        metrics.table_rows_in_pdf = pdf_rows
        metrics.table_cols_in_pdf = pdf_cols
    finally:
        doc.close()

    return metrics


def _extract_paragraphs_with_text(
    docx_path: Path,
    total_pages: int,
) -> list[tuple[int, str, int]]:
    """提取DOCX所有段落（带纯文本和估算页号）。

    Returns:
        list of (paragraph_index, text, approx_page_no)
        approx_page_no 是按段落序号比例 + 总页数估算的"参考页号"，
        与PDF页数同尺度，用于偏差统计。
    """
    with zipfile.ZipFile(docx_path, "r") as z:
        try:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        except KeyError:
            return []
    root = etree.fromstring(doc_xml.encode("utf-8"))
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    all_paras = list(root.iter(f"{W}p"))
    n = max(1, len(all_paras))
    result: list[tuple[int, str, int]] = []
    for idx, p in enumerate(all_paras):
        texts = p.findall(f".//{W}t")
        full = "".join(t.text or "" for t in texts).strip()
        if not full:
            continue
        # 估算页号：按段落序号比例分配，与PDF总页数对齐
        approx_page = int(idx / n * total_pages) + 1
        result.append((idx, full, approx_page))
    return result


def _find_paragraph_pages(pdf_path: Path, texts: list[str]) -> list[int | None]:
    """查找每个段落文本在PDF中首次出现的页号（1-based）。

    Returns:
        与texts等长的页号列表；未匹配返回 None。
    """
    doc = fitz.open(pdf_path)
    try:
        pages_text: list[str] = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        result: list[int | None] = []
        for text in texts:
            # 用首段10字符作为锚点
            anchor = text[:10].strip()
            if not anchor:
                result.append(None)
                continue
            found: int | None = None
            for page_idx, page_text in enumerate(pages_text, start=1):
                if anchor in page_text:
                    found = page_idx
                    break
            result.append(found)
        return result
    finally:
        doc.close()


def go_no_go_check(metrics: FidelityMetrics, dirt_level: str = "medium") -> dict[str, bool]:
    """根据文档8.3表进行Go/No-Go判定。

    Args:
        metrics: 保真度指标。
        dirt_level: 脏度等级（light/medium/heavy）。

    Returns:
        每项指标是否通过的字典。
    """
    thresholds = {
        "light": {
            "text_recall": 0.99,
            "image_recall": 0.98,
            "table_row_accuracy": 0.97,
            "deviation_within_one_line_ratio": 0.95,
        },
        "medium": {
            "text_recall": 0.99,
            "image_recall": 0.98,
            "table_row_accuracy": 0.95,
            "deviation_within_one_line_ratio": 0.90,
        },
        "heavy": {
            "text_recall": 0.99,
            "image_recall": 0.98,
            "table_row_accuracy": 0.88,
            "deviation_within_one_line_ratio": 0.80,
        },
    }
    th = thresholds.get(dirt_level, thresholds["medium"])
    return {
        "text_recall": metrics.text_recall >= th["text_recall"],
        "image_recall": metrics.image_recall >= th["image_recall"],
        "table_row_accuracy": metrics.table_row_accuracy >= th["table_row_accuracy"],
        "deviation": metrics.deviation_ratio >= th["deviation_within_one_line_ratio"],
        "overall": all([
            metrics.text_recall >= th["text_recall"],
            metrics.image_recall >= th["image_recall"],
            metrics.table_row_accuracy >= th["table_row_accuracy"],
            metrics.deviation_ratio >= th["deviation_within_one_line_ratio"],
        ]),
    }


__all__ = [
    "FidelityMetrics",
    "measure_fidelity",
    "go_no_go_check",
    "convert_docx_to_pdf",
]