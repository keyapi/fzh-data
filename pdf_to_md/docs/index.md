---
okf: v0.1
type: Index
title: pdf_to_md 文档索引
description: PDF→Markdown 转换模块的 OKF 文档导航
tags: [pdf-to-md, index]
---

# pdf_to_md — 文档索引

> 将 PDF（含截图/扫描件）转换为结构化 Markdown。支持 3 种 OCR 引擎。

## 快速导航

| 文档 | 类型 | 描述 |
|------|------|------|
| [log.md](log.md) | Log | 变更历史 |
| [reference/engines.md](reference/engines.md) | Reference | 三引擎对比 + 选型指南 |
| [research/2026-06-17-ocr-engine-research.md](research/2026-06-17-ocr-engine-research.md) | Research | OCR 引擎调研 |
| [specs/2026-06-17-pdf-to-md-spec.md](specs/2026-06-17-pdf-to-md-spec.md) | Spec | PDF→MD 转换规范 |
| [lessons/2026-06-17-iteration-history.md](lessons/2026-06-17-iteration-history.md) | Lesson | v1→v7 迭代历程 |

## 入口点

```bash
# 智能默认引擎（auto→qwen>paddle>easyocr）
uv run python pdf_to_md/pdf_to_md.py <pdf>

# 指定引擎
uv run python pdf_to_md/pdf_to_md.py --engine easyocr <pdf>
uv run python pdf_to_md/pdf_to_md.py --engine paddle <pdf>
uv run python pdf_to_md/pdf_to_md.py --engine qwen <pdf>
```

## 输出

所有输出在 `pdf_to_md/out/` 目录。
