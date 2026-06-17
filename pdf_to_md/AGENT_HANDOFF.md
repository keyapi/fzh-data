# pdf_to_md — PDF → Markdown 转换 + OCR 文字识别

## 快速摘要

将 PDF 文档（含截图/扫描件）完整转换为结构化 Markdown。纯文本页直接提取 + 代码块格式修复，截图页自动 OCR + 版面分析（表格/段落分流）。

## 目录结构

```
pdf_to_md/
├── AGENT_HANDOFF.md              ← 本文档
├── scripts/
│   ├── pdf_to_md.py              ← 混合方案脚本（主入口，v3）
│   └── pdf_to_md_easyocr.py      ← 同事脚本（v2，版面分析原型）
├── .agents/skills/
│   └── pdf-to-md/SKILL.md        ← Claude Code 技能定义
└── 数据源/
    ├── listing优化智能体.pdf      ← 样例 PDF（10页：5页文本 + 5页截图）
    ├── listing优化智能体.md       ← 当前最佳输出（v3 混合方案）
    ├── listing优化智能体_v1_flat.md    ← v1 纯 OCR 直出版本
    ├── listing优化智能体_v2_table.md   ← v2 同事脚本输出
    ├── listing优化智能体_v3_hybrid.md  ← v3 混合方案输出
    ├── listing优化智能体_v4_final.md   ← v4 后处理管线输出（当前）
    ├── listing优化智能体_backup.md     ← 改版前原始输出
    └── listing_images/            ← PDF 中提取的截图
```

## 快速启动

```bash
cd pdf_to_md

# 确保依赖已安装
uv pip install pymupdf easyocr pillow numpy

# 运行转换（默认 300 DPI + 版面分析）
uv run python -X utf8 scripts/pdf_to_md.py "数据源/要转换的文件.pdf"

# 强制 OCR（跳过文本层）
uv run python -X utf8 scripts/pdf_to_md.py --ocr-only "数据源/文件.pdf"

# 调整 DPI（影响 OCR 精度和速度）
uv run python -X utf8 scripts/pdf_to_md.py --dpi 200 "数据源/文件.pdf"
```

## 迭代历程（2026-06-16 ~ 06-17）

### v1 — 原始版本（pdf_to_md.py 初版）

**问题**：截图页 OCR 全部返回空，第 6-10 页无内容。

**根因**：
1. easyocr 默认 `text_threshold=0.7` 太高，表格截图文字置信度不够被丢弃
2. `paragraph=True` 抑制非段落布局（表格/散落文字）
3. 无图像预处理，PDF 渲染的 RGB 原图直入 OCR
4. `detail=1` 返回空列表时静默丢弃

**修复**（commit `ba3f792`）：
- 图像预处理：`img.convert("L")` + `ImageEnhance.Contrast(×2.0)`
- easyocr 参数：`text_threshold=0.3`, `low_text=0.3`, `detail=0`
- 移除 `paragraph=True`

**效果**：第 6-10 页能识别出文字，但纯拍平输出，无格式保留。

### v2 — 同事脚本（pdf_to_md_easyocr.py）

**改进**：
- 版面分析：`_group_rows` 按 Y 坐标分组 → `_is_table` 列数一致性检测 → `_format_table` 生成 Markdown 表格
- `_format_paragraphs` / `_format_list` 检测列表和结构化内容
- 默认 DPI 300（原 200）
- `detail=1, paragraph=False` 获取 bbox 坐标

**优势**：表格截图（第 6、8、9 页）能正确输出 Markdown 表格。

**问题**：纯文本页（第 7、10 页）段落被打碎成短行碎片，因为 `_group_rows` 对文本行也做了切分，`_format_paragraphs` 无合并逻辑。

### v3 — 混合方案

**集成逻辑**：

| 场景 | 处理方式 |
|------|----------|
| 文本层页面 | pymupdf `get_text()` + 代码块检测修复 |
| OCR 页面 → 表格 | `_format_table()` → Markdown 表格 |
| OCR 页面 → 段落 | `_build_paragraph_text()` → 合并短行为连续段落 |

**关键修复细节**：

1. **零宽字符陷阱** ⚠️
   - PDF 文本层中「代码块」后跟 `​`（零宽空格）
   - `stripped == "代码块"` 永远为 False
   - 解决：全局 `text.replace("​", "").replace("﻿", "")`

2. **跨页代码块**
   - 原版逐页处理 → 代码块跨页被切断
   - v3 先合并所有文本层页面（`<!--PB-->` 分隔符），统一处理代码块，再拆回页面
   - 代码块从第 2 页「🔧 Gems 核心指令全文」→ 第 4 页「STEP 4」正确闭合

3. **段落合并**（`_build_paragraph_text`）
   - 非表格页的 OCR 结果按行分组后合并相邻短行
   - 检测新段落起始（中文数字、英文大写开头、符号标记如 ✅ 🔧 ⛔）
   - buffer 续行判断：上一行是否以标点结尾

4. **表格检测阈值**（`_is_table`）
   - ≥3 行数据
   - ≥40% 的行含 2+ 列
   - ≥50% 的行与主要列数一致（±1）

## 依赖

