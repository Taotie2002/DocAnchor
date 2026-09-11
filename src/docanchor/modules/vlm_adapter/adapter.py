"""VLM Adapter 主入口（3.2）。

Adapter层归一化Provider输出到标准Block Schema。
执行 pipeline:
1. Provider原始输出获取
2. 结构归一化（normalizer.normalize_block_type）
3. 坐标对齐（coordinate_align.align_coordinates）
4. 二次校验（validator.validate_blocks）
5. 异常过滤（filter.filter_blocks）
6. 版本锁定（version_lock.current_version）
"""

from __future__ import annotations

from pathlib import Path

from docanchor.common.errors import AdapterError
from docanchor.common.logger import get_logger
from docanchor.common.schema import Block
from docanchor.config import get_settings
from docanchor.modules.vlm_adapter import (
    coordinate_align,
    filter as vlm_filter,
    normalizer,
    validator,
    version_lock,
)

logger = get_logger("vlm_adapter.adapter")


class VLMAdapter:
    """VLM Adapter：将Provider输出归一化为标准Block Schema。"""

    def __init__(self, provider):
        self.provider = provider
        self.settings = get_settings()

    def parse_pdf(self, pdf_path: Path | str) -> list[list[Block]]:
        """解析PDF，按页返回Block数组。

        Args:
            pdf_path: PDF文件路径或URL字符串。

        Returns:
            list[list[Block]]：每页一个Block列表。

        Raises:
            AdapterError: 解析失败且重试耗尽。
        """
        # 归一化：接受 Path 或 str；URL 用 str
        # 注意：Path("https://...") 会把 // 变 /，所以URL场景必须保留为str
        if isinstance(pdf_path, Path):
            # Path对象：保持原样（本地文件用）
            path_obj = pdf_path
            pdf_str = str(pdf_path)
            is_url = False
        elif isinstance(pdf_path, str):
            if pdf_path.startswith("http://") or pdf_path.startswith("https://"):
                # URL: 直接用str（避免Path转URL时丢失双斜杠）
                path_obj = None
                pdf_str = pdf_path
                is_url = True
            else:
                # 本地文件路径
                path_obj = Path(pdf_path)
                pdf_str = pdf_path
                is_url = False
        else:
            raise TypeError(f"pdf_path必须是Path或str，得到{type(pdf_path)}")

        max_retries = self.settings.vlm_max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return self._parse_with_pipeline(pdf_path, is_url)
            except AdapterError:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning(
                    f"VLM解析失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                )

        # 重试耗尽：尝试降级到PyMuPDF文本+规则分块（仅本地PDF）
        if self.settings.vlm_fallback_to_pymupdf and not is_url and path_obj:
            logger.warning("VLM重试耗尽，降级到PyMuPDF文本+规则分块")
            return self._fallback_to_pymupdf(path_obj)

        raise AdapterError(
            f"VLM解析失败（重试{max_retries + 1}次）: {last_error}"
        )

    def _parse_with_pipeline(self, pdf_path: str, is_url: bool) -> list[list[Block]]:
        """执行完整的Adapter pipeline。

        Args:
            pdf_path: PDF路径字符串。
            is_url: 是否为URL。
        """
        # 1) Provider原始输出
        if is_url and hasattr(self.provider, "parse_url"):
            raw_pages = self.provider.parse_url(pdf_path)
        else:
            # 本地路径：转回Path对象传给provider
            raw_pages = self.provider.parse(Path(pdf_path))
        model_version = self.provider.version()

        # 2) 逐页处理
        # URL场景：用raw_pages的长度作为页数；本地场景用fitz.open获取
        if is_url:
            n_pages = len(raw_pages)
        else:
            doc = fitz.open(pdf_path)
            try:
                n_pages = len(doc)
            finally:
                doc.close()

        result: list[list[Block]] = []
        for page_idx in range(min(len(raw_pages), n_pages)):
            if is_url:
                # URL场景无法直接获取page size，从blocks的bbox推断
                page_size = self._infer_page_size_from_blocks(raw_pages[page_idx])
            else:
                page_size = self._get_page_size(pdf_path, page_idx)
            page_blocks = raw_pages[page_idx]
            normalized = self._normalize_page(page_blocks, page_size, model_version)
            result.append(normalized)

        logger.info(
            f"VLM Adapter: {len(result)}页, "
            f"总计 {sum(len(p) for p in result)} 个Block"
        )
        return result

    def _infer_page_size_from_blocks(
        self, blocks: list[Block], default: tuple[float, float] = (595.0, 842.0)
    ) -> tuple[float, float]:
        """从blocks推断页面尺寸（URL场景无PDF元数据）。"""
        if not blocks:
            return default
        max_x = max((b.bbox.x2 for b in blocks), default=default[0])
        max_y = max((b.bbox.y2 for b in blocks), default=default[1])
        # 用max+一点padding作为页面尺寸
        return (max(max_x + 10, default[0]), max(max_y + 10, default[1]))

    def _normalize_page(
        self,
        blocks: list[Block],
        page_size: tuple[float, float],
        model_version: str,
    ) -> list[Block]:
        """对单页Block做归一化+校验+过滤。"""
        # 1) 结构归一化（已在Provider层处理，Adapter层再做防御性归一）
        normalized: list[Block] = []
        for b in blocks:
            try:
                b.block_type = normalizer.normalize_block_type(b.block_type.value)
            except (KeyError, ValueError):
                b.block_type = b.block_type  # type: ignore[assignment]
            normalized.append(b)

        # 2) 坐标对齐
        for b in normalized:
            aligned = coordinate_align.align_coordinates(
                bbox=[b.bbox.x1, b.bbox.y1, b.bbox.x2, b.bbox.y2],
                page_size=page_size,
            )
            b.bbox = type(b.bbox)(  # type: ignore[call-arg]
                x1=aligned[0], y1=aligned[1], x2=aligned[2], y2=aligned[3]
            )

        # 3) 二次校验
        validated = validator.validate_blocks(normalized)

        # 4) 异常过滤
        filtered = vlm_filter.filter_blocks(validated, page_size)

        # 5) 设置模型版本
        for b in filtered:
            if not b.vlm_model_version:
                b.vlm_model_version = model_version

        return filtered

    def _get_page_size(self, pdf_path: Path, page_idx: int) -> tuple[float, float]:
        """获取PDF单页尺寸。"""
        import fitz

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_idx]
            return (page.rect.width, page.rect.height)
        finally:
            doc.close()

    def _fallback_to_pymupdf(self, pdf_path: Path) -> list[list[Block]]:
        """降级路径：直接用PyMuPDF文本span生成Block（标注低置信度）。"""
        from docanchor.common.idgen import new_block_id
        from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider

        # MockVLMProvider已经基于PyMuPDF，作为降级实现
        provider = MockVLMProvider()
        pages = provider.parse(pdf_path)
        for page_blocks in pages:
            for b in page_blocks:
                b.confidence = 0.5  # 降级标记
                b.vlm_model_version = "fallback-pymupdf"
        return pages


def get_default_adapter() -> VLMAdapter:
    """根据配置创建默认Adapter。"""
    import os

    settings = get_settings()
    if settings.vlm_provider == "mineru":
        from docanchor.modules.vlm_adapter.providers.mineru import MinerUProvider

        # 从环境变量读取token
        token = os.environ.get("DOCANCHOR_MINERU_TOKEN", "")
        if not token:
            logger.warning(
                "DOCANCHOR_MINERU_TOKEN未配置，回退到MockVLMProvider。"
                "设置DOCANCHOR_MINERU_TOKEN=<your-token>后重启生效。"
            )
            from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider
            return VLMAdapter(MockVLMProvider())
        provider = MinerUProvider(token=token, model="vlm")
    else:
        from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider

        provider = MockVLMProvider()
    return VLMAdapter(provider)


def parse_pdf_with_vlm(pdf_path: Path) -> list[list[Block]]:
    """便捷函数：使用默认Adapter解析。"""
    return get_default_adapter().parse_pdf(pdf_path)


__all__ = ["VLMAdapter", "get_default_adapter", "parse_pdf_with_vlm"]