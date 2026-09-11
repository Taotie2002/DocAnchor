# PDF转换与对象提取验收方案

> 阶段1交付物之一。本文档定义了DOCX→PDF转换保真度的验收口径、测试方法与判定标准，对应需求文档3.1.6"Go/No-Go判定项"。

## 1. 验收口径

### 1.1 三项核心指标（文档3.1.6）

| 指标 | 计算口径 | 阈值（中度脏文档） |
|------|---------|-------------------|
| 内容召回率 | PDF可提取字符数 / DOCX可提取字符数 | 正文/表格文本≥99%、图片≥98% |
| 分页偏差分布 | 段落估算页号 vs PDF实际页号偏差 ≤1 的占比 | 中度脏文档≥90% |
| 表格结构保真度 | PyMuPDF识别行列数 / DOCX实际行列数 | 常规表格行列≥95%、嵌套畸变率≤5% |

### 1.2 不同脏度等级阈值（文档8.3）

| 指标 | 轻度 | 中度 | 重度 |
|------|------|------|------|
| text_recall | ≥99% | ≥99% | ≥99% |
| image_recall | ≥98% | ≥98% | ≥98% |
| table_row_accuracy | ≥97% | ≥95% | ≥88% |
| deviation_within_one_line_ratio | ≥95% | ≥90% | ≥80% |

## 2. 测试方法

### 2.1 语料构成

- POC阶段：用户提供5-10篇DOCX样本，按脏度分配（建议3轻+4中+2重）
- 待用户样本到位后执行实际Go/No-Go

### 2.2 当前可用的合成验证

- `tests/fixtures/build_synthetic_dirty_docx.py` 构造一份含修订/隐藏文字/标题/表格/列表的合成脏DOCX
- `tests/unit/test_pdf_convert.py::measure_fidelity` 执行保真度测量
- `tests/unit/test_pdf_convert.py::go_no_go_check` 判定Go/No-Go

### 2.3 验收流程

```
提供样本 → XML清洗 → LibreOffice转PDF → measure_fidelity → go_no_go_check
   ↓
全部pass → 进入阶段1第6天 PyMuPDF对象提取
任一fail → 启用降级链路 OnlyOffice / Word COM 重新测量
仍fail → 反馈风险，重新评估方案基线
```

## 3. 当前合成样本验收结果（仅供开发联调）

> **重要**：以下结果基于合成单样本，不代表真实样本表现。用户样本到位后需重新测量。

| 指标 | 值 | 阈值（中度） | 通过 |
|------|-----|-------------|------|
| text_recall | 1.0000 | ≥0.99 | ✅ |
| image_recall | 1.0000 | ≥0.98 | ✅ |
| table_row_accuracy | 1.0000 | ≥0.95 | ✅ |
| deviation_within_one_line_ratio | 0.7857 | ≥0.90 | ⚠️ |

### 关于deviation指标

deviation指标依赖"DOCX段落序号估算页号"的近似算法。在合成单文档上，由于：

1. 部分段落是2-3字短文本（如"2周"），PDF文本层行宽拆分后首段匹配失败
3. 文档末尾注入的脏数据段在XML清洗后被正确移除，PDF中自然找不到对应文本

这些情况并非转换保真度问题，而是metric算法的边界。**真实样本到位后需要用基于DOCX分节符/分页符的更稳健估算策略重新校准。**

## 4. 模块架构

```
pdf_convert/
├── __init__.py          # 重导出 convert_docx_to_pdf / ConversionReport
├── converter.py         # 统一入口 + 降级链路管理
├── libreoffice.py       # 主选引擎（已实现并验证）
├── onlyoffice.py        # 备选引擎（占位，需 DOCANCHOR_ONLYOFFICE_URL 环境变量）
└── word_com.py          # 兜底引擎（仅Windows）
```

降级链路默认：`libreoffice → onlyoffice → word_com`，可在配置中调整。

## 5. 已知限制

1. **视图配置生效依赖LibreOffice宏**：当前通过命令行参数控制输出PDF，部分"关闭修订显示"需在LibreOffice Options中固化
2. **字体替换记录未采集**：当前`font_replacements`字段为预留，未来通过LibreOffice日志解析
3. **降级链路后两个引擎未启用**：OnlyOffice需要HTTP服务地址，Word COM仅Windows

## 6. 用户样本到位后行动清单

- [ ] 用户提供5-10篇DOCX样本
- [ ] 在每篇样本上跑`measure_fidelity`
- [ ] 按脏度分桶统计（轻/中/重）
- [ ] 任意样本fail则启用降级链路
- [ ] 全部通过则签署Go/No-Go，进入阶段1第6天