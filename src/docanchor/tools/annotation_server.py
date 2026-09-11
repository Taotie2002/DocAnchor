"""轻量Web标注工具（阶段1第13-14天）。

目标：
- 用户加载DOCX+PDF后，可视化点击block进行标注
- 标注项：global_level / parent_id / sort_key / table_dims / cross_page_pair
- 标注结果存为JSON（与评测脚本格式一致）

实现策略：
- 后端：FastAPI（轻量、async、自动OpenAPI）
- 前端：单文件HTML+原生JS，无前端框架（避免重型依赖）
- 启动入口：`docanchor annotate <input.docx>` 启动HTTP服务

为了避免引入FastAPI依赖导致venv膨胀，本实现使用Python标准库http.server，
足够支撑单用户标注场景。
"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from docanchor.common.idgen import new_node_id
from docanchor.common.logger import get_logger

logger = get_logger("annotation_server")


# 默认端口
DEFAULT_PORT = 8765

# 静态资源目录（当前实现使用内嵌HTML，无需外部静态文件）
STATIC_DIR = Path(__file__).parent / "annotation_static"  # noqa: F841

# 工作空间：每个会话一个目录，保存标注结果
# 优先用环境变量 DOCANCHOR_WORKSPACE，否则用项目目录下的 .annotation_workspace
import os

_env_workspace = os.environ.get("DOCANCHOR_WORKSPACE")
if _env_workspace:
    WORKSPACE_ROOT = Path(_env_workspace)
else:
    # 默认放在工作目录下（避开HOME只读问题）
    WORKSPACE_ROOT = Path.cwd() / ".annotation_workspace"


# ============================================================
# HTML/JS/CSS 静态资源（内嵌避免外部依赖）
# ============================================================

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>DocAnchor 结构标注工具</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
header { background: #2c3e50; color: white; padding: 12px 20px; }
header h1 { margin: 0; font-size: 18px; }
.container { display: flex; height: calc(100vh - 50px); }
.left { flex: 2; padding: 12px; overflow: auto; background: white; border-right: 1px solid #ddd; }
.right { flex: 1; padding: 12px; overflow: auto; }
.toolbar { margin-bottom: 12px; }
.toolbar input { padding: 6px 10px; margin-right: 6px; border: 1px solid #ccc; border-radius: 4px; }
.toolbar button { padding: 6px 12px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
.toolbar button:hover { background: #2980b9; }
.block-list { list-style: none; padding: 0; }
.block-item { padding: 8px; margin-bottom: 4px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background: white; }
.block-item:hover { background: #ecf0f1; }
.block-item.selected { background: #3498db; color: white; }
.block-item .meta { font-size: 11px; opacity: 0.7; }
.annot-form { background: white; padding: 12px; border: 1px solid #ddd; border-radius: 4px; }
.annot-form label { display: block; margin-bottom: 8px; font-weight: bold; }
.annot-form input, .annot-form select { display: block; width: 100%; padding: 4px; margin-top: 2px; border: 1px solid #ccc; border-radius: 3px; box-sizing: border-box; }
.annot-form button { margin-top: 12px; padding: 8px 16px; background: #27ae60; color: white; border: none; border-radius: 4px; cursor: pointer; }
#status { padding: 8px; background: #ecf0f1; border-radius: 4px; margin-bottom: 8px; font-family: monospace; font-size: 12px; }
</style>
</head>
<body>
<header>
<h1>📐 DocAnchor 结构标注工具</h1>
</header>
<div class="toolbar">
<input id="docxPath" placeholder="输入DOCX路径（或留空使用当前会话）" size="60">
<button onclick="loadDoc()">加载样本</button>
<button onclick="loadBlocks()">刷新Block列表</button>
<button onclick="exportAnno()">导出标注</button>
<button onclick="saveAnno()">保存标注</button>
</div>
<div class="container">
<div class="left">
<div id="status">就绪</div>
<h3>Block 列表</h3>
<ul id="blockList" class="block-list"></ul>
</div>
<div class="right">
<h3>标注表单</h3>
<div id="annotForm" class="annot-form">
<p>选择左侧Block进行标注</p>
</div>
</div>
</div>

<script>
let sessionId = null;
let currentDocx = null;
let blocks = [];
let annotations = {};

async function loadDoc() {
    const path = document.getElementById('docxPath').value;
    const resp = await fetch('/api/load?path=' + encodeURIComponent(path));
    const data = await resp.json();
    if (data.error) {
        alert('加载失败: ' + data.error);
        return;
    }
    sessionId = data.session_id;
    currentDocx = data.docx_path;
    setStatus('会话已创建: ' + sessionId + '\\n样本: ' + data.docx_path + '\\n脏度: ' + data.dirt_level);
    await loadBlocks();
}

async function loadBlocks() {
    if (!sessionId) { alert('请先加载样本'); return; }
    const resp = await fetch('/api/blocks?session=' + sessionId);
    const data = await resp.json();
    blocks = data.blocks;
    annotations = data.annotations || {};
    renderBlocks();
}

function renderBlocks() {
    const ul = document.getElementById('blockList');
    ul.innerHTML = '';
    blocks.forEach((b, idx) => {
        const li = document.createElement('li');
        li.className = 'block-item';
        li.dataset.idx = idx;
        const ann = annotations[b.block_id];
        const tag = ann ? `[${ann.type || '?'}/L${ann.global_level || '-'}] ` : '';
        li.innerHTML = `${tag}<b>${escape(b.block_type)}</b>: ${escape(b.text.substring(0, 40))}
            <div class="meta">p${b.page} id=${b.block_id.substring(0,16)}</div>`;
        li.onclick = () => selectBlock(idx);
        ul.appendChild(li);
    });
}

function selectBlock(idx) {
    const b = blocks[idx];
    document.querySelectorAll('.block-item').forEach(el => el.classList.remove('selected'));
    document.querySelectorAll('.block-item')[idx].classList.add('selected');
    showForm(b);
}

function showForm(b) {
    const ann = annotations[b.block_id] || {};
    const form = document.getElementById('annotForm');
    form.innerHTML = `
        <label>Block ID<input value="${b.block_id}" readonly></label>
        <label>类型
            <select id="f_type">
                <option value="heading" ${ann.type==='heading'?'selected':''}>标题</option>
                <option value="paragraph" ${ann.type==='paragraph'?'selected':''}>段落</option>
                <option value="table" ${ann.type==='table'?'selected':''}>表格</option>
                <option value="list" ${ann.type==='list'?'selected':''}>列表</option>
                <option value="image" ${ann.type==='image'?'selected':''}>图片</option>
                <option value="caption" ${ann.type==='caption'?'selected':''}>图注</option>
                <option value="formula" ${ann.type==='formula'?'selected':''}>公式</option>
            </select>
        </label>
        <label>全局层级 (1-6, 标题必填)<input id="f_level" type="number" min="1" max="6" value="${ann.global_level || 1}"></label>
        <label>父标题 ID (留空=顶级)<input id="f_parent" value="${ann.parent_id || ''}"></label>
        <label>阅读顺序键 (整数, 越小越前)<input id="f_sort" type="number" value="${ann.sort_key || 0}"></label>
        <label>表格行列 (仅表格)
            <div style="display:flex; gap:8px">
                <input id="f_rows" type="number" min="0" value="${ann.table_dims?.rows || 0}" placeholder="行" style="width:50%">
                <input id="f_cols" type="number" min="0" value="${ann.table_dims?.cols || 0}" placeholder="列" style="width:50%">
            </div>
        </label>
        <button onclick="submitForm('${b.block_id}')">保存标注</button>
    `;
}

function submitForm(blockId) {
    const table_dims_rows = parseInt(document.getElementById('f_rows').value) || 0;
    const table_dims_cols = parseInt(document.getElementById('f_cols').value) || 0;
    annotations[blockId] = {
        type: document.getElementById('f_type').value,
        global_level: parseInt(document.getElementById('f_level').value) || null,
        parent_id: document.getElementById('f_parent').value || null,
        sort_key: parseInt(document.getElementById('f_sort').value) || 0,
        table_dims: (table_dims_rows > 0 || table_dims_cols > 0) ? {rows: table_dims_rows, cols: table_dims_cols} : null,
    };
    setStatus('已标注: ' + blockId);
    renderBlocks();
}

async function saveAnno() {
    if (!sessionId) { alert('请先加载样本'); return; }
    const resp = await fetch('/api/save?session=' + sessionId, {
        method: 'POST',
        body: JSON.stringify({annotations}),
        headers: {'Content-Type': 'application/json'},
    });
    const data = await resp.json();
    setStatus('保存到: ' + data.path);
}

async function exportAnno() {
    if (!sessionId) { alert('请先加载样本'); return; }
    window.location.href = '/api/export?session=' + sessionId;
}

function setStatus(msg) {
    document.getElementById('status').textContent = msg;
}

function escape(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
</script>
</body>
</html>
"""


