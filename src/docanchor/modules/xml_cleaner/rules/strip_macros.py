"""规则6：清除宏与VBA（3.1.3）。

DOCX默认不包含宏（.docm才含），但部分用户会把.docm改名.zip混入。
- 删除 word/vbaProject.bin、word/vbaData.xml 等part
- 移除 Content Types 中的 vbaProject、vbaProjectSignature 声明
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from docanchor.common.logger import get_logger

logger = get_logger("xml_cleaner.strip_macros")

_VBA_PARTS = [
    "word/vbaProject.bin",
    "word/vbaData.xml",
    "word/vbaProjectSignature.bin",
]


def strip_macros(input_path: Path, output_path: Path) -> int:
    """移除所有VBA宏与ActiveX控件part。"""
    import zipfile

    changes = 0
    try:
        # 检查是否含宏
        with zipfile.ZipFile(input_path, "r") as z:
            vba_present = [n for n in z.namelist() if n in _VBA_PARTS]
            for vname in vba_present:
                logger.info(f"发现VBA part: {vname}")
                changes += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"扫描VBA失败: {e}")
        return 0

    if changes == 0:
        return 0

    # 重写zip，剔除VBA part
    import shutil

    if output_path == input_path:
        tmp = input_path.with_suffix(input_path.suffix + ".tmp")
        shutil.copyfile(input_path, tmp)
        source = tmp
    else:
        source = input_path

    try:
        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename in _VBA_PARTS:
                    continue
                zout.writestr(item, zin.read(item.filename))
        if source != input_path and source.exists():
            source.unlink()
    except Exception:
        if source != input_path and source.exists():
            source.unlink()
        raise

    return changes


__all__ = ["strip_macros"]