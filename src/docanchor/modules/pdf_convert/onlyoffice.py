"""OnlyOffice Document Server 转换（3.1.4备选）。

通过 HTTP API 调用 OnlyOffice Community Server 转换服务。
需要设置环境变量 DOCANCHOR_ONLYOFFICE_URL。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from docanchor.common.logger import get_logger

logger = get_logger("pdf_convert.onlyoffice")


def is_available() -> bool:
    url = os.environ.get("DOCANCHOR_ONLYOFFICE_URL", "")
    return bool(url)


def convert(input_path: Path, output_dir: Path, *, timeout: int = 180) -> Path:
    """通过 OnlyOffice HTTP API 转换。

    Args:
        input_path: 输入DOCX。
        output_dir: 输出目录。
        timeout: 超时秒数。

    Returns:
        生成的PDF路径。

    Raises:
        RuntimeError: 转换失败或服务不可用。
    """
    url = os.environ.get("DOCANCHOR_ONLYOFFICE_URL", "")
    if not url:
        raise RuntimeError("OnlyOffice服务地址未配置: DOCANCHOR_ONLYOFFICE_URL")

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # OnlyOffice 的 converter API 调用
    # 文档: https://api.onlyoffice.com/edition/converter-api
    endpoint = url.rstrip("/") + "/converter"
    output_basename = input_path.stem

    # 使用 curl 调用（避免引入额外依赖）
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pdf = Path(tmpdir) / (input_path.stem + ".pdf")
        cmd = [
            "curl", "-sS",
            "-F", f"file=@{input_path}",
            "-F", "outputtype=pdf",
            "-F", f"title={input_path.stem}",
            endpoint,
            "-o", str(tmp_pdf),
        ]
        logger.info(f"OnlyOffice命令: curl ... {endpoint}")
        start = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"OnlyOffice转换超时（{timeout}s）") from e

        if proc.returncode != 0 or not tmp_pdf.exists() or tmp_pdf.stat().st_size == 0:
            raise RuntimeError(f"OnlyOffice转换失败: {proc.stderr[:500]}")

        # 复制到目标
        target_pdf = output_dir / f"{output_basename}.pdf"
        shutil.copyfile(tmp_pdf, target_pdf)
        elapsed = time.time() - start
        logger.info(f"OnlyOffice转换成功: {target_pdf} 耗时 {elapsed:.2f}s")
        return target_pdf


__all__ = ["is_available", "convert"]