# ============================================================
# 会话管理
# ============================================================


class AnnotationSession:
    """单个DOCX标注会话。

    启动时执行 Pipeline 但跳过模板灌注，仅保留 Block 列表供用户标注。
    """

    def __init__(self, docx_path: Path, dirt_level: str = "medium"):
        self.docx_path = docx_path.resolve()
        self.dirt_level = dirt_level
        self.session_id = new_node_id()
        self.blocks: list[dict] = []
        self.annotations: dict[str, dict] = {}
        self.workspace_dir = WORKSPACE_ROOT / self.session_id
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._load_blocks()
        self._save_meta()

    def _load_blocks(self) -> None:
        """执行Pipeline前半段，提取Block列表。"""
        from docanchor.modules.pdf_convert import convert_docx_to_pdf
        from docanchor.modules.vlm_adapter import parse_pdf_with_vlm
        from docanchor.modules.xml_cleaner import clean_docx

        cleaned = self.workspace_dir / f"{self.docx_path.stem}_cleaned.docx"
        clean_docx(self.docx_path, cleaned)
        pdf_dir = self.workspace_dir / "pdf"
        pdf_dir.mkdir(exist_ok=True)
        conv = convert_docx_to_pdf(cleaned, pdf_dir)
        pdf_path = Path(conv.output_path)
        pages = parse_pdf_with_vlm(pdf_path)
        for page_blocks in pages:
            for b in page_blocks:
                self.blocks.append(
                    {
                        "block_id": b.block_id,
                        "page": b.page_id,
                        "block_type": b.block_type.value,
                        "text": b.text,
                        "bbox": [b.bbox.x1, b.bbox.y1, b.bbox.x2, b.bbox.y2],
                    }
                )

    def _save_meta(self) -> None:
        meta = {
            "session_id": self.session_id,
            "docx_path": str(self.docx_path),
            "dirt_level": self.dirt_level,
            "block_count": len(self.blocks),
        }
        (self.workspace_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save(self, annotations: dict[str, dict]) -> Path:
        self.annotations = annotations
        path = self.workspace_dir / "annotations.json"
        path.write_text(
            json.dumps(annotations, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def export(self) -> Path:
        """导出符合评测格式的标注JSON。"""
        result = {
            "document_id": self.session_id,
            "docx_path": str(self.docx_path),
            "dirt_level": self.dirt_level,
            "annotations": [
                {
                    "id": ann.get("id") or bid,
                    "type": ann.get("type", ""),
                    "page": ann.get("page"),
                    "global_level": ann.get("global_level"),
                    "parent_id": ann.get("parent_id"),
                    "sort_key": ann.get("sort_key", 0),
                    "table_dims": ann.get("table_dims"),
                    "cross_page_pair": ann.get("cross_page_pair"),
                }
                for bid, ann in self.annotations.items()
            ],
            "review_metadata": {
                "reviewer": "pending",
                "review_time": None,
                "notes": "通过DocAnchor标注工具生成",
            },
        }
        path = self.workspace_dir / "annotations_eval_format.json"
        path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path


_SESSIONS: dict[str, AnnotationSession] = {}


# ============================================================
# HTTP处理器
# ============================================================


class AnnotationHandler(BaseHTTPRequestHandler):
    """标注工具HTTP处理器。"""

    def log_message(self, format, *args):  # noqa: A002
        # 抑制默认访问日志
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        ct = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_html(INDEX_HTML)
        elif path == "/api/load":
            self._api_load(qs)
        elif path == "/api/blocks":
            self._api_blocks(qs)
        elif path == "/api/export":
            self._api_export(qs)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/save":
            self._api_save(qs)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_load(self, qs: dict) -> None:
        docx_str = qs.get("path", [""])[0]
        dirt = qs.get("dirt", ["medium"])[0]
        if not docx_str:
            self._send_json(400, {"error": "缺少path参数"})
            return
        docx_path = Path(docx_str).expanduser().resolve()
        if not docx_path.exists():
            self._send_json(404, {"error": f"DOCX不存在: {docx_path}"})
            return
        try:
            session = AnnotationSession(docx_path, dirt_level=dirt)
            _SESSIONS[session.session_id] = session
            self._send_json(
                200,
                {
                    "session_id": session.session_id,
                    "docx_path": str(docx_path),
                    "dirt_level": dirt,
                    "block_count": len(session.blocks),
                },
            )
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": str(e)})

    def _api_blocks(self, qs: dict) -> None:
        sid = qs.get("session", [""])[0]
        session = _SESSIONS.get(sid)
        if not session:
            self._send_json(404, {"error": "session not found"})
            return
        self._send_json(
            200,
            {
                "blocks": session.blocks,
                "annotations": session.annotations,
            },
        )

    def _api_save(self, qs: dict) -> None:
        sid = qs.get("session", [""])[0]
        session = _SESSIONS.get(sid)
        if not session:
            self._send_json(404, {"error": "session not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body)
            annotations = data.get("annotations", {})
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"JSON解析失败: {e}"})
            return
        path = session.save(annotations)
        self._send_json(200, {"path": str(path)})

    def _api_export(self, qs: dict) -> None:
        sid = qs.get("session", [""])[0]
        session = _SESSIONS.get(sid)
        if not session:
            self._send_json(404, {"error": "session not found"})
            return
        path = session.export()
        self._send_file(path, "application/json")


# ============================================================
# 启动入口
# ============================================================


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """启动标注服务并返回server实例。"""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AnnotationHandler)
    logger.info(f"标注工具已启动: http://{host}:{port}")
    logger.info(f"工作空间: {WORKSPACE_ROOT}")
    return server


def serve_forever(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
    """阻塞运行标注服务。"""
    server = serve(port=port, host=host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
        server.shutdown()


__all__ = [
    "AnnotationSession",
    "serve",
    "serve_forever",
    "DEFAULT_PORT",
    "WORKSPACE_ROOT",
]