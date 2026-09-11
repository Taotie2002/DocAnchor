"""CLI 入口。

使用方式：
    docanchor run <input.docx> -o <output_dir>
    docanchor config  # 打印当前配置
    docanchor version  # 打印版本
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docanchor import __version__, __stage__
from docanchor.common.logger import get_logger, setup_logging
from docanchor.config import get_settings

logger = get_logger("cli")


def cmd_run(args: argparse.Namespace) -> int:
    """处理单篇文档。"""
    from docanchor.pipeline import run_pipeline

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve() if args.output else Path("./output").resolve()

    if not input_path.exists():
        logger.error(f"输入文件不存在: {input_path}")
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"开始处理: {input_path} -> {output_dir}")

    try:
        result = run_pipeline(input_path=input_path, output_dir=output_dir)
        logger.info(f"处理完成: {result}")
        return 0
    except NotImplementedError as e:
        logger.warning(f"链路尚未实现: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        logger.exception(f"处理失败: {e}")
        return 1


def cmd_annotate(args: argparse.Namespace) -> int:
    """启动标注工具HTTP服务。"""
    from docanchor.tools.annotation_server import DEFAULT_PORT, serve_forever

    port = args.port or DEFAULT_PORT
    logger.info(f"启动标注工具: http://127.0.0.1:{port}")
    logger.info("按 Ctrl+C 停止服务")
    try:
        serve_forever(port=port)
        return 0
    except KeyboardInterrupt:
        return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """批量评测语料库。"""
    from docanchor.eval.cli import (
        generate_badcase_classification,
        run_corpus_evaluation,
    )
    from docanchor.eval.report import build_report

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    corpus_dir = Path(args.corpus).resolve()
    ann_dir = Path(args.annotations).resolve()
    if not corpus_dir.exists():
        logger.error(f"语料目录不存在: {corpus_dir}")
        return 2
    if not ann_dir.exists():
        logger.error(f"标注目录不存在: {ann_dir}")
        return 2

    results = run_corpus_evaluation(corpus_dir, ann_dir, output_dir)
    if not results:
        logger.error("无评测结果")
        return 1

    report = build_report(results, output_path=output_dir / "report.json")
    badcase = generate_badcase_classification(
        results, output_path=output_dir / "badcase.json"
    )
    logger.info(f"评测完成: {len(results)} 篇文档, 报告 {output_dir / 'report.json'}, badcase {output_dir / 'badcase.json'}")
    return 0


def cmd_config(_args: argparse.Namespace) -> int:
    """打印当前配置（脱敏）。"""
    import json

    settings = get_settings()
    d = settings.model_dump()
    # 脱敏 api_key
    if d.get("llm_api_key"):
        d["llm_api_key"] = "***" + d["llm_api_key"][-4:] if len(d["llm_api_key"]) > 4 else "***"
    print(json.dumps(d, indent=2, ensure_ascii=False))
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"docanchor {__version__} ({__stage__})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docanchor",
        description="DocAnchor 文锚结构化重建系统",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    p_run = sub.add_parser("run", help="处理单篇DOCX")
    p_run.add_argument("input", help="输入DOCX文件路径")
    p_run.add_argument("-o", "--output", help="输出目录", default="./output")
    p_run.set_defaults(func=cmd_run)

    p_anno = sub.add_parser("annotate", help="启动结构标注工具（HTTP）")
    p_anno.add_argument("-p", "--port", type=int, default=None, help="端口，默认8765")
    p_anno.set_defaults(func=cmd_annotate)

    p_eval = sub.add_parser("eval", help="批量评测语料库")
    p_eval.add_argument("--corpus", default="tests/fixtures/corpus", help="语料目录")
    p_eval.add_argument("--annotations", default="tests/fixtures/annotations", help="标注目录")
    p_eval.add_argument("-o", "--output", default="eval_run", help="输出目录")
    p_eval.set_defaults(func=cmd_eval)

    p_cfg = sub.add_parser("config", help="打印当前配置")
    p_cfg.set_defaults(func=cmd_config)

    p_ver = sub.add_parser("version", help="打印版本")
    p_ver.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())