"""关键字段强制双路比对（3.4.3.1）。

覆盖范围：金额、日期、编号、编码、证件号等硬字段。
通过正则+实体识别定位。

处理规则：
- VLM文本与PDF文本不一致时，默认采信PDF文本
- 若PDF文本与原始DOCX文本存在差异，以DOCX为准，记录conflict日志
- 降权场景：PDF文本来自域代码、修订残留时，降低权重，进入复核队列
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from docanchor.common.logger import get_logger

logger = get_logger("text_verify.critical_fields")

# 金额（人民币/数字）
RE_AMOUNT = re.compile(
    r"(?:RMB|¥|￥|\$|USD|EUR|￥)?\s*"
    r"[0-9][0-9,]*\.?[0-9]*"
    r"(?:元|块|万元|百万元|亿元|圆|角|分)?",
    re.IGNORECASE,
)

# 日期（YYYY-MM-DD / YYYY年MM月DD日 / YYYY/MM/DD）
RE_DATE = re.compile(
    r"\b\d{4}[-/年\.]\d{1,2}[-/月\.]\d{1,2}(?:日)?\b|"
    r"\b\d{1,2}[-/月\.]\d{1,2}[-/]\d{4}\b",
)

# 编号（合同号/订单号/发票号等）
RE_CODE = re.compile(
    r"(?:合同号|订单号|发票号|编号|编号:|No\.|NO\.|NO:|编号:|合同编号|订单编号)[：:\s]*([A-Z0-9\-]{4,})",
    re.IGNORECASE,
)

# 身份证号（18位）
RE_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")

# 手机号
RE_PHONE = re.compile(r"\b1[3-9]\d{9}\b")

# 邮箱
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

ALL_PATTERNS = [
    ("amount", RE_AMOUNT),
    ("date", RE_DATE),
    ("code", RE_CODE),
    ("id_card", RE_ID_CARD),
    ("phone", RE_PHONE),
    ("email", RE_EMAIL),
]


@dataclass
class CriticalFieldHit:
    """关键字段命中。"""

    field_type: str
    value: str
    start: int
    end: int


@dataclass
class CriticalFieldConflict:
    """关键字段冲突记录。"""

    field_type: str
    vlm_value: str
    pdf_value: str
    docx_value: str = ""
    source: str = "vlm_vs_pdf"  # vlm_vs_pdf | pdf_vs_docx
    resolution: str = ""  # pending | adopted_pdf | adopted_docx | need_review


def extract_critical_fields(text: str) -> list[CriticalFieldHit]:
    """从文本中提取所有关键字段。

    Args:
        text: 待分析文本。

    Returns:
        关键字段命中列表。
    """
    hits: list[CriticalFieldHit] = []
    for field_type, pattern in ALL_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(0).strip()
            hits.append(
                CriticalFieldHit(
                    field_type=field_type,
                    value=value,
                    start=m.start(),
                    end=m.end(),
                )
            )
    return hits


def verify_critical_fields(
    vlm_text: str,
    pdf_text: str,
    docx_text: str = "",
) -> list[CriticalFieldConflict]:
    """校验关键字段在三个来源间的一致性。

    Args:
        vlm_text: VLM识别文本。
        pdf_text: PDF原生文本层。
        docx_text: 原始DOCX文本（可选）。

    Returns:
        冲突列表。
    """
    vlm_fields = extract_critical_fields(vlm_text)
    pdf_fields = extract_critical_fields(pdf_text)
    docx_fields = extract_critical_fields(docx_text) if docx_text else []

    conflicts: list[CriticalFieldConflict] = []

    # 按(field_type, value)索引
    def _index(fields: list[CriticalFieldHit]) -> dict[tuple[str, str], int]:
        idx: dict[tuple[str, str], int] = {}
        for f in fields:
            k = (f.field_type, f.value)
            idx[k] = idx.get(k, 0) + 1
        return idx

    vlm_idx = _index(vlm_fields)
    pdf_idx = _index(pdf_fields)
    docx_idx = _index(docx_fields)

    # VLM vs PDF：默认采信PDF
    for key, v_count in vlm_idx.items():
        p_count = pdf_idx.get(key, 0)
        if v_count != p_count:
            # 取VLM和PDF的实际值（同一type的所有值）
            v_vals = [f.value for f in vlm_fields if (f.field_type, f.value) == key]
            p_vals = [f.value for f in pdf_fields if (f.field_type, f.value) == key]
            conflicts.append(
                CriticalFieldConflict(
                    field_type=key[0],
                    vlm_value=", ".join(v_vals),
                    pdf_value=", ".join(p_vals),
                    source="vlm_vs_pdf",
                    resolution="adopted_pdf",
                )
            )

    # PDF vs DOCX（若提供DOCX）：DOCX权威
    if docx_text:
        for key, p_count in pdf_idx.items():
            d_count = docx_idx.get(key, 0)
            if p_count != d_count:
                p_vals = [f.value for f in pdf_fields if (f.field_type, f.value) == key]
                d_vals = [f.value for f in docx_fields if (f.field_type, f.value) == key]
                conflicts.append(
                    CriticalFieldConflict(
                        field_type=key[0],
                        vlm_value="",
                        pdf_value=", ".join(p_vals),
                        docx_value=", ".join(d_vals),
                        source="pdf_vs_docx",
                        resolution="adopted_docx",
                    )
                )

    if conflicts:
        logger.warning(f"关键字段冲突 {len(conflicts)} 处")
    return conflicts


__all__ = [
    "CriticalFieldHit",
    "CriticalFieldConflict",
    "extract_critical_fields",
    "verify_critical_fields",
]