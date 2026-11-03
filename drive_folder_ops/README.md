---
okf: v0.1
type: Guide
title: drive_folder_ops — 共享 Drive 文件夹 Markdown / Sheet 读写
description: 用现有服务账号在「FZH运营知识中心」等共享文件夹里列目录、读文件、写 Markdown、读写 Google Sheet
updated: 2026-11-03
---

# drive_folder_ops — 共享 Drive 文件夹 Markdown / Sheet 读写

> 本文给人看。Agent 请直接读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。

## 这是什么

在**已经共享给服务账号**的 Google Drive 文件夹里：

- 列目录、看权限与能力（`info` / `list`）
- 读 Markdown / 文本 / Google Doc / Google Sheet（`read`）
- 新建或覆盖 Markdown（`write`，默认 dry-run）
- 新建、读取、写入 Google Sheet（`sheet-new` / `sheet-read` / `sheet-write`）
- 一次性验证服务账号的 Markdown / Sheet / Doc 写入能力（`smoke-test`）

当前默认根目录是 **「FZH运营知识中心」**，属主 `mxdeals1023@gmail.com`，已共享给
`colab-gsheets@gsheets-351101.iam.gserviceaccount.com`（`writer`）。

## 为什么不需要新凭证

服务账号是**独立的机器人身份**，不是某个 Gmail 的账号。把目标文件夹共享给它的邮箱，
就完成了授权；现有 `secrets/gsheets-service-account.json` 直接可用。

换一个 Google 账号的文件时，只需要：

1. 登录该账号
2. 右键文件夹 → 共享
3. 填 `colab-gsheets@gsheets-351101.iam.gserviceaccount.com`，角色选「编辑者」
4. 用 `info .` / `list .` 验证

不需要新建服务账号、不需要新 JSON 密钥、不需要用户 OAuth。完整说明见
[google_drive_permissions 的参考文档](../google_drive_permissions/docs/reference/share-folder-with-service-account.md)。

## 快速开始

Windows Git Bash 会把单独 `/` 转成盘符路径，所以**根目录统一写 `.`**：

```bash
# 看根目录权限与能力
uv run python drive_folder_ops/drive_folder_ops.py info .

# 递归列目录
uv run python drive_folder_ops/drive_folder_ops.py list . --recursive

# 读一篇知识文档
uv run python drive_folder_ops/drive_folder_ops.py read "00_候选与修正/运营对话知识沉淀-权限边界与试点方式.md"

# 新建 Markdown（先 dry-run，加 --apply 才写）
uv run python drive_folder_ops/drive_folder_ops.py write "00_候选与修正/新知识.md" --from ./new.md
uv run python drive_folder_ops/drive_folder_ops.py write "00_候选与修正/新知识.md" --from ./new.md --apply

# 覆盖（会先备份到仓库外）
uv run python drive_folder_ops/drive_folder_ops.py write "00_候选与修正/新知识.md" --from ./new.md --overwrite --apply

# 新建 Google Sheet 并写数据
uv run python drive_folder_ops/drive_folder_ops.py sheet-new "运营2部/汇总" --apply
uv run python drive_folder_ops/drive_folder_ops.py sheet-write "运营2部/汇总" --range A1 --values-json ./data.json --apply
uv run python drive_folder_ops/drive_folder_ops.py sheet-read "运营2部/汇总" --range A1:D20
```

## 命令表

| 命令 | 说明 |
|------|------|
| `info [PATH]` | 名称、ID、属主、权限、SA 能力 |
| `list [PATH] [--recursive]` | 列目录（默认不递归） |
| `read PATH [--out FILE] [--range A1:Z1000] [--json]` | 读文本 / Markdown / Doc / Sheet |
| `write PATH --from FILE [--overwrite] [--expect-mtime MT] [--apply]` | 新建或覆盖 Markdown |
| `mkdir PATH [--apply]` | 创建文件夹，幂等 |
| `sheet-new PATH [--title T] [--apply]` | 新建 Google Sheet |
| `sheet-read PATH [--range A1:Z1000] [--json]` | 读 Sheet |
| `sheet-write PATH --range A1 --values-json FILE [--apply]` | 写 Sheet 并回读校验 |
| `sheet-tabs PATH` | 列出工作表 |
| `smoke-test [--apply]` | 创建临时文件夹，测 Markdown / Sheet / Doc，再移入回收站 |

所有写命令默认 **dry-run**，必须加 `--apply`。

## 安全规则

- 写入前沿 `parents` 上溯，必须到达 `ROOT_FOLDER_ID`；越界直接拒绝。
- 覆盖必须显式 `--overwrite`；覆盖前把旧内容备份到
  `~/.claude/backups/drive_folder_ops/`（仓库外）。
- 同名项不唯一时拒绝猜测，直接列出候选。
- `--expect-mtime` 做尽力而为的并发守卫；Drive 没有原子 compare-and-swap。
- 不打印文档正文到日志；提交前跑 `uv run python scripts/check_secrets.py`。

## 存储配额

服务账号在 Google Drive 的 My Drive 里**没有存储配额**，因此在某些共享文件夹中新建普通文件
（Markdown / xlsx / PDF）可能返回 `403 storageQuotaExceeded`。

本文件夹实测**可以**新建 Markdown、Google Sheet 和 Google Doc（见 `docs/log.md`）。
如果换到别的文件夹被配额拦住，`write` 会明确报错并给出三条路，不会静默改成 Google Doc：

1. 由文件夹属主手动建空 `.md` 占位文件，Agent 再覆盖内容
2. 与用户确认后改用 Google Doc
3. 重新评估用户 OAuth

## 网络说明

本机解析 Google IPv6 但 IPv6 不通，且 `www.googleapis.com` 偶发
`SSL: UNEXPECTED_EOF_WHILE_READING`。本工具：

- 强制 urllib3 只使用 IPv4
- 429/5xx/SSL/连接错误指数退避重试
- 连续失败后切换到 `https://content.googleapis.com`

看到 `retry` 或自动切主机属正常，不是凭证问题。

## 测试

```bash
uv run pytest drive_folder_ops/tests -q
uv run python drive_folder_ops/drive_folder_ops.py smoke-test --apply
```
