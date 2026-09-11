"""VLM分页解析（3.2）。

Adapter层归一化MinerU或其他Provider的输出到标准Block Schema。
"""

from docanchor.modules.vlm_adapter.adapter import (
    VLMAdapter,
    get_default_adapter,
    parse_pdf_with_vlm,
)

__all__ = ["VLMAdapter", "get_default_adapter", "parse_pdf_with_vlm"]