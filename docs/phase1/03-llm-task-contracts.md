# 小模型任务契约

> 阶段1交付物之一。本文定义三大LLM任务的输入输出Schema、Prompt模板、温度参数与防幻觉约束。

## 1. 通用设计规范（文档3.6）

所有小模型任务统一遵循：

1. **选型与部署**：7B/14B参数开源模型本地部署，或商用内网合规API
2. **输入输出强约束**：固定Prompt模板、固定JSON Schema；Schema校验失败自动重试2次
3. **温度参数控制**：分类/判断/层级类任务温度=0；语义分析类≤0.3
4. **防幻觉机制**：禁止改写原文，仅做判断/分类/异常标注；所有输出带置信度
5. **一致性校验**：关键任务（标题层级、表格合并）支持多轮投票校验
6. **单篇预算**：默认20次LLM调用/文档

## 2. 任务一：跨页表格二元判断

**适用场景**（文档3.3.2）：跨页表格规则初筛通过后，调用小模型做最终二元判断。

### 2.1 输入契约

```python
{
    "header_a": str,         # 表格A的表头文本（按列拼接）
    "col_count_a": int,
    "first_row_a": list[str], # 首行内容
    "page_a": int,
    "header_b": str,
    "col_count_b": int,
    "first_row_b": list[str],
    "page_b": int,
}
```

### 2.2 输出契约（JSON）

```json
{"is_same_table": <bool>, "confidence": <float 0-1>}
```

### 2.3 Schema

```python
CROSS_PAGE_TABLE_SCHEMA = {
    "type": "object",
    "required": ["is_same_table", "confidence"],
    "properties": {
        "is_same_table": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}
```

### 2.4 Prompt片段

- **System**：明确说明任务边界（仅判断、不修改文本）
- **User**：表格A/表格B的结构化展示

### 2.5 阈值

- `confidence < 0.8` → 标记待复核，不强制合并

### 2.6 防幻觉

- 任务提示词明确"禁止修改、猜测或补充任何文字内容"
- `additionalProperties: False` 防止模型添加多余字段

## 3. 任务二：标题层级归一化

**适用场景**（文档3.3.3）：滑动窗口增量校正，调用小模型输出全局层级与父子关系。

### 3.1 输入契约（窗口大小10，重叠2）

```python
[{
    "id": str,
    "text": str,
    "local_level": int | null,    # VLM局部层级
    "page_id": int,
    "numbering": str | null,        # 文档自带编号（如"第1章"/"1.1"）
}, ...]
```

### 3.2 输出契约（JSON数组）

```json
[{
    "id": "<标题id>",
    "global_level": <1-6整数>,
    "parent_id": "<父标题id或null>",
    "confidence": <float 0-1>
}, ...]
```

### 3.3 Schema

```python
HEADING_LEVEL_ITEM_SCHEMA = {
    "type": "object",
    "required": ["id", "global_level", "parent_id", "confidence"],
    "properties": {
        "id": {"type": "string"},
        "global_level": {"type": "integer", "minimum": 1, "maximum": 6},
        "parent_id": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}
```

### 3.4 强约束

- `global_level` 必须为1-6整数（Pydantic/Schema双重校验）
- 禁止改写标题文本
- `confidence < 0.5` 标记无法判定
- 父子关系由代码端维护栈结构，LLM仅提供id引用

### 3.5 优先级（文档3.3.3）

文档自带章节编号 > 小模型判断 > VLM局部视觉层级

LLM判断窗口：10个标题，前进2个重叠，每5窗口触发全量回溯校验。

## 4. 任务三：语义校验

**适用场景**（文档3.4.3.2）：小模型分段通读全文，检测不通顺、歧义、语病。

### 4.1 输入契约

```python
{
    "text": str,           # 待校验文本
    "context": dict | None # 可选上下文（章节、相邻段落）
}
```

### 4.2 输出契约（JSON数组）

```json
[{
    "location": "<异常位置描述>",
    "issue_type": "<不通顺|歧义|语病|错别字|其他>",
    "description": "<问题描述>",
    "confidence": <float 0-1>
}]
```

### 4.3 Schema

```python
SEMANTIC_CHECK_ISSUE_SCHEMA = {
    "type": "object",
    "required": ["location", "issue_type", "description", "confidence"],
    "properties": {
        "location": {"type": "string"},
        "issue_type": {"enum": ["不通顺", "歧义", "语病", "错别字", "其他"]},
        "description": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "additionalProperties": False,
}
```

### 4.4 温度参数

- 语义分析类任务：温度≤0.3（`llm_temperature_semantic`配置项）
- 无明显异常时返回 `[]`

### 4.5 防幻觉

- 仅发现异常，不修改文本
- `description` 描述问题但不重写原文
- 校验底线：禁止无原生依据自动改写（所有修正必须可溯源PDF文本层或DOCX原文）

## 5. 实现入口

| 任务 | 函数 | 文件 |
|------|------|------|
| 跨页表格 | `judge_cross_page_table` | `src/docanchor/llm/tasks/cross_page_table.py` |
| 标题层级 | `normalize_heading_levels` | `src/docanchor/llm/tasks/heading_level.py` |
| 语义校验 | `semantic_check_text` | `src/docanchor/llm/tasks/semantic_check.py` |

## 6. 单元测试覆盖

- `tests/unit/test_llm_tasks.py`：13个测试覆盖Schema校验、重试、成本计数、任务契约输入输出

## 7. 接入真实LLM步骤

1. 在 `.env` 中配置：
   ```
   DOCANCHOR_LLM_BASE_URL=http://your-internal-api/v1
   DOCANCHOR_LLM_API_KEY=sk-xxx
   DOCANCHOR_LLM_MODEL=qwen2.5-7b-instruct
   ```
2. 启动后 `get_default_client()` 自动选择 OpenAICompatProvider
4. 首次接入建议：
   - 用1篇已知样本做smoke test
   - 检查Schema校验通过率
   - 检查各任务confidence分布
3. 若模型输出不符合Schema：在任务文件中调整Prompt或温度