---
okf: v0.1
type: Handoff
title: drive_folder_ops — Agent 交接说明
description: 共享 Drive 文件夹读写：凭证、命令、实测结果、配额与网络坑
updated: 2026-11-03
---

# drive_folder_ops — Agent 交接说明

> 人读文档: [README.md](README.md)

## 1. 凭证与根目录

| 项目 | 值 |
|------|----|
| 服务账号私钥 | `GSPREAD_SERVICE_ACCOUNT_FILE`，默认向上查找 `secrets/gsheets-service-account.json` |
| 机器人邮箱 | `colab-gsheets@gsheets-351101.iam.gserviceaccount.com` |
| 根文件夹 | `FZH运营知识中心` |
| 根文件夹 ID | `1RGSCHVGlCFQz7cAdMtdL66VU45758ntp` |
| 属主 | `mxdeals1023@gmail.com` |
| SA 角色 | `writer`（`canEdit/canAddChildren/canListChildren/canShare` 均 true） |

**不需要用户 OAuth。** `secrets/gsheets-user-oauth.json` 已过期（`invalid_grant`），本模块不使用它。
**不需要新凭证。** 服务账号是独立机器人身份；换账号的文件只需把文件夹共享给机器人邮箱。

## 2. 已验证（2026-11-03）

`smoke-test --apply` 在根目录下建临时文件夹并测试，结果：

```text
md_create      OK
md_readback    OK
sheet_create   OK
sheet_rw       OK
doc_create     OK
cleanup        OK
```

`write` 命令另做了创建 → 回读 → 覆盖 → 备份 → 清理的端到端测试，全部通过。
备份落在 `~/.claude/backups/drive_folder_ops/`（仓库外）。

## 3. 命令

```bash
# 根目录用 .（Windows Git Bash 会把单独 / 转成盘符路径）
uv run python drive_folder_ops/drive_folder_ops.py info .
uv run python drive_folder_ops/drive_folder_ops.py list . --recursive
uv run python drive_folder_ops/drive_folder_ops.py read "00_候选与修正/xxx.md"
uv run python drive_folder_ops/drive_folder_ops.py write "00_候选与修正/xxx.md" --from ./x.md --apply
uv run python drive_folder_ops/drive_folder_ops.py write "00_候选与修正/xxx.md" --from ./x.md --overwrite --apply
uv run python drive_folder_ops/drive_folder_ops.py mkdir "运营2部/新分类" --apply
uv run python drive_folder_ops/drive_folder_ops.py sheet-new "运营2部/汇总" --apply
uv run python drive_folder_ops/drive_folder_ops.py sheet-write "运营2部/汇总" --range A1 --values-json ./data.json --apply
uv run python drive_folder_ops/drive_folder_ops.py sheet-read "运营2部/汇总" --range A1:D20
uv run python drive_folder_ops/drive_folder_ops.py smoke-test --apply
```

## 4. 安全边界

- 所有写入前调用 `assert_under_root`，沿 `parents` 上溯到根 ID；越界拒绝。
- 覆盖必须 `--overwrite`；旧内容先备份到仓库外。
- 同名项不唯一直接报错，不猜第一个。
- `--expect-mtime` 只能尽力防并发；Drive 无原子 CAS。
- 不要把文档正文、员工 PII、任何 JSON 密钥写进 commit。

## 5. 坑

1. **根路径别写 `/`**：Windows Git Bash 会把它转成 `C:/Program Files/Git/`，报「不支持盘符路径」。用 `.`。
2. **IPv6 不通**：本机解析出 Google IPv6 地址但连接失败；模块强制 IPv4。`curl` 排错时用 `curl -4`。
3. **SSL EOF 是间歇的**：`www.googleapis.com` 偶发 `UNEXPECTED_EOF_WHILE_READING`；重试并回退到 `content.googleapis.com`。
4. **存储配额**：服务账号在别的文件夹可能无法新建普通文件；本文件夹实测可以。被拦时不要静默改成 Google Doc。
5. **Google 原生文件**（Sheet/Doc）不能用 `write` 覆盖；分别用 `sheet-write` 或走 Docs API。
6. **SA 看不到未共享的文件**：即使同属一个账号，也必须显式共享；本模块不是全盘审计工具。

## 6. 测试

```bash
uv run pytest drive_folder_ops/tests -q
```

单测只覆盖纯函数（路径规范化、query 转义、祖先链守卫、配额识别、凭证路径），不碰网络。
真实写入用 `smoke-test --apply`，它会在根目录建临时文件夹并在结束时移入回收站。
