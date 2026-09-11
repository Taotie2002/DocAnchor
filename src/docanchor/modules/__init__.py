"""业务模块集合。"""

from docanchor.modules import (
    global_aggregate,
    pdf_convert,
    pdf_extract,
    template_render,
    text_verify,
    vlm_adapter,
    xml_cleaner,
)

__all__ = [
    "xml_cleaner",
    "pdf_convert",
    "pdf_extract",
    "vlm_adapter",
    "global_aggregate",
    "text_verify",
    "template_render",
]