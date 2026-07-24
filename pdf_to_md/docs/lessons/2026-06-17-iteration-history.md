---
okf: v0.1
type: Lesson
title: v1→v7 迭代历程
description: pdf_to_md 模块 7 轮迭代中的关键经验教训
tags: [pdf-to-md, lessons, iteration]
---

# 迭代历程与经验教训

> 日期：2026-06-16 ~ 2026-06-17 | 分支：listing-optimization

## 迭代概览

| v | 日期 | 关键突破 | 遗留问题 |
|---|------|---------|---------|
| v1 | 06-16 | OCR 不再空返回 | 无格式，纯拍平 |
| v2 | 06-16 | 版面分析表格检测 | 段落碎片化 |
| v3 | 06-16 | 代码块围栏 + 段落合并 | 中文 OCR 精度差 |
| v4 | 06-16 | 列合并 + 页码过滤 | 仍有单词拆裂 |
| v5 | 06-17 | PaddleOCR 精度提升 | oneDNN bug 需 workaround |
| v6 | 06-17 | VL 语义理解零拆裂 | API 依赖 |
| v7 | 06-17 | 模块拆分 + 文档化 | — |

## 关键教训

### Lesson 1: PDF 零宽字符陷阱
`代码块` 后跟 `​`，`strip() == "代码块"` 永远 False。
解决：`text.replace("​", "")`

### Lesson 2: easyocr 默认参数不适用于表格
`text_threshold=0.7` + `paragraph=True` → 表格截图全空。
解决：`text_threshold=0.3`, `low_text=0.3`, `detail=1`, `paragraph=False`

### Lesson 3: TEXT_IGNORE_ACTUALTEXT 破坏中文
pymupdf flag 导致 CJK 字符变 `�`。
解决：仅用 `TEXT_PRESERVE_WHITESPACE`

### Lesson 4: PaddleOCR 3.3 + Windows CPU = 崩溃
oneDNN `ConvertPirAttribute2RuntimeAttribute not support`。
解决：`engine='onnxruntime'` 绕过 Paddle 推理引擎

### Lesson 5: VL 模型需要 temperature=0.0
`temperature=0.1` 导致小数点格式随机变化、幻觉 artifact "T " 前缀。
解决：`temperature=0.0` + `_clean_vl_output` 后处理

### Lesson 6: 跨页代码块需要先合并再处理
逐页处理导致代码块跨页切断。
解决：Phase 1 合并所有文本页 → `_fix_code_blocks` → Phase 2 拆回

### Lesson 7: Python 版本锁定
3.14 不兼容 paddlepaddle。降级 3.12 后稳定。
`.python-version` 锁定版本。

## 同事协作

- PR #16 (`dev/jack-wq-ops-pdf`): easyocr 轻量方案，版面分析原型
- PR #18 (`dev/jack-wq-ops-pdf3`): 标题检测 + OCR 纠错词典 + out/ 输出
- 吸收到我们的 easyocr_md.py（纠错词典）+ _shared.py（标题检测）
