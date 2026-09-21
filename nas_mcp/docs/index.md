---
okf: v0.1
type: Index
title: nas_mcp
description: 只读把群晖 NAS 暴露给 MCP 客户端（含 ChatGPT）
tags: [nas, synology, mcp, index]
timestamp: 2026-09-21
---

# nas_mcp

把公司群晖 NAS **只读**暴露给 MCP 客户端（Claude / Cursor / **ChatGPT 连接器**）。

**只读、路径锁死在 `NAS_ROOT_FOLDER`、Bearer 鉴权（已在 ChatGPT 实测可用）。**
**没有创建/移动/删除能力 —— 这是刻意设计。**

## 文档

| 你需要... | 读这个 |
|----------|--------|
| 概览、三条硬安全约束、本地怎么跑 | [../README.md](../README.md) |
| 部署到上海 VPS：Docker、nginx 反代、外部验证、接 ChatGPT | [reference/deploy.md](reference/deploy.md) |
| 为什么部署在 VPS 而不是 NAS、为什么自建而不是用第三方 | [../../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md](../../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md) |

## 工具（只读，15 个）

| 类别 | 工具 |
|------|------|
| 连通 / 浏览 | `nas_health` · `nas_list_shares` · `nas_list_folder` · `nas_file_info` · `nas_folder_size` · `nas_search` |
| 读内容 | `nas_read_text` · `nas_read_pdf`（渲染成图 + 抽文字）· `nas_read_image` · `nas_read_doc`（Office 文字） |
| 图片 / 校验 | `nas_thumbnail` · `nas_folder_thumbnails` · `nas_file_md5` |
| 压缩包 / 深链 | `nas_list_archive`（不解压看内容）· `nas_link`（File Station 深链） |

`nas_link` / `nas_file_info` / `nas_list_folder` 返回的链接是 **File Station 深链**，打开需 DSM 登录
—— 天然满足「有 NAS 权限的人才看得到」。格式**照抄 EN 产品物料库的 `encode_filestation_link()`**（双层 URL 编码），
**不是自己发明的**；`tests/test_smoke.py` 用真实样例钉住编码。
