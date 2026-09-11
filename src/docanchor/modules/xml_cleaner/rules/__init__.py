"""清洗规则集：每条规则独立可单测、可关闭。"""

from docanchor.modules.xml_cleaner.rules.accept_revisions import accept_all_revisions
from docanchor.modules.xml_cleaner.rules.freeze_fields import freeze_fields
from docanchor.modules.xml_cleaner.rules.remove_strikethrough import remove_strikethrough
from docanchor.modules.xml_cleaner.rules.remove_vanish import remove_vanish
from docanchor.modules.xml_cleaner.rules.strip_comments import strip_comments
from docanchor.modules.xml_cleaner.rules.strip_macros import strip_macros

ALL_RULES = [
    accept_all_revisions,
    remove_vanish,
    remove_strikethrough,
    strip_comments,
    freeze_fields,
    strip_macros,
]

__all__ = [
    "accept_all_revisions",
    "freeze_fields",
    "remove_strikethrough",
    "remove_vanish",
    "strip_comments",
    "strip_macros",
    "ALL_RULES",
]