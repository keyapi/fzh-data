# pdf_to_md — PDF → Markdown 转换 + OCR 文字识别

## 快速摘要

将 PDF 文档（含截图/扫描件）完整转换为结构化 Markdown。纯文本页直接提取，截图页自动 OCR 识别中英文文字（含表格数据）。

## 目录结构

```
pdf_to_md/
├── AGENT_HANDOFF.md              ← 本文档
├── scripts/
│   └── pdf_to_md.py              ← 转换脚本（主入口）
├── .agents/skills/
│   └── pdf-to-md/SKILL.md        ← Claude Code 技能定义
└── 数据源/
    ├── listing优化智能体.pdf      ← 样例 PDF（10页）
    ├── listing优化智能体.md       ← 转换后的 Markdown
    └── listing_images/            ← PDF 中提取的截图
```

## 快速启动

```bash
cd D:\Claude Demo\fzh-data\pdf_to_md

# 确保依赖已安装
pip install pymupdf easyocr pillow numpy

# 运行转换
python -X utf8 scripts/pdf_to_md.py "数据源/要转换的文件.pdf"

# 强制 OCR（跳过文本层）
python -X utf8 scripts/pdf_to_md.py --ocr-only "数据源/文件.pdf"
```

输出文件与 PDF 同目录，文件名相同、扩展名为 `.md`。

## 依赖

| 包 | 用途 |
|----|------|
| `pymupdf` (fitz) | PDF 文本提取 + 页面渲染 |
| `easyocr` | 图片文字识别（中英文） |
| `pillow` | 图片加载（解决 OpenCV 中文路径问题） |
| `numpy` | 图片数组转换 |

首次运行 easyocr 会自动下载识别模型（约 100MB），后续使用已缓存。

## 工作流程

```
PDF 文件
  │
  ├─▶ 有文字层? ──▶ page.get_text() 直接提取
  │
  └─▶ 纯截图? ───▶ page.get_pixmap() → PIL → numpy → easyocr
                      │
                      └─▶ 返回识别文本（段落模式）
```

## 硬约束

1. **中文路径处理**：OpenCV 的 `imread` 不支持中文路径，脚本内部通过 `PPaIPIL` → `numpy` 数组传入 easyocr，不要改为直接文件路径。
2. **首次运行慢**：easyocr 需下载模型，CPU 模式下后续 OCR 每页约 5-30 秒（取决于截图复杂度和分辨率）。
3. **OCR 准确率**：受截图质量影响。表格类数据建议人工校验数值。
4. **编码**：Windows 下必须使用 `python -X utf8` 避免 GBK 编码报错。

## 已知问题

- `easyocr` 的 `paragraph=True` 模式返回 `(text, conf)` 二元组（非三元组），解包时已兼容处理
- 高分辨率图片 OCR 较慢，可考虑降低 `dpi` 参数（当前 200）

## 输出

- Markdown 文件包含页面分隔符 `---` 和页码标记 `**第 N 页**`
- 截图识别出的文字直接嵌入文档正文，不保留原图引用
- 表格类数据尽量还原为 Markdown 表格格式

## 参考

- 转换脚本：`scripts/pdf_to_md.py`
- 技能定义：`.agents/skills/pdf-to-md/SKILL.md`
- 样例数据：`数据源/listing优化智能体.pdf`（10页，含5页截图）
- 转换结果：`数据源/listing优化智能体.md`
