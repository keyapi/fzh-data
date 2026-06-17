# PDF → Markdown 转换（pdf_to_md）

将 PDF 文档（含截图/扫描件）完整转换为结构化 Markdown。纯文本页直接提取，截图页自动 OCR 识别中英文文字。

## 目录结构

```
pdf_to_md/
├── AGENT_HANDOFF.md          ← Agent 交接文档
├── README.md                 ← 本文件
├── __init__.py               ← 包标记
├── scripts/
│   └── pdf_to_md.py          ← 转换主脚本
├── out/                      ← 输出目录
├── 数据源/                   ← 源 PDF 文件
└── 数据源样例/               ← 样例数据
```

## 依赖

| 包 | 用途 |
|----|------|
| `pymupdf` (fitz) | PDF 文本提取 + 页面渲染 |
| `easyocr` | 图片文字识别（中英文） |
| `pillow` | 图片加载 |
| `numpy` | 图片数组转换 |

```bash
pip install pymupdf easyocr pillow numpy
```

首次运行 easyocr 会自动下载识别模型（~100MB）。

## 用法

```bash
cd pdf_to_md
python -X utf8 scripts/pdf_to_md.py "数据源/要转换的文件.pdf"
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `pdf_path` | 必填 | PDF 文件路径（支持中文路径） |
| `--lang` | `ch_sim,en` | OCR 语言 |
| `--ocr-only` | 关闭 | 强制所有页使用 OCR |

输出文件与 PDF 同目录，文件名相同、扩展名为 `.md`。

## 处理流程

```
PDF → 有文字层? → page.get_text() 直接提取
      └→ 纯截图? → page.get_pixmap() → PIL → numpy → easyocr → 识别文本
```

## 输出格式

```
---
**第 1 页**
---

页面内容...

---
**第 2 页**
---

页面内容...
```

## 已知问题

- OCR 对复杂截图（如 Amazon Listing 排版）准确率有限，表格数据建议人工校验
- CPU 模式下每页 OCR 约 5-30 秒
- Windows 下须用 `python -X utf8` 避免 GBK 编码错误

## 参考

- 转换脚本：[scripts/pdf_to_md.py](scripts/pdf_to_md.py)
- Agent 文档：[AGENT_HANDOFF.md](AGENT_HANDOFF.md)
- 源文件：`数据源/`
