---
okf: v0.1
type: Log
title: developer-experience — 变更日志
tags: [solutions, developer-experience, log]
---

# developer-experience 变更日志

## 2026-10-28

- **新增**: `gitignore-sensitive-pattern-hides-source-module.md` — `.gitignore` 的 `*token*` 会静默漏掉正常源码与测试（本次 `token_cache.py`）；本地测试与增量部署都正常，干净 clone 才暴露。用 `git check-ignore -v` / `git ls-files` / clean-tree import 检查。
