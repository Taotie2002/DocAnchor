# DocAnchor 文锚结构化重建系统

针对多人拼凑、样式混乱、XML结构崩坏、深度嵌套的脏 DOCX 文档，实现全自动的文档结构解析、内容纠错、层级归一化、结构重建，最终输出格式统一、结构严谨、符合预置模板规范的干净 DOCX 文档。

## 核心设计取舍

- **锚定 PDF 同源坐标系**：放弃 Word 原始排版还原，以 PDF 作为统一坐标与内容基准
- **XML 前置清洗，DOCX 退居辅助角色**：原始 DOCX 仅负责转换前的 XML 清洗与文字校对权威源
- **视觉负责结构，PDF 文本负责文字**：VLM 识别结构与层级，PDF 原生文本层兜底文字
- **规则优先、LLM 兜底**：高频固定逻辑用规则，模糊场景调用小模型

## 当前阶段

**阶段1+阶段2（单篇闭环）**：技术预研 POC + 单篇全功能闭环，不含批量处理 / 人工复核后台。

## 环境要求

- Python 3.13
- LibreOffice 7.x（PDF 转换主链路）
- 见 `.venv/`（已预装：python-docx、lxml、PyMuPDF、openai、jsonschema、pydantic）

## 环境变量（阶段2接入真实LLM时配置）

```bash
DOCANCHOR_LLM_BASE_URL=     # 内网OpenAI兼容API地址
DOCANCHOR_LLM_API_KEY=      # 鉴权Key
DOCANCHOR_LLM_MODEL=        # 模型名，默认 qwen2.5-7b-instruct
```

复制 `.env.example` 为 `.env` 后填入。

## 仓库结构

```
src/docanchor/
├── cli.py                  # CLI入口
├── pipeline.py             # 端到端Pipeline编排
├── config.py               # 全局配置
├── common/                 # 公共基础
│   ├── schema.py           # Block/Node数据模型
│   ├── logger.py
│   ├── idgen.py
│   ├── hash.py
│   └── errors.py
├── modules/
│   ├── xml_cleaner/        # XML级元数据清洗
│   ├── pdf_convert/        # DOCX → PDF
│   ├── pdf_extract/        # PyMuPDF对象提取
│   ├── vlm_adapter/        # VLM解析+Adapter归一化
│   ├── global_aggregate/   # 全局聚合
│   ├── text_verify/        # 文字校验与双路核对
│   └── template_render/    # 模板灌注与文档重建
└── llm/                    # 小模型客户端与任务契约
```

## 运行

```bash
# CLI入口（待阶段1第13天实现）
.venv/bin/python -m docanchor.cli run input.docx -o output_dir/
```

## 进度

见项目 TODO 跟踪。