"""XML级元数据清洗（3.1.3）。"""

from docanchor.modules.xml_cleaner.cleaner import (
    CleaningReport,
    clean_docx,
    default_rules,
)

__all__ = ["clean_docx", "CleaningReport", "default_rules"]