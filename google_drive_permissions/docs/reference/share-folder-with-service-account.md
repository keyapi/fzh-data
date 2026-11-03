---
okf: v0.1
type: Reference
title: 把另一个 Google 账号的文件夹共享给现有机器人（无需新凭证）
description: 服务账号是独立机器人身份；登录目标账号把文件夹共享给 SA 邮箱即可，不用新建密钥或用户 OAuth
tags: [google-drive, service-account, sharing, credentials, folder]
timestamp: 2026-11-03
---

# 把另一个 Google 账号的文件夹共享给现有机器人

## 先纠正一个常见误解

现有 Google 能力用的是**服务账号**，它是一个**独立机器人身份**，不是 `kyzh2022@gmail.com` 这个账号：

```text
colab-gsheets@gsheets-351101.iam.gserviceaccount.com
```

所以「给另一个 Google 账号加权限」不是给机器人换账号，也不是生成新密钥，而是：
**让那个账号把目标文件夹共享给机器人邮箱。**

## 操作步骤

以 `mxdeals1023@gmail.com` 的「FZH运营知识中心」为例：

1. 在浏览器登录 `mxdeals1023@gmail.com`。
2. 打开 Google Drive，找到目标文件夹。
3. 右键 → **共享**（Share）。
4. 在「添加人员和群组」里填：
   `colab-gsheets@gsheets-351101.iam.gserviceaccount.com`
5. 角色选 **编辑者**（Editor / writer）。
6. 取消勾选「通知对方」（机器人没有收件箱）。
7. 点「共享」/「发送」。

共享是**继承**的：文件夹里的现有子项和以后新建的子项都会自动带上机器人权限。

## 验证

在仓库根目录运行：

```bash
uv run python drive_folder_ops/drive_folder_ops.py info .
uv run python drive_folder_ops/drive_folder_ops.py list . --recursive
```

预期能看到：

- 属主是目标账号
- 权限列表里有 `colab-gsheets@gsheets-351101.iam.gserviceaccount.com`，角色 `writer`
- `capabilities` 里 `canEdit` / `canAddChildren` / `canListChildren` 为 `true`

## 共享 Drive（Workspace）的特殊情况

如果目标不是个人 My Drive，而是 **Shared Drive**：

- 需要把机器人加为 **Shared Drive 成员**（内容管理员/贡献者），而不是只共享某个文件夹。
- API 调用要带 `supportsAllDrives=true`（本仓库脚本已默认带上）。

## 这授予了什么 / 没授予什么

**授予：**

- 该文件夹子树内的读取、编辑、新建子文件夹/文件
- 新子项自动继承共享
- 权限允许时，机器人也能再共享（`canShare`）

**没授予：**

- **全盘审计**：机器人仍看不到目标账号未共享给它的任何文件
- **目标账号的根目录**：除非显式共享根目录或具体文件夹
- **绕过存储配额**：服务账号在 My Drive 里没有存储配额，某些文件夹新建普通文件会
  `403 storageQuotaExceeded`。本文件夹实测可新建 Markdown/Sheet/Doc，换文件夹需重测。

## 什么时候才真的需要“新凭证”

| 需求 | 需要什么 |
|------|----------|
| 只是访问另一个账号的某些文件夹/表格 | **不需要新凭证**：共享给现有 SA 即可 |
| 需要一套隔离的身份/配额/审计边界 | 在目标账号名下新建 Cloud 项目 + 服务账号；仍只能看共享给它的文件 |
| 需要看目标账号**全部** Drive、建任意文件、做全盘权限审计 | 用户 OAuth（`drive` + `spreadsheets` scope）；外部应用 Testing 状态下 refresh token 约 7 天过期 |

**不要为了“换个账号”而新建服务账号**：新 SA 不会自动看到任何文件，仍然要逐个共享；
而且所有服务账号在 My Drive 都没有存储配额。

## 已知坑

- **「仅属主可改共享」**：如果目标文件的 `writersCanShare=false`，机器人即使有 writer
  也不能增删共享；读取/改内容不受影响。属主可用 `PATCH files/{id}` 把
  `writersCanShare` 改为 `true`。判断时要用 **SA 凭证**看 `capabilities.canShare`，
  用属主凭证查永远是 true。
- **同名文件**：Drive 允许同名；脚本遇到不唯一会列候选并拒绝猜测。
- **PII**：权限台账里的员工邮箱只放受控 Google Sheet，不进 git。文件夹 ID 与机器人邮箱不是秘密。
