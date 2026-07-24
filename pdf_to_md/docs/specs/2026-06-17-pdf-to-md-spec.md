---
okf: v0.1
type: Spec
title: PDF→MD 转换规范
description: pdf_to_md 模块的转换 pipeline 和 MD 输出格式规范
tags: [pdf-to-md, spec, pipeline]
---

# PDF→MD 转换规范

> 日期：2026-06-17 | 状态：v7 已实现

## 输入

- 任意 PDF 文件（支持中英文混合、文本页 + 截图页）

## Pipeline

```
PDF
├─▶ 文本层（>50 字符）
│     └─▶ pymupdf get_text()
│           ├─▶ _fix_code_blocks() → ``` 围栏
│           ├─▶ _clean_page_numbers() → 去页码
│           └─▶ _format_text_layer() → # ## ### 标题 + - 列表
│
└─▶ 截图页（文本层 <50 字符）
      ├─▶ easyocr: 灰度+对比度 → OCR → 版面分析 → 表格/段落
      ├─▶ paddleocr: 原图 → ONNX OCR → 版面分析（Y=30）
      └─▶ qwen-vl-ocr: 原图 → API → 语义理解 → Markdown
```

## 输出格式

- 无页标记（MD 不分页）
- MD 标题层级（`#` `##` `###` `####`）
- ``` 代码围栏
- `-` bullet 列表
- Markdown 表格（`| col | col |` + `|---|---|`）
- 输出到 `out/<pdf_stem>.md`

## 模块结构

```
pdf_to_md/
├── pdf_to_md.py           ← 智能入口
├── easyocr_md.py          ← easyocr 引擎
├── paddleocr_md.py        ← PaddleOCR 引擎
├── qwen_vl_md.py          ← qwen-vl-ocr 引擎
├── _shared.py             ← 共享层（引擎无关）
├── docs/                  ← OKF 文档
├── out/                   ← 输出
└── scripts/               ← 存档
```

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--engine` | auto | auto/qwen/paddle/easyocr |
| `--dpi` | 200 (qwen) / 300 (others) | 渲染分辨率 |
| `--ocr-only` | false | 强制全页 OCR |
| Y_TOLERANCE | 15 (easyocr) / 30 (paddle) | 行分组容差 |
