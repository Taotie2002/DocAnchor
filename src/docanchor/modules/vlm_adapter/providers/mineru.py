"""真实 MinerU Provider（接入 mineru.net API）。

接口：异步任务
- POST /api/v4/extract/task 提交任务（需 PDF URL）
- GET /api/v4/extract/task/{task_id} 轮询结果
- 结果为 zip 包（含 Markdown + layout JSON + 中间文件）

注意：
- 标准 API 要求 PDF 通过 URL 访问（不支持直接传文件）
- 阶段2本机 PDF 需先上传到公网/对象存储才能用 MinerU 标准 API
- 替代方案：本地用 magic-pdf 离线跑 MinerU（开源、避免网络上传）
"""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from io import BytesIO
from pathlib import Path

from docanchor.common.idgen import new_block_id
from docanchor.common.logger import get_logger
from docanchor.common.schema import Block, BlockType, BoundingBox

logger = get_logger("vlm_adapter.mineru")

_BASE_URL = "https://mineru.net/api/v4/extract/task"
_POLL_INTERVAL = 5  # 秒
_POLL_TIMEOUT = 600  # 单次任务最长 10 分钟


def _get_cache_dir() -> Path:
    """获取MinerU缓存目录（可由环境变量覆盖）。"""
    custom = os.environ.get("DOCANCHOR_MINERU_CACHE")
    if custom:
        return Path(custom)
    # 默认放cwd下
    return Path.cwd() / ".mineru_cache"

logger = get_logger("vlm_adapter.mineru")

_BASE_URL = "https://mineru.net/api/v4/extract/task"
_POLL_INTERVAL = 5  # 秒
_POLL_TIMEOUT = 600  # 单次任务最长 10 分钟


