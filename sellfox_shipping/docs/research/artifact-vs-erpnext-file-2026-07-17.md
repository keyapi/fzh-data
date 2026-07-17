---
okf: v0.1
type: Research
title: Artifact 存储与 ERPNext File 对照
description: 说明本模块 shipping_artifacts 与 ERPNext File doctype 的异同（扁平路径、private/files、content_hash=MD5）
timestamp: 2026-07-17
tags: [sellfox-shipping, artifact, erpnext, file, content-hash, md5]
---

# Artifact 存储 ↔ ERPNext File

## ERPNext File（用户观察 / 生产习惯）

| 点 | ERPNext |
|----|---------|
| 布局 | **扁平**：`/private/files/…` 或公开 `/files/…` |
| URL 名 | 可读文件名（可含中文、空格）；例 `/private/files/EN系统订单模板c9d39c.xlsx`、`/files/泰迪熊.jpg` |
| content_hash | **MD5**（32 hex）；例 `7191dfa6e28d8ca6162ea35854dabdd7` |
| 去重 | 同 hash 往往共用底层对象；多条 File 可用不同 `file_name` 挂到不同单据 |
| folder | **虚拟**目录，不必然等于真实磁盘路径 |

## 本模块 `shipping_artifacts`（现行）

| 点 | sellfox_shipping |
|----|------------------|
| 布局 | `data/artifacts/private/files/{stem}_{hash8}{ext}`（扁平） |
| 显示名 | `file_name` 字段；下载时用此名 |
| content_hash | **MD5**（32 hex）— **与 ERPNext File 对齐**（2026-07-17 由 SHA-256 改回） |
| 去重 | 同 `content_hash` → 同一 `storage_relpath` blob；多条 Artifact 可不同 `file_name` / `virtual_folder` |
| virtual_folder | 如 `lizard/export`、`lizard/import`，仅分类，不改物理路径 |
| 可见性 | 本地 Web `/lizard/artifacts`；尚无公网 `/files` vs `/private` 分流（单机内网） |

## content_hash = MD5（对齐决策）

- **目的**：与 EN `File.content_hash` 同算法，便于日后跨系统按 hash 互认/对账。
- **长度**：32 hex（128 bit），不是「不如 64 hex」——对内网去重足够。
- **实现**：`hashlib.md5(..., usedforsecurity=False)`（内容指纹，非密码学密钥派生）。
- **迁移注意**：改算法前若本地已有 SHA-256 登记的制品，旧 blob 路径不会与新 MD5 自动合并；可清空 `data/artifacts/` 后重新导出/导入，或忽略历史测试数据。

## 设计取舍（路径 / 权限）

- **保留扁平 private/files**：便于人肉在磁盘上辨认；短 hash 后缀防同名撞车。
- **不做完整 EN File 权限模型**：P1 无对外 CDN；一律按私有制品处理。
- **`/files` 公开分流**：暂不做。
