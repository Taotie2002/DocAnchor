"""PDF转换主入口（3.1.4）。

提供统一接口 `convert_docx_to_pdf`，自动按降级链路依次尝试每个引擎。

降级链路（默认）：libreoffice → onlyoffice → word_com

引擎切换规则：
1. 优先尝试主选引擎（默认 libreoffice）
2. 捕获异常后，按 fallback_chain 顺序尝试下一引擎
3. 所有引擎失败时抛出 ConversionError
4. 每次降级都会记录在 ConversionReport.fallback_chain 中
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docanchor.common.errors import ConversionError
from docanchor.common.logger import get_logger
from docanchor.config import get_settings

logger = get_logger("pdf_convert")

# 引擎名称到模块的映射
_ENGINES = {
    "libreoffice": "docanchor.modules.pdf_convert.libreoffice",
    "onlyoffice": "docanchor.modules.pdf_convert.onlyoffice",
    "word_com": "docanchor.modules.pdf_convert.word_com",
}


@dataclass
class ConversionReport:
    """转换报告。"""

    input_path: str = ""
    output_path: str = ""
    engine: str = ""
    elapsed_seconds: float = 0.0
    page_count: int = 0
    file_size_bytes: int = 0
    font_replacements: list[str] = field(default_factory=list)
    fallback_triggered: bool = False
    fallback_chain: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "engine": self.engine,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "page_count": self.page_count,
            "file_size_bytes": self.file_size_bytes,
            "font_replacements": self.font_replacements,
            "fallback_triggered": self.fallback_triggered,
            "fallback_chain": self.fallback_chain,
            "errors": self.errors,
        }


def list_available_engines() -> list[str]:
    """列出当前可用的PDF转换引擎。"""
    import importlib

    available: list[str] = []
    for name in ("libreoffice", "onlyoffice", "word_com"):
        try:
            mod = importlib.import_module(_ENGINES[name])
            if mod.is_available():
                available.append(name)
        except Exception:  # noqa: BLE001
            pass
    return available


def convert_docx_to_pdf(
    input_path: Path,
    output_dir: Path,
    *,
    engine: str | None = None,
    fallback_chain: list[str] | None = None,
) -> ConversionReport:
    """DOCX → PDF 转换，带降级链路。

    Args:
        input_path: 输入DOCX路径。
        output_dir: 输出目录，PDF将写入其中。
        engine: 主选引擎，None则从配置读取。
        fallback_chain: 降级链路，None则使用配置的 engine_fallback。

    Returns:
        ConversionReport：含引擎选择、耗时、降级触发等信息。

    Raises:
        ConversionError: 所有引擎均失败。
    """
    import importlib
    import time

    settings = get_settings()
    primary = engine or settings.pdf_engine
    chain = fallback_chain or settings.pdf_engine_fallback
    # 主引擎放第一位
    if primary in chain:
        chain = [primary] + [e for e in chain if e != primary]
    else:
        chain = [primary] + list(chain)

    report = ConversionReport(input_path=str(input_path))
    report.fallback_chain = list(chain)

    last_errors: list[str] = []
    start = time.time()
    for eng in chain:
        try:
            mod = importlib.import_module(_ENGINES[eng])
        except ImportError as e:
            last_errors.append(f"{eng}: 模块不可用 ({e})")
            continue
        if not mod.is_available():
            last_errors.append(f"{eng}: 不可用")
            continue
        try:
            logger.info(f"尝试引擎: {eng}")
            pdf_path = mod.convert(input_path, output_dir)
            report.output_path = str(pdf_path)
            report.engine = eng
            report.elapsed_seconds = time.time() - start
            if eng != chain[0]:
                report.fallback_triggered = True
            # 统计文件信息
            if pdf_path.exists():
                report.file_size_bytes = pdf_path.stat().st_size
                try:
                    import fitz

                    doc = fitz.open(pdf_path)
                    try:
                        report.page_count = len(doc)
                    finally:
                        doc.close()
                except Exception:  # noqa: BLE001
                    pass
            logger.info(
                f"转换成功: engine={eng}, "
                f"pages={report.page_count}, "
                f"size={report.file_size_bytes}"
            )
            return report
        except Exception as e:  # noqa: BLE001
            err = f"{eng}: {type(e).__name__}: {e}"
            last_errors.append(err)
            report.errors.append(err)
            logger.warning(f"引擎 {eng} 失败: {e}")

    # 全部失败
    raise ConversionError(
        f"所有转换引擎均失败 ({len(last_errors)}个尝试): "
        + "; ".join(last_errors),
        engine=primary,
    )


__all__ = ["ConversionReport", "convert_docx_to_pdf", "list_available_engines"]