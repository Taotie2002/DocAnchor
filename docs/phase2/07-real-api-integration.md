# 真实 API 接入指南

> 阶段2交付物之一。本文记录 MinerU（VLM）和 NVIDIA（LLM）真实API接入的配置、测试与局限。

## 1. MinerU API Provider

### 1.1 API概览

MinerU 文档解析API（[官方文档](https://mineru.net/apiManage/docs)）：

| 项 | 值 |
|---|---|
| Base URL | `https://mineru.net/api/v4/extract/task` |
| 鉴权 | Bearer Token（从 https://mineru.net/apiManage/token 获取） |
| 模型 | `vlm`（推荐）、`pipeline`、`MinerU-HTML` |
| 输入 | 公网URL的PDF/图片/Office文档 |
| 输出 | ZIP（含Markdown + layout JSON + 图片） |
| 配额 | 免费1000页/天（高优先级），超出降级 |
| 限制 | 200MB / 200页 / 文件；批50个 |

### 1.2 接入方式

```bash
# 1. 设置环境变量（.env文件中已配置）
export DOCANCHOR_MINERU_BASE_URL=https://mineru.net/api/v4/extract/task
export DOCANCHOR_MINERU_TOKEN=<your-token>

# 2. 切换VLM Provider为MinerU
export DOCANCHOR_VLM_PROVIDER=mineru

# 3. 运行Pipeline（PDF需先上传到公网）
./docanchor.sh run /path/to/docx -o ./output
```

### 1.3 异步任务流

```
1. 提交任务 (POST /extract/task 或 /extract/task/batch)
   → 返回 task_id
2. 轮询结果 (GET /extract/task/{id} 或 /extract-results/batch/{id})
   → state: pending/running/converting/done/failed
3. 下载ZIP (full_zip_url)
4. 解压解析为标准Block
```

### 1.4 输出格式

MinerU v2格式（content_list_v2.json）：
```json
[
  [  // page 0
    {"type": "title", "content": {"title_content": [{"type": "text", "content": "..."}], "level": 1}, "bbox": [x1,y1,x2,y2]},
    {"type": "paragraph", "content": {"paragraph_content": [...]}, "bbox": [...]},
    {"type": "table", "content": {"table_content": [...]}, "bbox": [...]},
    ...
  ],
  ...
]
```

### 1.5 测试结果（arXiv 1706.03762 "Attention Is All You Need"）

- 任务提交：~0.6s
- 任务处理：~0.5s
- ZIP下载：~3s
- **15页 / 180个Block**
- 25个标题（带level 1/2/3）、40个列表、4个表格、3个图片
- 全部正确解析

### 1.6 已知限制

- **本地PDF需先上传到公网URL**（如OSS）才能提交。标准API不接受直接上传。
  - 替代方案：使用MinerU开源版 `pip install magic-pdf` 在本地跑
- 文件大小限制200MB / 200页
- 每日配额1000页（免费），超出后任务降级为低优先级

## 2. NVIDIA LLM Provider

### 2.1 API概览

NVIDIA Integrated API（OpenAI兼容）：

| 项 | 值 |
|---|---|
| Base URL | `https://integrate.api.nvidia.com/v1` |
| 鉴权 | Bearer Token（nvapi-...） |
| 推荐模型 | `mistralai/mistral-nemotron`（通用） |
| 输入 | OpenAI Chat Completions格式 |
| 输出 | JSON或文本 |

### 2.2 接入方式

```bash
# .env 文件
DOCANCHOR_LLM_BASE_URL=https://integrate.api.nvidia.com/v1
DOCANCHOR_LLM_API_KEY=nvapi-...
DOCANCHOR_LLM_MODEL=mistralai/mistral-nemotron
DOCANCHOR_LLM_TIMEOUT=120  # 秒
```

### 2.3 已验证可用模型

| 模型 | 状态 | 备注 |
|------|------|------|
| `mistralai/mistral-nemotron` | ✅ 可用 | 1-2s响应 |
| `deepseek-ai/deepseek-v4-flash-0731` | ⚠️ 卡死 | 首次调用超时 |
| `meta/llama-3.1-nemotron-70b-instruct` | ❌ 404 | 账户未授权 |
| `meta/llama-3.1-8b-instruct` | ❌ 410 | 模型EOL |
| `google/gemma-3-4b-it` | ❌ 404 | 账户未授权 |

### 2.4 输出格式

LLM返回可能含markdown fence：

```
```json
{"is_same_table": true, "confidence": 0.95}
```
```

LLMClient已自动剥离fence，提取内部JSON。

### 2.5 已知限制

- **延迟波动大**：首次调用1-2s，后续10-60s不等，可能因NVIDIA服务端冷启动/限流
- **模型覆盖**：需先确认账户是否有权限调用特定模型
- **Cold start**：LLMProvider首次调用timeout=120s，建议设置为120s+而非默认60s

## 3. 接入验证步骤

### 3.1 验证MinerU

```bash
# 命令行
PYTHONPATH=src .venv/bin/python -c "
import sys
sys.path.insert(0, 'src')
from docanchor.modules.vlm_adapter.providers.mineru import MinerUProvider
provider = MinerUProvider(token='<token>', model='vlm')
pages = provider.parse_url('https://arxiv.org/pdf/1706.03762.pdf')
print(f'Pages: {len(pages)}, Blocks: {sum(len(p) for p in pages)}')
"
```

期望：`Pages: 15, Blocks: 180`

### 3.2 验证NVIDIA LLM

```bash
PYTHONPATH=src .venv/bin/python -c "
import sys
sys.path.insert(0, 'src')
from docanchor.llm.client import LLMClient
from docanchor.llm.providers.openai_compat import OpenAICompatProvider
provider = OpenAICompatProvider(
    base_url='https://integrate.api.nvidia.com/v1',
    api_key='<key>',
    model='mistralai/mistral-nemotron',
)
client = LLMClient(provider=provider)
result = client.call(
    task='test',
    system_prompt='返回JSON：{\"x\": <int>}',
    user_prompt='x=42',
    schema={'type':'object','properties':{'x':{'type':'integer'}}, 'required':['x']},
    max_tokens=20,
    temperature=0.0,
)
print(f'data: {result.data}')
"
```

期望：`data: {'x': 42}`

## 4. 与Mock对比

| 项 | Mock VLM | MinerU vlm |
|---|---|---|
| 输入 | 任意PDF | 公网URL |
| 速度 | <1s/页 | 5-30s/页 |
| 标题识别 | 仅font_size判定 | 视觉+版式，含level |
| 列表识别 | 编号/项目符号 | 多种列表形式 |
| 表格识别 | 不识别 | 完整cell_matrix |
| 成本 | 0 | 配额消耗 |
| 网络依赖 | 否 | 是 |

## 5. 端到端Pipeline（真实API）

```
DOCX (本地)
  → XML清洗
  → LibreOffice转PDF
  → [新] 上传PDF到公网（用户实现）→ 公网URL
  → MinerU API解析 → Block Schema
  → PyMuPDF对象提取（与MinerU互补）
  → 全局聚合
  → 文字校验（含NVIDIA LLM小模型判断）
  → 模板灌注
  → 干净DOCX
```

## 6. 后续行动

- [ ] 用户上传本地PDF到公网（可实现 `parse_local` 方法自动用OSS API上传）
- [ ] 评测模块支持真实API开关
- [ ] 真实API成本与性能基准
- [ ] 失败重试与降级（API超时→Mock）