"""端到端Pipeline编排（文档第2章）。

固定顺序：
    DOCX源文件
      → XML级元数据清洗（3.1.3）
      → LibreOffice headless转PDF（3.1.4）
      → 双路并行：
          ├─ VLM分页解析（3.2）
          └─ PyMuPDF对象提取（3.1.5）
      → 全局聚合（3.3）：结构修复+层级归一
      → 文字双路校验（3.4）  [阶段2实现]
      → 模板灌注与文档重建（3.5）  [阶段2实现]
      → 标准化干净DOCX输出

阶段1第13天实现：核心链路打通到全局文档树输出。
阶段2补全文字校验与模板灌注。
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docanchor.common.idgen import new_node_id
from docanchor.common.logger import get_logger
from docanchor.common.schema import DocumentTree
from docanchor.config import get_settings
from docanchor.modules.global_aggregate.doc_tree_builder import build_document_tree
from docanchor.modules.global_aggregate.preprocessor import preprocess_blocks
from docanchor.modules.pdf_convert import convert_docx_to_pdf
from docanchor.modules.pdf_extract import extract_pdf_objects, get_object_summary
from docanchor.modules.template_render.builder import render_document_tree
from docanchor.modules.text_verify.aligner import align_vlm_with_pdf
from docanchor.modules.text_verify.critical_fields import verify_critical_fields
from docanchor.modules.vlm_adapter import parse_pdf_with_vlm
from docanchor.modules.xml_cleaner import clean_docx

logger = get_logger("pipeline")


@dataclass
class PipelineResult:
    """Pipeline运行结果汇总。"""

    document_id: str = ""
    output_docx: Path | None = None
    cleaned_docx: Path | None = None
    source_pdf: Path | None = None
    vlm_block_count: int = 0
    pdf_object_count: int = 0
    global_node_count: int = 0
    llm_call_count: int = 0
    review_queue_count: int = 0
    document_tree: DocumentTree | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "cleaned_docx": str(self.cleaned_docx) if self.cleaned_docx else None,
            "source_pdf": str(self.source_pdf) if self.source_pdf else None,
            "vlm_block_count": self.vlm_block_count,
            "pdf_object_count": self.pdf_object_count,
            "global_node_count": self.global_node_count,
            "llm_call_count": self.llm_call_count,
            "review_queue_count": self.review_queue_count,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "errors": self.errors,
        }


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    config: dict[str, Any] | None = None,
) -> PipelineResult:
    """端到端处理一篇DOCX。

    Args:
        input_path: 原始 DOCX 文件路径。
        output_dir: 输出目录。
        config: 可选配置覆盖（当前未使用，保留扩展点）。

    Returns:
        PipelineResult：包含产物路径与统计指标。

    Raises:
        NotImplementedError: 阶段1第13天不应再抛出此异常。
    """
    start = time.time()
    result = PipelineResult()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成document_id
    result.document_id = new_node_id()

    try:
        # === Step 1: XML级元数据清洗 ===
        cleaned_docx = output_dir / f"{input_path.stem}_cleaned.docx"
        cleaning_report = clean_docx(input_path, cleaned_docx)
        result.cleaned_docx = cleaned_docx
        logger.info(
            f"[Step 1] XML清洗: {cleaning_report.total_changes} 处变更, "
            f"耗时 {cleaning_report.elapsed_seconds:.2f}s"
        )

        # === Step 2: DOCX → PDF 转换 ===
        pdf_dir = output_dir / "pdf"
        pdf_dir.mkdir(exist_ok=True)
        conv_report = convert_docx_to_pdf(cleaned_docx, pdf_dir)
        result.source_pdf = Path(conv_report.output_path)
        logger.info(
            f"[Step 2] PDF转换: engine={conv_report.engine}, "
            f"pages={conv_report.page_count}, "
            f"耗时 {conv_report.elapsed_seconds:.2f}s"
        )

        # === Step 3: 双路并行 ===
        # VLM 分页解析
        vlm_pages = parse_pdf_with_vlm(result.source_pdf)
        all_blocks = [b for page in vlm_pages for b in page]
        result.vlm_block_count = len(all_blocks)
        logger.info(f"[Step 3a] VLM解析: {result.vlm_block_count} 个Block")

        # PyMuPDF 对象提取
        pdf_objects = extract_pdf_objects(
            result.source_pdf,
            image_output_dir=output_dir / "images",
        )
        result.pdf_object_count = len(pdf_objects)
        logger.info(
            f"[Step 3b] PDF对象提取: {result.pdf_object_count} 个对象, "
            f"分类: {get_object_summary(pdf_objects)}"
        )

        # === Step 4: 预处理（排序/过滤/归一） ===
        preprocessed = preprocess_blocks(all_blocks)
        logger.info(f"[Step 4] 预处理: {len(all_blocks)} -> {len(preprocessed)}")

        # === Step 5: 构建全局文档树 ===
        tree = build_document_tree(
            preprocessed,
            document_id=result.document_id,
            source_pdf=str(result.source_pdf),
            pdf_objects=pdf_objects,
        )
        result.document_tree = tree
        result.global_node_count = len(tree.nodes)
        result.review_queue_count = sum(
            1 for n in tree.nodes.values() if n.need_review
        )
        logger.info(
            f"[Step 5] 文档树: {result.global_node_count} 个节点, "
            f"复核队列 {result.review_queue_count}"
        )

        # === Step 6: 序列化文档树 ===
        tree_path = output_dir / f"{input_path.stem}_tree.json"
        with tree_path.open("w", encoding="utf-8") as f:
            json.dump(
                tree.model_dump(mode="json", exclude_none=True),
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"[Step 6] 文档树已序列化: {tree_path}")

        # === Step 7: 文字双路校验 ===
        alignment = align_vlm_with_pdf(preprocessed, pdf_objects)
        # 收集VLM与PDF文本对比，找关键字段冲突
        vlm_text = " ".join(b.text for b in preprocessed if b.text)
        pdf_text = " ".join(o.text for o in pdf_objects if o.text)
        critical_conflicts = verify_critical_fields(vlm_text, pdf_text)
        result.metrics["text_alignment"] = {
            "total": len(alignment),
            "strong": sum(1 for a in alignment if a.level == "strong"),
            "weak": sum(1 for a in alignment if a.level == "weak"),
            "none": sum(1 for a in alignment if a.level == "none"),
        }
        result.metrics["critical_field_conflicts"] = len(critical_conflicts)
        logger.info(
            f"[Step 7] 文字校验: alignment={len(alignment)} "
            f"(strong={result.metrics['text_alignment']['strong']}, "
            f"weak={result.metrics['text_alignment']['weak']}), "
            f"关键字段冲突={len(critical_conflicts)}"
        )

        # === Step 8: 模板灌注与文档重建 ===
        output_docx = output_dir / f"{input_path.stem}_clean.docx"
        try:
            render_document_tree(
                tree,
                template_path=None,
                output_path=output_docx,
            )
            result.output_docx = output_docx
            logger.info(f"[Step 8] 干净DOCX已输出: {output_docx}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"模板灌注失败: {e}")
            result.errors.append(f"template_render: {e}")

    except Exception as e:  # noqa: BLE001
        logger.exception(f"Pipeline失败: {e}")
        result.errors.append(f"{type(e).__name__}: {e}")
        raise

    finally:
        result.elapsed_seconds = time.time() - start
        logger.info(f"Pipeline耗时: {result.elapsed_seconds:.2f}s")

    return result


__all__ = ["PipelineResult", "run_pipeline"]