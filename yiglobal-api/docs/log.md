---
okf: v0.1
type: Log
title: yiglobal-api 变更日志
---

# 变更日志

## 2026-07-20

- **目录重命名**: `蜴国际-API/` → `yiglobal-api/`（与 `vite-api/` 命名风格对齐）
- **环境变量统一**: `YIGLOBAL_APP_TOKEN` / `YIGLOBAL_APP_KEY` / `YIGLOBAL_API_BASE_URL`（弃用 `LIZARD_*` 作为主名；脚本暂兼容旧名）
- **凭证**: 真实值仅仓库根 `.env`；见 `.env.example`
