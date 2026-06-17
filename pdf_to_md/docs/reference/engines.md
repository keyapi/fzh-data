---
okf: v0.1
type: Reference
title: OCR 引擎对比
description: easyocr / PaddleOCR / qwen-vl-ocr 三引擎对比和选型指南
tags: [pdf-to-md, engines, comparison]
---

# OCR 引擎对比

## 概览

| 引擎 | 文件 | 类型 | 精度 | 速度 | 依赖 |
|------|------|------|------|------|------|
| easyocr | `easyocr_md.py` | 本地离线 | 中 | 30-60s/page | easyocr + torch |
| PaddleOCR | `paddleocr_md.py` | 本地 ONNX | 高 | 20-40s/page | paddleocr + onnxruntime (~200MB) |
| qwen-vl-ocr | `qwen_vl_md.py` | API 云端 | 最高 | 3-5s/page | DASHSCOPE_API_KEY |

## 精度对比（同一 PDF 第 6 页表格）

| 原文 | easyocr | PaddleOCR | qwen-vl-ocr |
|------|---------|-----------|-------------|
| camping chairs | `campng Chars` | `camp ing chairs` | **`camping chairs`** |
| folding chair | `foldng \| char` | `fo ld ing chair` | **`folding chair`** |
| 20.18% | `2018` | `20.18%` | **`20.18%`** |
| 露营椅 | `露营掎` | `露营椅` | **`露营椅`** |

## 选型建议

| 场景 | 推荐 |
|------|------|
| 离线/无 API | PaddleOCR |
| 最小依赖/快速上手 | easyocr |
| 最高精度/正式文档 | qwen-vl-ocr |
| 默认自动 | `pdf_to_md.py`（auto→qwen>paddle>easyocr） |

## 成本

| 引擎 | 成本 |
|------|------|
| easyocr | 免费 |
| PaddleOCR | 免费（模型下载一次） |
| qwen-vl-ocr | < ¥0.01/PDF（百炼按量付费） |
