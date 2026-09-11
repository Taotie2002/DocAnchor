"""MinerU Provider单测（mocked HTTP，不真实调用API）。"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docanchor.common.schema import BlockType
from docanchor.modules.vlm_adapter.providers.mineru import MinerUProvider


def _make_mineru_v2_json() -> dict[str, Any]:
    """构造一个MinerU v2 content_list的JSON。"""
    return [
        # Page 1
        [
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "Test Paper Title"}],
                    "level": 1,
                },
                "bbox": [100, 100, 500, 130],
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {"type": "text", "content": "First paragraph."}
                    ],
                },
                "bbox": [100, 150, 500, 200],
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {"type": "text", "content": "Section 1."}
                    ],
                },
                "bbox": [100, 220, 500, 250],
            },
        ],
        # Page 2
        [
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "2 Background"}],
                    "level": 2,
                },
                "bbox": [100, 80, 500, 110],
            },
            {
                "type": "table",
                "content": {
                    "table_content": "A | B | C\n1 | 2 | 3",
                },
                "bbox": [100, 130, 500, 200],
            },
        ],
    ]


def _make_result_zip(v2_data: list) -> bytes:
    """构造MinerU结果zip的字节。"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("test_content_list_v2.json", json.dumps(v2_data))
    return buf.getvalue()


class TestMinerUProviderInit:
    def test_init_requires_token(self) -> None:
        with pytest.raises(ValueError, match="token is required"):
            MinerUProvider(token="", model="vlm")

    def test_init_ok(self) -> None:
        provider = MinerUProvider(token="test-token", model="vlm")
        assert provider.token == "test-token"
        assert provider.model == "vlm"
        assert provider.name == "mineru"

    def test_version(self) -> None:
        provider = MinerUProvider(token="t", model="vlm")
        assert provider.version() == "mineru-vlm-api"


class TestMinerUProviderParse:
    def test_parse_v2(self, tmp_path: Path) -> None:
        """端到端mocked parse：v2格式输出能正确解析为Block。"""
        provider = MinerUProvider(token="test-token", model="vlm")

        v2_data = _make_mineru_v2_json()
        zip_bytes = _make_result_zip(v2_data)
        task_id = "fake-task-id"
        cache_dir = tmp_path / "mineru_cache" / task_id
        cache_dir.mkdir(parents=True)

        # Mock HTTP calls：patch系统requests模块
        with patch("requests.post") as mock_post, \
             patch("requests.get") as mock_get:
            # 1) 提交任务返回 task_id
            mock_resp_post = MagicMock()
            mock_resp_post.json.return_value = {
                "code": 0,
                "data": {"task_id": task_id},
            }
            mock_resp_post.raise_for_status = MagicMock()
            # 2) 轮询返回 done
            mock_resp_get = MagicMock()
            mock_resp_get.json.return_value = {
                "code": 0,
                "data": {
                    "task_id": task_id,
                    "state": "done",
                    "full_zip_url": "http://example.com/result.zip",
                },
            }
            mock_resp_get.raise_for_status = MagicMock()
            # 3) 下载zip
            mock_resp_zip = MagicMock()
            mock_resp_zip.content = zip_bytes
            mock_resp_zip.raise_for_status = MagicMock()

            mock_post.return_value = mock_resp_post
            mock_get.side_effect = [mock_resp_get, mock_resp_zip]

            pages = provider.parse_url("http://example.com/paper.pdf")

        # 验证
        assert len(pages) == 2
        # Page 1: 1 title (level 1) + 2 paragraphs
        p1 = pages[0]
        assert p1[0].block_type == BlockType.TITLE
        assert p1[0].local_level == 1
        assert p1[0].text == "Test Paper Title"
        # Page 2: 1 title (level 2) + 1 table
        p2 = pages[1]
        assert p2[0].block_type == BlockType.TITLE
        assert p2[0].local_level == 2
        assert p2[0].text == "2 Background"
        assert p2[1].block_type == BlockType.TABLE

    def test_parse_raises_on_local_path(self) -> None:
        """parse() 拒绝本地路径（仅支持URL）。"""
        provider = MinerUProvider(token="t", model="vlm")
        with pytest.raises(NotImplementedError, match="公网URL"):
            provider.parse(Path("/tmp/local.pdf"))

    def test_parse_raises_on_failed_task(self, tmp_path: Path) -> None:
        """任务失败抛RuntimeError。"""
        provider = MinerUProvider(token="test-token", model="vlm")
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            mock_resp_post = MagicMock()
            mock_resp_post.json.return_value = {
                "code": 0,
                "data": {"task_id": "t1"},
            }
            mock_post.return_value = mock_resp_post

            mock_resp_get = MagicMock()
            mock_resp_get.json.return_value = {
                "code": 0,
                "data": {
                    "task_id": "t1",
                    "state": "failed",
                    "err_msg": "service unavailable",
                },
            }
            mock_get.return_value = mock_resp_get

            with pytest.raises(RuntimeError, match="任务失败"):
                provider.parse_url("http://example.com/paper.pdf")

    def test_parse_raises_on_submit_error(self) -> None:
        """提交任务返回错误时抛异常。"""
        provider = MinerUProvider(token="bad-token", model="vlm")
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": -10001,
                "msg": "service error",
            }
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            with pytest.raises(RuntimeError, match="提交失败"):
                provider.parse_url("http://example.com/paper.pdf")


class TestMinerUProviderHelpers:
    def test_map_type_v2(self) -> None:
        provider = MinerUProvider(token="t", model="vlm")
        assert provider._map_type_v2("title", {"level": 2})[0] == BlockType.TITLE
        assert provider._map_type_v2("title", {"level": 2})[1] == 2
        assert provider._map_type_v2("paragraph", {})[0] == BlockType.PARAGRAPH
        assert provider._map_type_v2("table", {})[0] == BlockType.TABLE
        assert provider._map_type_v2("image", {})[0] == BlockType.IMAGE
        assert provider._map_type_v2("formula", {})[0] == BlockType.FORMULA

    def test_extract_text_from_v2_content(self) -> None:
        provider = MinerUProvider(token="t", model="vlm")
        # title_content 结构
        content = {
            "title_content": [{"type": "text", "content": "Hello"}],
            "level": 1,
        }
        text = provider._extract_text_from_v2_content(content, "title")
        assert "Hello" in text
        # 字符串
        text = provider._extract_text_from_v2_content("plain text", "text")
        assert text == "plain text"


class TestCacheDir:
    def test_default_cache_dir(self, monkeypatch) -> None:
        monkeypatch.delenv("DOCANCHOR_MINERU_CACHE", raising=False)
        monkeypatch.chdir(tmp_path := "/tmp")
        from docanchor.modules.vlm_adapter.providers.mineru import _get_cache_dir
        d = _get_cache_dir()
        assert str(d).endswith(".mineru_cache")

    def test_custom_cache_dir(self, monkeypatch) -> None:
        monkeypatch.setenv("DOCANCHOR_MINERU_CACHE", "/custom/path")
        from docanchor.modules.vlm_adapter.providers.mineru import _get_cache_dir
        d = _get_cache_dir()
        assert str(d) == "/custom/path"