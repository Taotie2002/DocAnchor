"""普通文本语义校验（3.4.3.2）。

调用小模型分段通读全文，检测不通顺、歧义、语病。
"""

from __future__ import annotations

from docanchor.common.logger import get_logger

logger = get_logger("text_verify.semantic_check")


def run_semantic_check(
    *,
    text: str,
    client=None,
    context: dict | None = None,
) -> list:
    """对单段文本运行语义校验。

    Args:
        text: 待校验文本。
        client: LLM客户端（None则使用默认Mock，跳过真实校验）。
        context: 可选上下文。

    Returns:
        语义问题列表（SemanticCheckIssue）。
    """
    from docanchor.llm.tasks.semantic_check import semantic_check_text

    if client is None:
        from docanchor.llm import get_default_client
        client = get_default_client()

    try:
        issues = semantic_check_text(client=client, text=text, context=context)
        return list(issues)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"语义校验失败: {e}")
        return []


__all__ = ["run_semantic_check"]