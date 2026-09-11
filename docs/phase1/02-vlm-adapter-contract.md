# VLM/MinerU Adapter 接口契约

> 阶段1交付物之一。本文定义 VLM Adapter 的标准接口契约、Provider 扩展点与异常处理流程。

## 1. 设计目标

将不同 VLM Provider（MinerU / Donut / Pix2Struct 等）的输出统一归一化为标准 Block 结构，使下游链路对 Provider 无感知。

## 2. 标准 Block Schema

详见 `src/docanchor/common/schema.py::Block`。

### 2.1 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `page_id` | int (≥1) | 页码 |
| `block_id` | str | 页内唯一ID |
| `bbox` | BoundingBox | PDF原生坐标系 [x1,y1,x2,y2] |
| `block_type` | BlockType | 枚举值，见下表 |
| `text` | str | 识别纯文本 |
| `confidence` | float (0-1) | 识别置信度 |
| `vlm_model_version` | str | Provider版本标识 |

### 2.2 block_type 枚举

```python
class BlockType(str, Enum):
    TITLE = "title"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    CAPTION = "caption"
    FORMULA = "formula"
```

## 3. Provider 接口契约

### 3.1 抽象基类

```python
from abc import ABC, abstractmethod
from pathlib import Path

class BaseVLMProvider(ABC):
    name: str  # provider标识符

    @abstractmethod
    def parse(self, pdf_path: Path) -> list[list[Block]]:
        """解析PDF，按页返回Block数组。"""

    @abstractmethod
    def version(self) -> str:
        """返回Provider版本标识。"""
```

### 3.2 已实现 Provider

| Provider | 版本 | 适用场景 |
|----------|------|---------|
| `MockVLMProvider` | mock-0.1.0 | 开发与测试，基于PyMuPDF文本层 |
| `MinerUProvider` | mineru-pending | 阶段2接入真实MinerU |

## 4. Adapter 处理流程

```
Provider.parse()
   ↓ 原始输出
normalizer.normalize_block_type()  # 结构归一化
   ↓
coordinate_align.align_coordinates()  # 坐标对齐
   ↓
validator.validate_blocks()  # 二次校验
   ↓
filter.filter_blocks()  # 异常过滤
   ↓
version_lock  # 注入模型版本号
   ↓
标准Block列表
```

## 5. 异常处理与降级

### 5.1 重试策略

- `vlm_max_retries`（默认2）：Schema校验/解析失败自动重试
- 重试耗尽后触发降级

### 5.2 降级路径

当所有重试失败时：
1. `vlm_fallback_to_pymupdf=True`（默认）：使用 `MockVLMProvider` 作为降级，标注 `confidence=0.5` 与 `vlm_model_version="fallback-pymupdf"`
2. `vlm_fallback_to_pymupdf=False`：抛出 `AdapterError`

### 5.3 异常类型

```python
class AdapterError(DocAnchorError):
    def __init__(self, message: str, page_id: int | None = None):
        super().__init__(message)
        self.page_id = page_id
```

## 6. JSON Schema（输出Block列表）

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": ["page_id", "block_id", "bbox", "block_type", "text", "confidence"],
    "properties": {
      "page_id": {"type": "integer", "minimum": 1},
      "block_id": {"type": "string"},
      "bbox": {
        "type": "object",
        "properties": {
          "x1": {"type": "number"},
          "y1": {"type": "number"},
          "x2": {"type": "number"},
          "y2": {"type": "number"}
        }
      },
      "block_type": {"enum": ["title", "paragraph", "table", "list", "image", "caption", "formula"]},
      "local_level": {"type": ["integer", "null"], "minimum": 1, "maximum": 6},
      "text": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "markdown_content": {"type": "string"},
      "vlm_model_version": {"type": "string"}
    }
  }
}
```

## 7. 接入新Provider指南

1. 继承 `BaseVLMProvider` 或仿照 `MockVLMProvider` 实现 `parse()` 与 `version()`
2. 在 `src/docanchor/modules/vlm_adapter/providers/` 下添加文件
3. 在 `__init__.py` 中导出
4. 在 `config.py` 中扩展 `vlm_provider` 枚举值
5. 在 `adapter.py::get_default_adapter()` 添加分支
6. 编写单元测试，覆盖正常输出与边界场景

## 8. 测试覆盖

| 测试 | 文件 |
|------|------|
| MockVLM Provider parse | `tests/unit/test_vlm_adapter.py::TestMockVLMProvider` |
| filter_blocks | `tests/unit/test_vlm_adapter.py::TestFilterBlocks` |
| normalizer/coordinate_align/validator | 待阶段1第7-8天补齐 |