"""公共工具单测：idgen/hash/errors/logger。"""

from __future__ import annotations

import pytest

from docanchor.common.errors import (
    AdapterError,
    ConversionError,
    DocAnchorError,
    LLMCallError,
    SchemaValidationError,
)
from docanchor.common.hash import content_hash, dict_hash
from docanchor.common.idgen import (
    new_block_id,
    new_node_id,
    new_object_id,
    reset_counters,
)


class TestIdGen:
    def setup_method(self) -> None:
        reset_counters()

    def test_block_id_format(self) -> None:
        bid = new_block_id()
        assert bid.startswith("block-")
        assert len(bid) == len("block-") + 8

    def test_node_id_format(self) -> None:
        nid = new_node_id()
        assert nid.startswith("node-")

    def test_object_id_format(self) -> None:
        oid = new_object_id()
        assert oid.startswith("obj-")

    def test_ids_distinct(self) -> None:
        ids = {new_block_id() for _ in range(100)}
        assert len(ids) == 100


class TestHash:
    def test_content_hash_deterministic(self) -> None:
        assert content_hash("hello") == content_hash("hello")
        assert content_hash("a") != content_hash("b")

    def test_content_hash_length(self) -> None:
        assert len(content_hash("test")) == 16

    def test_dict_hash_sort_keys(self) -> None:
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert dict_hash(a) == dict_hash(b)

    def test_dict_hash_different(self) -> None:
        assert dict_hash({"x": 1}) != dict_hash({"x": 2})


class TestErrors:
    def test_base_class(self) -> None:
        e = DocAnchorError("test")
        assert str(e) == "test"
        assert isinstance(e, Exception)

    def test_conversion_error(self) -> None:
        e = ConversionError("failed", engine="libreoffice")
        assert e.engine == "libreoffice"

    def test_adapter_error(self) -> None:
        e = AdapterError("failed", page_id=3)
        assert e.page_id == 3

    def test_llm_error(self) -> None:
        e = LLMCallError("failed", task="cross_page_table", attempts=2)
        assert e.task == "cross_page_table"
        assert e.attempts == 2

    def test_schema_error(self) -> None:
        e = SchemaValidationError("invalid", schema_name="block", errors=["a", "b"])
        assert e.schema_name == "block"
        assert len(e.errors) == 2