| 包 | 用途 |
|----|------|
| `pymupdf` (fitz) | PDF 文本提取 + 页面渲染 |
| `easyocr` | 图片文字识别（中英文） |
| `pillow` | 图片加载 + 预处理 |
| `numpy` | 图片数组转换 |

首次运行 easyocr 自动下载识别模型（约 100MB），后续使用已缓存。

## 工作流程

```
PDF 文件
  │
  ├─▶ 文本层 > 50 字符
  │     └─▶ 所有文本层页合并 → _fix_code_blocks() → 拆回页面
  │           ├─ 「代码块」标记 → ``` 围栏
  │           └─ 零宽字符清理
  │
  └─▶ 截图页（文本层 < 50 字符）
        └─▶ OCR（灰度+对比度增强，300 DPI）
              └─▶ _group_rows() → _is_table()
                    ├─ True  → _format_table() → Markdown 表格
                    └─ False → _build_paragraph_text() → 连续段落
```

## 硬约束

1. **中文路径处理**：PIL → numpy 传图，不经过 OpenCV 文件读取（不支持中文路径）
2. **首次运行慢**：easyocr 需下载模型，CPU 模式下每页 5-30 秒
3. **编码**：Windows 下必须使用 `python -X utf8`
4. **GPU 不可用**：当前环境 CPU only，easyocr 使用 `gpu=False`

## 已知问题与待改进

| 问题 | 影响 | 状态 |
|------|------|------|
| ~~OCR 英文词被拆成多列~~ | v4 `_merge_table_columns` 已修复 | ✅ 已解决 |
| ~~页码脚注数字未过滤~~ | v4 `_clean_page_numbers` 已修复 | ✅ 已解决 |
| PaddleOCR 3.x + paddlepaddle 3.3 + Windows CPU | oneDNN PIR 转换 bug，predict() 崩溃 | 🔒 阻塞 |
| easyocr 英文 OCR 精度 | 单词仍有个别字符误识别 | ⚠️ 持续 |
| PDF→MD 原文格式丢失 | 粗体/斜体/层级缩进无法还原 | ⬜ 待办 |
| Python 3.12 降级 | 为 PaddleOCR 兼容从 3.14→3.12 | 📌 已切换 |
| PDF→MD 原文格式丢失 | 粗体/斜体/层级缩进无法还原 | 可能需要 markitdown 或多模态 LLM |

### v4 — 后处理管线（当前主脚本，2026-06-17）

**改进**（commit `a33963e`）：

1. **表格列合并**（`_merge_table_columns`）
   - 检测相邻短英文（2-8 字符），判断是否为被 OCR 拆开的单词片段
   - 例如 `foldng | char` → `folding char`, `foldab | le` → `foldable`
   - `_looks_split()` 验证合并后长度在 4-20 字符内

2. **页码 artifacts 清理**（`_clean_page_numbers`）
   - 检测单独成行的 1-3 位数字
   - 仅当相邻行也是数字行时（连续页码序列）才移除
   - 文本层第 2-4 页的 `1 2 3 ... 46` 页码序列完全清除

3. **text_threshold 调优**：0.3→0.4 减少噪声，low_text=0.2 保留低密度区域

4. **预处理回退**：`autocontrast + SHARPEN` 引入伪影导致 OCR 更差，回退为灰度+对比度增强

**Python 版本**：3.14→3.12 降级（为 PaddleOCR 兼容预留）

### PaddleOCR 调研（2026-06-17）

**尝试**：PaddleOCR 3.7.0 + paddlepaddle 3.3.1 → Windows CPU

**结论**：BLOCKED。`predict()` 在 text_detection 阶段崩溃：
```
NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
  [pir::ArrayAttribute<pir::DoubleAttribute>]
  (at onednn_instruction.cc:118)
```
根因是 paddlepaddle 3.3 PIR→oneDNN 转换不兼容。FLAGS_use_mkldnn=0 不生效，PaddleOCR v2 无法安装（PyPI 网络超时）。

**替代路径**：
- 等 paddlepaddle 修复 oneDNN bug
- Docker 内跑 PaddleOCR（Linux 无此 bug）
- 换其他 OCR 引擎（surya-ocr 不兼容 py3.14，Tesseract 中文弱）
- 当前最优：继续打磨 easyocr 管线

## 对比分支

同事正在用另一种方案实现 PDF→MD 转换，后续需对比：
- 对比文件：v3 输出 vs 同事输出
- 评测维度：表格准确率 / 段落流畅度 / 代码块完整性 / 特殊字符处理
- 三个备份版本已在 git 中（`_v1_flat.md`, `_v2_table.md`, `_v3_hybrid.md`）

## 输出

- Markdown 文件包含页面分隔符 `---` 和页码标记 `**第 N 页**`
- 表格页输出为 Markdown 表格格式
- 文本页代码块自动包裹 ``` 围栏
- 图片文件不嵌入 MD，需要时可从 PDF 重新提取

## 参考

- 转换脚本（主）：`scripts/pdf_to_md.py`
- 转换脚本（原型）：`scripts/pdf_to_md_easyocr.py`
- 技能定义：`.agents/skills/pdf-to-md/SKILL.md`
- 样例数据：`数据源/listing优化智能体.pdf`（10页，含5页截图）
