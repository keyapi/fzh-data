---
okf: v0.1
type: Log
title: pdf_to_md 变更日志
description: PDF→MD 模块所有版本变更记录
tags: [pdf-to-md, changelog]
---

# 变更日志

## 2026-06-17

### v7 — 文件结构统一 + OKF 文档化
- 统一根目录脚本结构：`pdf_to_md.py` 智能入口 + 3 引擎独立脚本
- 移除 `scripts/pdf_to_md.py` thin wrapper
- 融入 Jack PR #18 OCR 纠错词典到 `easyocr_md.py`
- 采纳 OKF v0.1 文档规范，创建 `docs/`
- Commit: `100ed44`, `db9b238`

### v6 — qwen-vl-ocr 多模态引擎
- 阿里云百炼 DashScope API 集成
- `qwen_vl_md.py`：截图页语义理解，零单词拆裂
- `temperature=0.0` + `_clean_vl_output()` 后处理
- Commit: `cd61635`, `be07476`

### v5 — PaddleOCR ONNX Runtime
- `paddleocr_md.py`：ONNX 后端绕过 oneDNN CPU bug
- 中英文精度显著优于 easyocr
- Python 3.14→3.12 降级兼容
- Commit: `a04fa5e`

### v4 — 后处理管线
- `_merge_table_columns`：表格列合并
- `_clean_page_numbers`：页码过滤
- `text_threshold` 0.3→0.4
- Commit: `a33963e`

### v3 — 混合方案
- `_fix_code_blocks`：代码块 ``` 围栏
- 跨页代码块统一处理
- `_build_paragraph_text`：段落合并
- Commit: `2626f29`

## 2026-06-16

### v2 — 版面分析原型（同事脚本）
- `_group_rows` + `_is_table` + `_format_table` 表格检测
- `_format_paragraphs` 列表格式化
- PR #16 来源

### v1 — 初版
- 灰度+对比度增强图像预处理
- `text_threshold=0.3`, `low_text=0.3`
- 移除 `paragraph=True`
- Commit: `ba3f792`
