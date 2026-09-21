---
okf: v0.1
type: Guide
title: nas_mcp — 只读把群晖 NAS 暴露给 MCP 客户端（含 ChatGPT）
description: 复用 NAS_API 的 DSM 客户端 + stdlib MCP 传输；只暴露只读工具、路径锁死在 NAS_ROOT_FOLDER；Bearer 鉴权（已在 ChatGPT 实测可用）
tags: [nas, synology, mcp, chatgpt, read-only]
timestamp: 2026-09-21
---

# nas_mcp

把公司群晖 NAS **只读**地暴露给 MCP 客户端（Claude Desktop / Cursor / **ChatGPT 连接器**）。

## 一句话

**只读、路径锁死、Bearer 鉴权。** 没有创建/移动/**删除**能力 —— 这是刻意的设计，不是待办。

## 三条硬安全约束

1. **只读**：只暴露 **8 个**工具 —— `nas_health` / `nas_list_folder` / `nas_file_info` /
   `nas_search` / `nas_folder_size` / **`nas_read_image`** / **`nas_read_pdf`** / `nas_read_text`。
   **不暴露任何写或删**（`NAS_API/synology.py` 里的 `create_folder` / `create_subfolders` / **`delete_folder`** 一律不用）。
2. **权限边界交给 NAS 账号**（默认 `NAS_ALLOWED_ROOTS=*`）：MCP 只拦 `..` 路径逃逸，
   **能看什么由 `fzh.mcp` 这个 DSM 账号的文件夹权限决定** —— 加目录不用改服务。
   需要收紧时把 `NAS_ALLOWED_ROOTS` 设成显式列表（那时才有 MCP 层白名单）。
3. **不吐大文件**：`nas_read_text` 上限 256 KiB 且只允许文本类扩展名；
   `nas_read_image` 超过长边上限会自动等比缩小后重编码；其余二进制只给元数据。

## 为什么自建而不用现成的

VPS 上**没有 Node**，而仓库本来就是 Python；更重要的是两端都能复用**已验证过**的件：

| 复用 | 位置 |
|---|---|
| DSM 客户端（认证 + `NAS_ROOT_FOLDER` 范围） | [`NAS_API/synology.py`](../NAS_API/synology.py) |
| MCP 传输形状 | 2026-09-21 被 **ChatGPT 实测成功调用过**的最小实现 |

（曾评估第三方 `mrquj/mcp-server-synology` —— 设计好，但需要 Node；见 [可行性调研](../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md)。）

## 本地跑

```bash
# 凭证复用 NAS_API/.env（NAS_URL / NAS_USERNAME / NAS_PASSWORD / NAS_ROOT_FOLDER）
export NAS_MCP_TOKEN=<自己定一个长的>
uv run python -m nas_mcp.server          # 默认 127.0.0.1:8402
```

冒烟测试（**只读**，会真连 NAS）：

```bash
uv run python nas_mcp/tests/test_smoke.py
```

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `NAS_MCP_TOKEN` | ✅ | Bearer 令牌。**绝不写进仓库或镜像** |
| `NAS_URL` / `NAS_USERNAME` / `NAS_PASSWORD` | ✅ | 同 `NAS_API`（复用其约定） |
| `NAS_ALLOWED_ROOTS` | | `*`（默认）= **信任 DSM 账号权限**；或显式列目录（逗号/冒号分隔）做 MCP 层收紧 |
| `NAS_MCP_IMAGE_MAX_EDGE` | | 图片返回长边上限像素，默认 `1280` |
| `NAS_ROOT_FOLDER` | | 单根兼容项；仅在未设 `NAS_ALLOWED_ROOTS` 时生效 |
| `NAS_MCP_BIND` / `NAS_MCP_PORT` | | 默认 `127.0.0.1:8402`（**只绑回环**，由 nginx 反代） |
| `NAS_MCP_LOG` | | 可选，追加日志到文件 |

## 部署（VPS）

见 [docs/reference/deploy.md](docs/reference/deploy.md)。

## 目录

- [docs/index.md](docs/index.md) — OKF 索引
- [docs/reference/deploy.md](docs/reference/deploy.md) — 部署与 nginx 反代
- [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — Agent 交接
- 调研背景：[docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md](../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md)

## 非目标

- 不做写入/删除（**刻意**；要写入需单独评估并另开权限模型）
- 不做 per-user 权限（当前是「一个受限 DSM 账号 + 一个 token」；多用户见调研文档 §「鉴权两种场景」）