class MinerUProvider:
    """真实MinerU API Provider（异步任务接口）。"""

    name = "mineru"

    def __init__(self, token: str, model: str = "vlm"):
        if not token:
            raise ValueError("MinerU token is required")
        self.token = token
        self.model = model
        self.base_url = _BASE_URL
        self._import_http()  # 预加载 requests

    def _import_http(self) -> None:
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "requests未安装。请运行: pip install requests"
            ) from e

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _post_task(self, pdf_url: str) -> str:
        """提交异步任务，返回 task_id。"""
        import requests

        payload = {
            "url": pdf_url,
            "model_version": self.model,
            "is_ocr": False,
            "enable_formula": True,
            "enable_table": True,
            "language": "ch",
        }
        logger.info(f"MinerU提交任务: {pdf_url}")
        resp = requests.post(
            self.base_url, headers=self._headers(), json=payload, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", -1) != 0:
            raise RuntimeError(f"MinerU提交失败: {data}")
        task_id = data["data"]["task_id"]
        logger.info(f"MinerU task_id={task_id}")
        return task_id

    def _poll_result(self, task_id: str) -> dict:
        """轮询任务状态直到完成或超时。"""
        import requests

        import urllib.parse
        poll_url = f"{self.base_url}/{task_id}"
        start = time.time()
        while time.time() - start < _POLL_TIMEOUT:
            resp = requests.get(poll_url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", -1) != 0:
                raise RuntimeError(f"MinerU轮询失败: {data}")
            state = data["data"].get("state", "")
            logger.debug(f"MinerU task {task_id} state={state}")
            if state == "done":
                return data["data"]
            if state == "failed":
                raise RuntimeError(
                    f"MinerU任务失败: {data['data'].get('err_msg', '')}"
                )
            time.sleep(_POLL_INTERVAL)
        raise TimeoutError(f"MinerU任务超时（>{_POLL_TIMEOUT}s）")

    def _download_zip(self, zip_url: str, dest_dir: Path) -> Path:
        """下载结果zip并解压。"""
        import requests

        dest_dir.mkdir(parents=True, exist_ok=True)
        zip_path = dest_dir / "mineru_result.zip"
        resp = requests.get(zip_url, timeout=120)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
        # 解压
        extract_dir = dest_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(BytesIO(resp.content)) as z:
            z.extractall(extract_dir)
        return extract_dir

    def _parse_mineru_output(self, extract_dir: Path) -> list[list[Block]]:
        """解析MinerU的输出为标准Block列表。

        MinerU zip 解压后通常包含：
        - <name>_content_list_v2.json：详细content list（含 type, level, bbox）
        - <name>_content_list.json：简化 content list
        - <name>_model.json：layout信息
        - full.md：Markdown汇总
        - images/：提取的图片
        """
        # 优先 v2（最详细，含type/level）
        v2_files = list(extract_dir.glob("*_content_list_v2.json"))
        if v2_files:
            return self._parse_content_list_v2(v2_files[0])

        # 简化v1
        content_list = list(extract_dir.glob("*_content_list.json"))
        if content_list:
            return self._parse_content_list(content_list[0])

        # 兜底 layout.json
        layout_files = list(extract_dir.glob("*layout*.json"))
        if layout_files:
            return self._parse_layout_json(layout_files[0])

        # 兜底任意 json
        json_files = [
            f for f in extract_dir.glob("*.json")
            if "_content_list" not in f.name and "layout" not in f.name
        ]
        if json_files:
            return self._parse_layout_json(json_files[0])

        # 兜底 Markdown
        md_files = list(extract_dir.glob("*.md"))
        if md_files:
            return self._parse_markdown(md_files[0])

        logger.warning("MinerU结果无可用文件，回退到空列表")
        return []

    def _parse_content_list_v2(self, json_path: Path) -> list[list[Block]]:
        """从MinerU v2 content_list解析。

        v2结构（按页分组的list of items）：
        [
          [  # page 0
            {"type": "title", "content": {"title_content": [...], "level": 1}, "bbox": [...]},
            {"type": "paragraph", "content": {"paragraph_content": [...]}, "bbox": [...]},
            {"type": "table", "content": {...}, "bbox": [...]},
          ],
          [  # page 1
            ...
          ],
        ]
        """
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning(f"content_list_v2.json非list: {type(data)}")
            return []

        pages: list[list[Block]] = []
        for page_idx, page_items in enumerate(data):
            if not isinstance(page_items, list):
                continue
            page_blocks: list[Block] = []
            for item in page_items:
                if not isinstance(item, dict):
                    continue
                bbox_list = item.get("bbox") or [0, 0, 0, 0]
                if len(bbox_list) != 4:
                    continue

                raw_type = item.get("type") or "text"
                content = item.get("content") or {}
                text = self._extract_text_from_v2_content(content, raw_type)
                block_type, local_level = self._map_type_v2(raw_type, content)

                if block_type == BlockType.TABLE:
                    text = text[:200]  # 限长

                page_blocks.append(
                    Block(
                        page_id=page_idx + 1,
                        block_id=new_block_id(),
                        bbox=BoundingBox(
                            x1=float(bbox_list[0]),
                            y1=float(bbox_list[1]),
                            x2=float(bbox_list[2]),
                            y2=float(bbox_list[3]),
                        ),
                        block_type=block_type,
                        local_level=local_level,
                        text=text,
                        confidence=0.9,
                        vlm_model_version=self.version(),
                    )
                )
            if page_blocks:
                pages.append(page_blocks)
        return pages

    def _extract_text_from_v2_content(self, content: dict, raw_type: str) -> str:
        """从v2 content嵌套结构提取纯文本。"""
        # 多种content结构兼容
        if isinstance(content, str):
            return content.strip()

        # title_content / paragraph_content / table_content / ...
        text_key = f"{raw_type}_content"
        if text_key in content and isinstance(content[text_key], list):
            parts = []
            for sub in content[text_key]:
                if isinstance(sub, dict):
                    parts.append(sub.get("content") or sub.get("text") or "")
                elif isinstance(sub, str):
                    parts.append(sub)
            return "\n".join(parts).strip()

        # 通用：递归提取所有"content"字段
        texts: list[str] = []

        def _walk(obj):
            if isinstance(obj, str):
                texts.append(obj)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("text", "content") and isinstance(v, str):
                        texts.append(v)
                    elif isinstance(v, (dict, list)):
                        _walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    _walk(x)

        _walk(content)
        return " ".join(texts).strip()

    def _map_type_v2(
        self, raw_type: str, content: dict
    ) -> tuple[BlockType, int | None]:
        """v2类型映射，支持嵌套content的level字段。"""
        raw = str(raw_type).lower()
        if raw in ("title", "heading", "head"):
            # 从content.level提取
            level = content.get("level") if isinstance(content, dict) else None
            try:
                level_int = int(level) if level is not None else 1
            except (ValueError, TypeError):
                level_int = 1
            level_int = max(1, min(6, level_int))
            return BlockType.TITLE, level_int
        if raw in ("table",):
            return BlockType.TABLE, None
        if raw in ("image", "figure", "picture"):
            return BlockType.IMAGE, None
        if raw in ("equation", "formula"):
            return BlockType.FORMULA, None
        if raw in ("list", "list_item", "list-item"):
            return BlockType.LIST, None
        if raw in ("caption", "figure_caption", "table_caption"):
            return BlockType.CAPTION, None
        if raw in ("text", "paragraph"):
            return BlockType.PARAGRAPH, None
        return BlockType.PARAGRAPH, None

    def _parse_content_list(self, json_path: Path) -> list[list[Block]]:
        """从MinerU v1 content_list.json解析。

        v1结构（flat list of items）：
        [
            {"type": "text", "text": "...", "bbox": [x1,y1,x2,y2], "page_idx": 0},
            ...
        ]
        """
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning(f"content_list.json非list: {type(data)}")
            return []

        by_page: dict[int, list[Block]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            page_idx = item.get("page_idx", 0)
            bbox_list = item.get("bbox") or [0, 0, 0, 0]
            if len(bbox_list) != 4:
                continue
            text = (item.get("text") or "").strip()
            raw_type = item.get("type") or "text"
            block_type, local_level = self._map_type(raw_type)
            if block_type == BlockType.TABLE:
                text = text[:200]

            block = Block(
                page_id=page_idx + 1,
                block_id=new_block_id(),
                bbox=BoundingBox(
                    x1=float(bbox_list[0]),
                    y1=float(bbox_list[1]),
                    x2=float(bbox_list[2]),
                    y2=float(bbox_list[3]),
                ),
                block_type=block_type,
                local_level=local_level,
                text=text,
                confidence=0.9,
                vlm_model_version=self.version(),
            )
            by_page.setdefault(page_idx + 1, []).append(block)
        return [by_page[k] for k in sorted(by_page.keys())]

    def _parse_layout_json(self, layout_path: Path) -> list[list[Block]]:
        """从MinerU model.json或layout.json解析（兼容旧格式）。"""
        data = json.loads(layout_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []

        pages: list[list[Block]] = []
        for key, value in data.items():
            if not key.startswith("page_") or not isinstance(value, dict):
                continue
            try:
                page_id = int(key.replace("page_", "")) + 1
            except ValueError:
                continue

            blocks_data = value.get("blocks") or value.get("para_blocks") or []
            page_blocks: list[Block] = []
            for b in blocks_data:
                bbox_list = b.get("bbox") or [0, 0, 0, 0]
                if len(bbox_list) != 4:
                    continue
                text = (b.get("text") or b.get("content") or "").strip()
                raw_type = b.get("type") or b.get("block_type") or "text"
                block_type, local_level = self._map_type(raw_type)

                page_blocks.append(
                    Block(
                        page_id=page_id,
                        block_id=new_block_id(),
                        bbox=BoundingBox(
                            x1=float(bbox_list[0]),
                            y1=float(bbox_list[1]),
                            x2=float(bbox_list[2]),
                            y2=float(bbox_list[3]),
                        ),
                        block_type=block_type,
                        local_level=local_level,
                        text=text,
                        confidence=float(b.get("score", 0.85)),
                        vlm_model_version=self.version(),
                    )
                )
            if page_blocks:
                pages.append(page_blocks)
        return pages

    def _map_type(self, raw: str) -> tuple[BlockType, int | None]:
        """映射MinerU类型到标准BlockType。"""
        raw = str(raw).lower()
        if raw in ("title", "heading", "head"):
            return BlockType.TITLE, 1
        if raw in ("table",):
            return BlockType.TABLE, None
        if raw in ("image", "figure", "picture"):
            return BlockType.IMAGE, None
        if raw in ("equation", "formula"):
            return BlockType.FORMULA, None
        if raw in ("list", "list_item", "list-item"):
            return BlockType.LIST, None
        if raw in ("caption", "figure_caption", "table_caption"):
            return BlockType.CAPTION, None
        return BlockType.PARAGRAPH, None

    def _parse_markdown(self, md_path: Path) -> list[list[Block]]:
        """从MinerU的Markdown提取。"""
        lines = md_path.read_text(encoding="utf-8").splitlines()
        block = Block(
            page_id=1,
            block_id=new_block_id(),
            bbox=BoundingBox(x1=0, y1=0, x2=595, y2=842),
            block_type=BlockType.PARAGRAPH,
            text="\n".join(lines),
            confidence=0.8,
            vlm_model_version=self.version(),
        )
        return [[block]]

    def parse(self, pdf_path: Path) -> list[list[Block]]:
        """解析PDF。

        MinerU 标准API仅支持公网URL。Adapter 期望传入的是URL或可下载的远端PDF。
        本地PDF需先上传到公网（建议使用 MinerU 的 /file-urls/batch 端点）。

        Args:
            pdf_path: PDF文件路径（仅支持URL）。

        Returns:
            list[list[Block]]：每页一个Block列表。
        """
        pdf_str = str(pdf_path)
        if pdf_str.startswith("http://") or pdf_str.startswith("https://"):
            return self._parse_url(pdf_str)
        raise NotImplementedError(
            "MinerU标准API需PDF公网URL。调用方应先上传PDF或使用本地开源版。"
        )

    def _parse_url(self, pdf_url: str) -> list[list[Block]]:
        """从URL解析。"""
        task_id = self._post_task(pdf_url)
        result = self._poll_result(task_id)

        zip_url = result.get("full_zip_url")
        if not zip_url:
            raise RuntimeError(f"MinerU结果无zip URL: {result}")

        work_dir = _get_cache_dir() / task_id
        extract_dir = self._download_zip(zip_url, work_dir)
        return self._parse_mineru_output(extract_dir)

    def parse_url(self, pdf_url: str) -> list[list[Block]]:
        """从URL解析PDF的便捷方法。"""
        return self._parse_url(pdf_url)

    def version(self) -> str:
        return f"mineru-{self.model}-api"


__all__ = ["MinerUProvider"]