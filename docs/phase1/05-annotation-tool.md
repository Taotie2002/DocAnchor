# 结构标注工具使用指南

> 阶段1第13-14天交付物：用于人工标注样本结构的轻量Web工具。

## 1. 启动

```bash
# 默认端口8765
./docanchor.sh annotate

# 自定义端口
./docanchor.sh annotate -p 9000
```

启动后浏览器访问 `http://127.0.0.1:8765`。

## 2. 工作空间

标注过程中产生的所有文件保存于：

- 默认：`./.annotation_workspace/<session_id>/`
- 可通过环境变量 `DOCANCHOR_WORKSPACE` 自定义

每个会话包含：
- `meta.json`：会话元数据（docx_path, dirt_level, block_count）
- `<stem>_cleaned.docx`：清洗后DOCX
- `pdf/<stem>_cleaned.pdf`：转换后PDF
- `annotations.json`：用户保存的标注
- `annotations_eval_format.json`：评测格式导出

## 3. 使用流程

### 3.1 加载样本

1. 在顶部工具栏输入DOCX路径（或留空使用当前会话）
2. 选择脏度（light/medium/heavy）—— 默认为medium
3. 点击「加载样本」按钮
4. 系统执行Pipeline前半段（XML清洗 + PDF转换 + VLM解析），耗时约2-3秒

### 3.2 标注Block

1. 左侧Block列表显示所有从VLM提取的Block（含page_id, block_type, text预览）
2. 点击任一Block，右侧显示标注表单
3. 填写标注项：
   - **类型**：标题/段落/表格/列表/图片/图注/公式
   - **全局层级**：1-6，仅标题必填
   - **父标题ID**：留空表示顶级标题，否则填父节点的block_id
   - **阅读顺序键**：整数，越小越靠前
   - **表格行列**：仅表格填写
4. 点击「保存标注」按钮

### 3.3 保存与导出

- 「保存标注」：将当前所有标注写入 `annotations.json`
- 「导出标注」：导出符合评测脚本格式的 `annotations_eval_format.json`

## 4. 标注JSON格式

### 4.1 工作格式（annotations.json）

```json
{
  "<block_id>": {
    "type": "heading|paragraph|table|...",
    "global_level": 1,
    "parent_id": "<parent_block_id_or_null>",
    "sort_key": 0,
    "table_dims": {"rows": 3, "cols": 3},
    "cross_page_pair": "<paired_block_id_or_null>"
  }
}
```

### 4.2 评测格式（annotations_eval_format.json）

```json
{
  "document_id": "<session_id>",
  "docx_path": "<原docx路径>",
  "dirt_level": "light|medium|heavy",
  "annotations": [
    {
      "id": "<block_id>",
      "type": "...",
      "page": 1,
      "global_level": 1,
      "parent_id": null,
      "sort_key": 0,
      "table_dims": null,
      "cross_page_pair": null
    }
  ],
  "review_metadata": {
    "reviewer": "pending",
    "review_time": null,
    "notes": "通过DocAnchor标注工具生成"
  }
}
```

## 5. 实施说明

### 5.1 技术选型

- 后端：Python标准库 `http.server` + `ThreadingHTTPServer`（避免FastAPI重型依赖）
- 前端：单文件HTML + 原生JavaScript（无React/Vue）
- 通信：JSON over HTTP

### 5.2 Pipeline复用

标注工具加载DOCX时，复用 `docanchor.modules.*` 的Pipeline前半段（XML清洗 + PDF转换 + VLM解析），不执行后续聚合与渲染。

### 5.3 已知限制

- 不支持多人协作（单用户本地工具）
- 不支持断点续标（每次加载重新执行Pipeline提取Block）
- 不显示PDF预览（仅Block列表）
- 仅适合5-10篇样本的最小标注场景

## 6. 后续优化方向

- [ ] 集成PDF.js实现PDF预览
- [ ] 支持上传标注基准与多用户共享
- [ ] 增加标注进度可视化
- [ ] 导出CSV便于在Excel中编辑