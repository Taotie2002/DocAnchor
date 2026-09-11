"""DocAnchor自定义异常体系。

所有异常都支持降级链路：抛出非致命异常时，调用方应捕获并降级到下一级Provider。
"""

from __future__ import annotations


class DocAnchorError(Exception):
    """所有 DocAnchor 异常的基类。"""


class ConversionError(DocAnchorError):
    """PDF转换失败（LibreOffice/OnlyOffice/Word COM均失败）。"""

    def __init__(self, message: str, engine: str | None = None):
        super().__init__(message)
        self.engine = engine


class AdapterError(DocAnchorError):
    """VLM Adapter 解析失败（重试2次后仍失败）。"""

    def __init__(self, message: str, page_id: int | None = None):
        super().__init__(message)
        self.page_id = page_id


class LLMCallError(DocAnchorError):
    """小模型调用失败（重试耗尽或Schema校验不通过）。"""

    def __init__(
        self,
        message: str,
        task: str | None = None,
        attempts: int | None = None,
    ):
        super().__init__(message)
        self.task = task
        self.attempts = attempts


class SchemaValidationError(DocAnchorError):
    """JSON Schema校验失败。"""

    def __init__(
        self,
        message: str,
        schema_name: str | None = None,
        errors: list[str] | None = None,
    ):
        super().__init__(message)
        self.schema_name = schema_name
        self.errors = errors or []


__all__ = [
    "DocAnchorError",
    "ConversionError",
    "AdapterError",
    "LLMCallError",
    "SchemaValidationError",
]