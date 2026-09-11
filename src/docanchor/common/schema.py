"""核心数据结构（文档第4章）。

本模块定义了系统中流转的所有核心数据结构的Pydantic模型，包括：

1. **BoundingBox**：PDF页面坐标 [x1,y1,x2,y2]（点单位）
2. **Block**：VLM分页解析产物，每页一个Block数组（3.2.3）
3. **PdfObjectRef**：PyMuPDF提取的PDF原生对象引用（文本/图片/表格）
4. **GlobalNode**：全局聚合后的统一节点（含分类型扩展字段）
5. **DocumentTree**：全局文档树JSON（唯一标准输出）

设计要点：
- 所有节点共享通用基础字段（4.1）
- 表格/列表/图片/公式按需扩展（4.2）
- 审计与复核扩展字段独立挂在 qa_result / review_resolution
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 注意：hash 模块可能在 docanchor.common 初始化中被部分加载，
# 为避免循环导入问题，使用 sys.modules 直接获取。
import sys as _sys
_hash_mod = _sys.modules.get("docanchor.common.hash")
if _hash_mod is None:
    from docanchor.common.hash import content_hash, dict_hash  # type: ignore
else:
    content_hash = _hash_mod.content_hash  # type: ignore
    dict_hash = _hash_mod.dict_hash  # type: ignore

# ============================================================
# 枚举定义
# ============================================================


class BlockType(str, Enum):
    """VLM分页Block类型（3.2.3）。"""

    TITLE = "title"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    CAPTION = "caption"
    FORMULA = "formula"


class NodeType(str, Enum):
    """全局节点类型（4.1）。"""

    DOCUMENT_ROOT = "document_root"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    CAPTION = "caption"
    FORMULA = "formula"


class PdfObjectKind(str, Enum):
    """PDF原生对象类型。"""

    TEXT_SPAN = "text_span"
    IMAGE = "image"
    TABLE = "table"


class NativeProvenance(str, Enum):
    """原生来源（4.1 native_provenance 字段）。"""

    PDF_TEXT = "PDF文本层"
    ORIGINAL_DOCX = "原始DOCX"
    PURE_VISION = "纯视觉识别"


class SchemaVersion:
    """当前schema版本号。所有节点序列化时携带此版本。"""

    CURRENT = "1.0.0"


# ============================================================
# 基础数据类
# ============================================================


class BoundingBox(BaseModel):
    """PDF页面坐标 [x1, y1, x2, y2]（点单位，PDF原生坐标系）。

    坐标系说明：
    - 原点在页面左下角，X向右递增，Y向上递增
    - 单位为PDF点（1英寸=72点）
    - 与 PyMuPDF 输出的 page.get_text("dict")["blocks"][...]["bbox"] 完全兼容
    """

    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float

    @field_validator("x2", "y2")
    @classmethod
    def _check_positive_size(cls, v: float, info: Any) -> float:
        # 仅在字段存在对应起点时校验，allow x1==x2 / y1==y2 表示零尺寸点
        return v

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def iou(self, other: "BoundingBox") -> float:
        """计算与另一个bbox的IoU。"""
        x1 = max(self.x1, other.x1)
        y1 = max(self.y1, other.y1)
        x2 = min(self.x2, other.x2)
        y2 = min(self.y2, other.y2)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        union = self.width * self.height + other.width * other.height - inter
        return inter / union if union > 0 else 0.0

    def overlaps(self, other: "BoundingBox") -> bool:
        """判断坐标范围是否重叠。"""
        return not (
            self.x2 <= other.x1 or other.x2 <= self.x1
            or self.y2 <= other.y1 or other.y2 <= self.y1
        )

    def to_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]


# ============================================================
# VLM分页Block（3.2.3）
# ============================================================


class Block(BaseModel):
    """VLM单页Block产物（3.2.3）。"""

    page_id: int = Field(..., ge=1, description="页码，从1开始")
    block_id: str = Field(..., description="页内唯一ID，由idgen.new_block_id()生成")
    bbox: BoundingBox
    block_type: BlockType
    local_level: int | None = Field(None, ge=1, le=6, description="页面局部视觉层级，1-6")
    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    markdown_content: str = ""
    vlm_model_version: str = ""
    # 扩展字段：原模型可能输出的额外信息
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_source_bbox(self) -> list[float]:
        """用于填充 GlobalNode.source_bbox。"""
        return self.bbox.to_list()


# ============================================================
# PDF原生对象引用（3.1.5）
# ============================================================


class PdfObjectRef(BaseModel):
    """PyMuPDF提取的PDF原生对象引用。

    包括文本span、图片、表格三类。每类有不同附加属性。
    """

    object_id: str = Field(..., description="PDF原生对象ID")
    kind: PdfObjectKind
    page_id: int
    bbox: BoundingBox
    text: str = ""
    # 图片特有
    image_ref: str | None = None  # 导出文件路径
    width: float | None = None
    height: float | None = None
    # 表格特有
    row_count: int | None = None
    col_count: int | None = None
    cell_matrix: list[list[str]] | None = None
    # 文本特有
    font_name: str | None = None
    font_size: float | None = None
    # 通用扩展
    extras: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 审计与复核扩展字段（4.2 审计扩展字段）
# ============================================================


class QaResult(BaseModel):
    """QA结果（4.2 审计扩展字段）。"""

    structure_pass: bool = False
    table_pass: bool = False
    text_pass: bool = False
    failed_items: list[str] = Field(default_factory=list)


class ReviewResolution(BaseModel):
    """人工复核修正结果（4.2 审计扩展字段）。"""

    reviewer: str = ""
    review_time: datetime | None = None
    before_value: Any = None
    after_value: Any = None
    conclusion: str = ""


# ============================================================
# 分类型扩展字段（4.2）
# ============================================================


class TableExtension(BaseModel):
    """表格类型扩展（4.2 表格类型扩展）。"""

    row_count: int = 0
    col_count: int = 0
    cell_matrix: list[list[str]] = Field(default_factory=list)
    merged_cells: list[list[int]] = Field(
        default_factory=list,
        description="合并单元格坐标 [[r1,c1,r2,c2], ...]",
    )
    has_cross_page: bool = False
    repeat_header: bool = False
    pymupdf_check: Literal["一致", "不一致", "待复核"] = "待复核"


class ListExtension(BaseModel):
    """列表类型扩展（4.2 列表类型扩展）。"""

    list_type: Literal["ordered", "unordered"]
    marker_style: str = ""
    start_number: int = 1
    is_continuous: bool = True
    level: int = 1


class ImageExtension(BaseModel):
    """图片类型扩展（4.2 图片类型扩展）。"""

    image_ref: str = ""
    caption_id: str = ""
    width: float = 0.0
    height: float = 0.0


class FormulaExtension(BaseModel):
    """公式类型扩展（4.2 公式类型扩展）。"""

    formula_type: Literal["inline", "block"] = "block"
    latex_code: str = ""
    confidence: float = 0.0


# ============================================================
# 全局节点（4.1 + 4.2）
# ============================================================


class GlobalNode(BaseModel):
    """全局节点。所有节点共享基础字段，按 node_type 携带分类型扩展。

    字段命名严格对应文档4.1表格。
    """

    # === 通用基础字段（4.1） ===
    schema_version: str = SchemaVersion.CURRENT
    node_id: str = Field(..., description="全局唯一ID")
    node_type: NodeType
    text: str = ""
    page_range: list[int] = Field(default_factory=list, description="[起始页, 结束页]")
    source_bbox: list[float] = Field(
        default_factory=list,
        description="PDF页面坐标 [x1,y1,x2,y2]",
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    need_review: bool = False
    review_reason: str = ""
    pdf_object_id: str = ""
    native_provenance: NativeProvenance = NativeProvenance.PURE_VISION
    native_trust: float = Field(0.0, ge=0.0, le=1.0)
    page_block_ids: list[str] = Field(default_factory=list)
    merge_history: list[str] = Field(default_factory=list)
    split_history: list[str] = Field(default_factory=list)
    content_hash: str = ""
    vlm_model_version: str = ""
    pdf_renderer_version: str = ""
    template_version: str = ""

    # === 标题特有 ===
    global_level: int | None = Field(None, ge=1, le=6)
    parent_id: str | None = None

    # === 分类型扩展字段（4.2，按 node_type 选择性填充） ===
    # 注意：字段名不能用 list/image/formula 等内建或常用类型名，
    # 否则后续 type hint 中的 list[str] 解析会从 class namespace 取值而非 builtin。
    table: TableExtension | None = None
    list_ext: ListExtension | None = None
    image: ImageExtension | None = None
    formula: FormulaExtension | None = None

    # === 审计与复核扩展字段（4.2） ===
    qa_result: QaResult | None = None
    review_resolution: ReviewResolution | None = None

    # === 子节点引用（仅 document_root / heading 持有） ===
    children_ids: list[str] = Field(default_factory=list)

    def recompute_content_hash(self) -> None:
        """基于 text 重算 content_hash。"""
        self.content_hash = content_hash(self.text)

    def record_merge(self, source_ids: list[str], strategy: str) -> None:
        """记录合并历史。"""
        self.merge_history.append(
            f"{strategy}: [{', '.join(source_ids)}] -> {self.node_id}"
        )

    def record_split(self, target_ids: list[str], strategy: str) -> None:
        """记录拆分历史。"""
        self.split_history.append(
            f"{strategy}: {self.node_id} -> [{', '.join(target_ids)}]"
        )

    def mark_review(self, reason: str) -> None:
        """标记待复核。"""
        self.need_review = True
        self.review_reason = reason


# ============================================================
# 全局文档树（3.3.4 输出）
# ============================================================


class DocumentTree(BaseModel):
    """全局文档树JSON（3.3.4唯一标准输出，供后续灌注使用）。

    root 节点的 node_type 固定为 document_root，其 children_ids 指向所有顶级标题/段落。
    其余节点的 children_ids 通过 node_id 索引到 nodes 列表中的对应节点。
    """

    schema_version: str = SchemaVersion.CURRENT
    document_id: str
    root: GlobalNode
    nodes: dict[str, GlobalNode] = Field(
        default_factory=dict,
        description="所有节点按 node_id 索引（root 也在内）",
    )
    # 元数据
    source_docx: str = ""
    source_pdf: str = ""
    pdf_renderer_version: str = ""
    vlm_model_version: str = ""
    template_version: str = ""
    created_at: datetime | None = None
    # 可追溯
    pdf_object_count: int = 0
    vlm_block_count: int = 0

    def get(self, node_id: str) -> GlobalNode | None:
        return self.nodes.get(node_id)

    def walk(self, start_id: str | None = None) -> list[GlobalNode]:
        """深度优先遍历。"""
        result: list[GlobalNode] = []
        if start_id is None:
            start_id = self.root.node_id
        stack = [start_id]
        while stack:
            cur = self.nodes.get(stack.pop())
            if cur is None:
                continue
            result.append(cur)
            stack.extend(reversed(cur.children_ids))
        return result

    def tree_hash(self) -> str:
        """基于完整结构的稳定哈希。用于幂等性校验（7.4幂等性）。"""
        canonical = {
            "document_id": self.document_id,
            "schema_version": self.schema_version,
            "nodes": {
                nid: node.model_dump(mode="json", exclude_none=True)
                for nid, node in sorted(self.nodes.items())
            },
        }
        return dict_hash(canonical)


__all__ = [
    # enums
    "BlockType",
    "NodeType",
    "PdfObjectKind",
    "NativeProvenance",
    "SchemaVersion",
    # models
    "BoundingBox",
    "Block",
    "PdfObjectRef",
    "QaResult",
    "ReviewResolution",
    "TableExtension",
    "ListExtension",
    "ImageExtension",
    "FormulaExtension",
    "GlobalNode",
    "DocumentTree",
]