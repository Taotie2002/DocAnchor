"""Word COM 转换（3.1.4兜底，仅Windows）。

通过 pywin32 调用 Microsoft Word 进行转换。
仅在 Windows 平台可用。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from docanchor.common.logger import get_logger

logger = get_logger("pdf_convert.word_com")


def is_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401

        return True
    except ImportError:
        return False


def convert(input_path: Path, output_dir: Path) -> Path:
    """通过 Word COM 转换。

    Raises:
        RuntimeError: 非Windows或Word未安装。
    """
    if sys.platform != "win32":
        raise RuntimeError("Word COM仅支持Windows平台")
    try:
        import win32com.client
    except ImportError as e:
        raise RuntimeError("pywin32未安装: pip install pywin32") from e

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    word = win32com.client.Dispatch("Word.Application")
    try:
        word.Visible = False
        # 关闭修订/隐藏/批注显示
        try:
            word.Options.ShowRevisions = False
        except Exception:  # noqa: BLE001
            pass

        abs_input = str(input_path.resolve())
        abs_output = str((output_dir / (input_path.stem + ".pdf")).resolve())

        doc = word.Documents.Open(abs_input)
        try:
            # wdExportFormatPDF = 17
            doc.ExportAsFixedFormat(
                OutputFileName=abs_output,
                ExportFormat=17,
                OpenAfterExport=False,
                OptimizeFor=0,  # wdOptimizeForPrint
                Range=0,  # wdExportAllDocument
                Item=0,
                IncludeDocProps=True,
                KeepIRM=True,
                CreateBookmarks=0,
                DocStructureTags=True,
                BitmapMissingFonts=True,
                UseISO19005_1=False,
            )
        finally:
            doc.Close(SaveChanges=False)
    finally:
        word.Quit()

    output_pdf = output_dir / (input_path.stem + ".pdf")
    if not output_pdf.exists():
        raise RuntimeError(f"Word COM未生成PDF: {output_pdf}")
    logger.info(f"Word COM转换成功: {output_pdf}")
    return output_pdf


__all__ = ["is_available", "convert"]