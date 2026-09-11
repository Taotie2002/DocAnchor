"""公共基础模块：数据结构、日志、ID生成、哈希、异常。"""

from docanchor.common.errors import (
    AdapterError,
    ConversionError,
    DocAnchorError,
    LLMCallError,
    SchemaValidationError,
)

__all__ = [
    "DocAnchorError",
    "ConversionError",
    "AdapterError",
    "LLMCallError",
    "SchemaValidationError",
]