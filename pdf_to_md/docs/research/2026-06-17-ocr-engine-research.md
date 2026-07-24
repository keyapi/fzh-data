---
okf: v0.1
type: Research
title: OCR 引擎调研
description: PDF 截图→Markdown OCR 引擎选型调研（2026-06-17）
tags: [pdf-to-md, ocr, research, easyocr, paddleocr, qwen-vl]
---

# OCR 引擎调研

> 日期：2026-06-17 | 分支：listing-optimization

## 调研背景

PDF `listing优化智能体.pdf`（10 页：5 页文本 + 5 页 Excel/文本截图）需要转为 Markdown。
文本层页面用 pymupdf 直接提取，截图页需要 OCR。

## 方案评估

### 方案 1: easyocr + 图像预处理

- 灰度化 + 对比度增强（`ImageEnhance.Contrast(2.0)`）
- `text_threshold=0.4`, `low_text=0.2`
- 默认参数 `text_threshold=0.7` 导致表格截图返回空
- 英文精度有限，单词拆裂问题严重

### 方案 2: PaddleOCR ONNX Runtime

- PaddleOCR 3.7.0 原生支持 `engine='onnxruntime'`
- 绕过 paddlepaddle 3.3.1 Windows CPU oneDNN bug
- 中文精度好，英文优于 easyocr
- 仍有轻度单词拆裂（`camp ing` vs `camping`）

### 方案 3: qwen-vl-ocr API

- 阿里云百炼 DashScope API
- 语义理解表格，零单词拆裂
- `temperature=0.0` 确保输出稳定性
- 需 `_clean_vl_output()` 后处理过滤模型幻觉 artifact

### 方案 4: surya-ocr / marker-pdf

- 不支持 Python 3.14，降级 3.12 后 pillow 编译失败
- 未采纳

## 结论

- **首选** qwen-vl-ocr（精度最高，成本极低）
- **离线** PaddleOCR ONNX
- **降级** easyocr（无需额外安装）
