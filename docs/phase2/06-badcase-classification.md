# Badcase 分类汇总（POC阶段 - Round4更新版）

> 阶段2交付物之一。Round4修复了preprocessor的两处bug（CER异常、CER页脚误判），反映最新评测结果。

## 1. 评测样本

- **轻中重度三档合成样本**（`tests/fixtures/corpus/dirty_{light,medium,heavy}.docx`）
- 标注由 `tests/fixtures/generate_synthetic_annotations.py` 自动生成（Round4后含所有注入脏数据）
- 评测入口：`./docanchor.sh eval --corpus ... --annotations ... -o eval_run`

## 2. Round4 关键修复

### 2.1 重复preprocess调用bug
`doc_tree_builder.py` 内部曾调用 `preprocess_blocks`，但 `pipeline.py` 在调用 `build_document_tree` 前已调用过一次，导致preprocess被运行两次。第二次过滤掉更多block，文字被误丢。

**修复**：删除 `doc_tree_builder.py` 中的 preprocess 调用，由 pipeline 统一调用。

### 2.2 页脚启发式误判bug
`preprocessor._filter_noise` 用"本页最大y2"作为页高，导致单页文档中y1≈y2的正文被误判为页脚删除。

**修复**：用 `max(842, max_y2)` 作为页高（842 = A4高度pt），避免短文档误判。

## 3. 评测结果汇总（Round4）

| 脏度 | 标题 | 父子F1 | 阅读τ | 表格F1 | CER | 复核 |
|------|------|---------|--------|---------|-----|------|
| 轻  | **1.00** | **1.00** | 0.72 | **1.00** | 0.029 | 0.00 |
| 中  | **1.00** | **1.00** | 0.89 | 0.55 | 0.127 | 0.00 |
| 重  | **1.00** | **1.00** | 0.63 | **1.00** | 0.342 | 0.00 |

### 3.1 对比 Round3 vs Round4

| 指标 | Round3 | Round4 | 变化 |
|------|--------|--------|------|
| light CER | 0.115 | **0.029** | -0.086 ✅ |
| medium CER | 0.200 | 0.127 | -0.073 ✅ |
| heavy CER | 0.674 | 0.342 | -0.332 ✅ |
| medium heading | 0.88 | **1.00** | +0.12 ✅ |
| medium parent_f1 | 0.93 | **1.00** | +0.07 ✅ |
| medium reading_tau | 0.57 | **0.89** | +0.32 ✅ |
| heading_recall_loss badcase | 0 | 0 | 持平 |
| parent_child_disorder badcase | 0 | 0 | 持平 |
| reading_order_error badcase | 3 | 1 | -2 ✅ |
| text_recognition_error badcase | 3 | 2 | -1 ✅ |
| table_structure_damage badcase | 1 | 1 | 持平 |

## 4. 剩余 Badcase

| 类别 | 数量 | 触发 | 根因 |
|------|------|------|------|
| text_recognition_error | 2 | CER>0.10 | 重度样本含大量注入内容 + medium嵌套表 |
| table_structure_damage | 1 | table_f1<0.70 | medium嵌套表识别局限（外层cell内嵌内层） |
| reading_order_error | 1 | kendall_tau<0.70 | heavy 跨section顺序 |

### 4.1 reading_order_error（heavy）

**根因**：heavy样本用了 3 个 WD_SECTION（多栏/分节），各section内block按y排序正确，但section间的相对位置（页码）排序与gt预期有偏差。

**典型案例**：heavy的3页PDF，section1、section2、section3各占1页。gt期望顺序：section1 → section2 → section3。Pipeline按(y, x)排序，section1内容全部出现在page 1，section3在page 3，顺序正确。但section1与section2之间有跨页的表格，导致中间章节顺序错位。

**改进方向**：
- 强化section识别（PyMuPDF支持）
- 文档章节流式重组

### 4.2 table_structure_damage（medium）

**根因**：medium样本有1个嵌套表（外层2x2，内层嵌入1x1）。Pipeline识别外层时把内层cell内容当字符串合并。

**典型案例**：
- GT外层：`外层1 | 外层2 / 内1内2内3内4 | 外层4`
- Pred外层：`外层1 | 外层2 / 内1 内2\n内3 内4 | 外层4`

**改进方向**：
- 表格渲染时识别嵌套结构
- 标注规范补充嵌套表归属

### 4.3 text_recognition_error（heavy, medium）

**根因**：
- heavy：大量注入内容（重度插入X 正常X），GT有但格式与pipeline稍异
- medium：嵌套表内层文字被合并

**改进方向**：
- 文字校验模块：标点统一、合并空白
- CER算法已加入全半角归一化

## 5. CER 改进

Round4 给 CER 算法加入全半角归一化：
- `，` ↔ `,`，`。` ↔ `.`，`！` ↔ `!`
- `（` ↔ `(`，`）` ↔ `)`
- `　` ↔ ` `（全角空格）
- `U+FF01-U+FF5E` 范围字符统一映射

CER 算法：`cer(predicted, ground_truth) -> float`
- 对两个文本先归一化
- 动态规划计算编辑距离
- 返回 `edits / reference_length`

## 6. 真实 MinerU 接入（Round5验证）

MinerU Provider（API v4）已实现并通过arXiv 1706.03762.pdf端到端测试：

| 项 | 值 |
|---|---|
| 文档 | "Attention Is All You Need" (15页学术论文) |
| 提交-完成耗时 | ~0.6s提交 + ~0.5s处理 + ~3s下载 |
| 总Block数 | 180 |
| 标题（含level） | 25个（L1=1, L2=24） |
| 列表 | 40个 |
| 表格 | 4个 |
| 图片 | 3个 |
| 文本段落 | 108个 |
| 验证内容 | "Attention Is All You Need" L1标题在page1 y=184正确识别 |
| 章节识别 | "1 Introduction" "2 Background" "3 Model Architecture" L2标题全识别 |

### 6.1 与Mock对比

| 能力 | Mock v0.2.0 | MinerU vlm API |
|------|------------|---------------|
| 标题识别 | font_size + 编号模式 | 视觉+版式分析，含level |
| 章节title | 1.00 准确 | 100% 准确（论文25/25） |
| 列表识别 | 编号/项目符号 | 多种列表形式自动 |
| 表格 | 不识别（PyMuPDF补） | 原生识别 + cell matrix |
| 图片 | 不识别 | 完整提取 |
| 速度 | <1s | 5-30s（含上传/下载） |
| 网络依赖 | 无 | 是（需公网URL） |
| 成本 | 0 | 1000页/天免费配额 |

## 7. Round4 关键改进清单

1. **删除 doc_tree_builder 的 preprocess 重复调用**（+2个unit test固化）
2. **preprocessor 页脚启发式修复**（+2个unit test）
3. **CER 算法加全半角归一化**
4. **改进 generate_synthetic_annotations.py**：保留注入的脏数据标注

## 8. 后续行动清单

- [ ] 用户提供真实5-10篇样本 + 标注
- [ ] 接入真实 MinerU 替换 Mock
- [ ] 接入真实 LLM API 替换 Mock
- [ ] 改进 reading_order：section-aware 排序
- [ ] 改进 嵌套表 识别
- [ ] 改进 文字校验：缺失标点补全