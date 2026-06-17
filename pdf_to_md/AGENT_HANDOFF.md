# pdf_to_md — Agent 交接说明

> **脚本**: `pdf_to_md.py`（~300 行，唯一主脚本）

---

## 1. 业务背景

将 PDF 文档（含截图/扫描件）完整转换为结构化 Markdown：
- 纯文本页 → PyMuPDF 直接提取（检测标题/列表，过滤行号）
- 截图/图片页 → easyOCR + bbox 坐标版面分析（自动识别表格/列表/标题）

---

## 2. 处理流程

```
PDF
├─▶ 有文字层 (text > 50 chars)
│     → page.get_text()
│     → 过滤纯数字行（PDF 行号）
│     → 逐行检测标题（一、→##, STEP N→###, ✅→####）
│     → bullet 列表格式化
│     → 输出 Markdown
│
└─▶ 纯截图
      → page.get_pixmap(dpi=300)
      → PIL → numpy → easyOCR (paragraph=False, 含 bbox)
      → 按 Y 坐标分组为行 → 按 X 坐标排序
      ├─▶ 多列行 ≥40% + 列数一致 ≥50% → Markdown 表格
      └─▶ 单列
          ├─▶ 标题检测 → 加 ## / ### / #### 标记
          ├─▶ bullet/编号/中文字题 ≥25% → 列表
          └─▶ 否则 → 段落文本
```

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `has_text_layer(page)` | 判断页是否有 >50 字符的文本层 |
| `extract_text_page(page)` | 提取文本 → 过滤行号 → 检测标题/列表 |
| `_detect_heading(line)` | 检测一行是否为标题（中文序号/STEP/emoji/已有#） |
| `_format_text_line(line)` | 格式化单行（bullet 列表 → `- `） |
| `_group_rows(results, y_tol=15)` | 将 OCR bbox 按 Y 坐标分组为行，X 排序 |
| `_is_table(rows)` | 启发式判断是否为表格 |
| `_format_table(rows)` | 输出 Markdown 表格 |
| `_format_list(texts)` | 输出 Markdown 列表（bullet/编号/题头） |
| `_format_paragraphs(rows)` | 单列布局 → 检测标题/列表/段落 |
| `ocr_page(page, reader, dpi=300)` | OCR → 版面分析 → Markdown |
| `convert(pdf_path, ...)` | 主循环：逐页判断 → 处理 → 写文件到 out/ |

---

## 4. 命令行

```bash
cd pdf_to_md
python -X utf8 pdf_to_md.py "数据源/文件.pdf"
python -X utf8 pdf_to_md.py --ocr-only "数据源/文件.pdf"
python -X utf8 pdf_to_md.py --dpi 400 "数据源/文件.pdf"
```

---

## 5. 数据路径约定

| 角色 | 默认位置 |
|------|----------|
| 源 PDF | `pdf_to_md/数据源/*.pdf` |
| 输出 MD | `pdf_to_md/out/*.md` |
| 样例 | `pdf_to_md/数据源样例/` |

---

## 6. 输出格式

页面之间以空行分隔，无页码标记。标题自动识别：

```markdown
## 一、主要章节
### STEP 1｜子步骤
#### ✅ 要点标记

| 表格列1 | 表格列2 |
|---|---|
| 值 | 值 |

- 列表项
- 列表项
```

---

## 7. 已知问题

- **中文 OCR 准确率**：easyOCR 对复杂截图（小字体、中英文混排）准确率有限，表格列可能错位
- **CPU 模式慢**：每页截图 OCR 约 5-30 秒；首次运行需下载 ~100MB 模型
- **Windows 编码**：必须使用 `python -X utf8` 避免 GBK 编码报错
- **文本层提取**：PyMuPDF 可能带入不可见行号（已过滤纯数字行）

---

## 8. 依赖

| 包 | 用途 |
|----|------|
| `pymupdf` (fitz) | PDF 文本提取 + 页面渲染 |
| `easyocr` | OCR 文字识别（中英文） |
| `pillow` | 图片加载 |
| `numpy` | 图片数组转换 |

```bash
pip install pymupdf easyocr pillow numpy
```

---

*若与代码不一致，以 `pdf_to_md.py` 为准。*
