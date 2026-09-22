---
okf: v0.1
type: Reference
title: 为什么把「改同事的 Colab notebook」做成独立工具箱 colab_kit（而不是塞进 google_drive_permissions）
date: 2026-09-22
category: tooling-decisions
module: colab_kit
problem_type: tooling_decision
component: tooling
severity: low
applies_when:
  - "要改同事的 Colab notebook 代码，纠结是手点、临时写脚本、还是用现成工具"
  - "想知道 colab_kit 与 google_drive_permissions 的分界（都碰 Google Drive / Colab）"
  - "要为一条「还在 Colab 里的业务流水线」做本地化迁移（如 PB 之后的下一条）"
tags: [colab, ipynb, drive-api, tooling-decision, module-split]
---

# 为什么把「改同事的 Colab notebook」做成独立工具箱

## Context

业务同事的流水线（Overstock 订单处理、PB 订单处理…）都跑在 **Google Colab notebook** 里，
代码在登录墙后面。改它只有两条路：让人手点，或走 Drive API。

一次会话里，为了适配同事改过的通途导出模板，同一个 notebook 被改了 **4 次**
（插入备份格、加 35 字符截断、给 FedEx 分支加 30 字符守卫、把 `!zip` 换成 `zipfile`）。
**每一次都是现写一遍 Drive 调用**：下载、定位 cell、改、上传、再下回来比对。
用完即散，下次还得重写。

## Guidance（本学习沉淀的做法）

**成立独立模块 `colab_kit/` + skill `colab-kit`**，把动作固化成带退出码的命令：

| 类型 | 命令 |
|---|---|
| 网络（Drive） | `meta` / `fetch` / `backup` / `guard` / `write` / `verify` |
| 本地（纯文件，可离线） | `cells` / `dump` / `find` / `insert` / `backup-cell` / `sed` / `syntax` / `diff` |

标准姿势固定成一条链：

```
fetch → guard → 本地改 → syntax → write → verify --expect-changed
```

三条设计取舍：

1. **网络与本地命令分开**。改 cell 是纯 JSON 操作，拆出来后可以离线跑、可以单测（14 例），
   不必每次都连 Drive；只有 `fetch`/`write`/`verify` 才需要网络。
2. **`verify` 与 `guard` 是一等公民，不是"记得的话"**。`verify --expect-changed 8,9` 用退出码
   断言"只有这几格变了"；`guard` 比 `modifiedTime` 挡并发。把这两步变成流程里的固定环节，
   是这套工具存在的**主要理由** —— 手写时它们最容易省掉。
3. **`sed` 默认拒绝多命中**。notebook 里"生效代码 + 注释掉的老代码"常常只差一个 `#`；
   实测 `find --text "merged_sku = "` 同时命中 **2 格**。默认拒绝比默默改错一格安全。

## 与 `google_drive_permissions` 的分界

两个模块都碰 Google Drive / Colab，但**调用面完全不同**：

| | `google_drive_permissions` | `colab_kit` |
|---|---|---|
| 管什么 | **权限**：谁能看/改（`permissions` API、台账） | **内容**：把 cell 读出来、改掉、写回去 |
| 典型动作 | 加/删共享、盘点离职账号权限 | 备份 cell、格内替换、回读比对 |
| 失败模式 | 权限判断错（`capabilities` 误读） | **写坏别人的活文档** |

合并会让"权限模块"这个心智模型被污染（下一个人会以为它只做权限，找不到执行工具），
所以**分开**，并在两边 handoff 互相指路。

## Why This Matters

- 这是**会重复**的需求：`pb_orders/` 已经把「PB 订单处理」从 Colab 迁进仓库，
  Overstock 这条将来也可能迁 —— 届时还要反复读那个 notebook。
- 这些动作里有一批"**写错很难发现**"的点：不校验就回写、老锚点多命中、语法自检时
  中和魔法行丢了缩进（会得到**假的** `IndentationError`）。固化成命令后，正确做法成为默认路径。
- 复利：`guard`/`verify` 这类"防呆"步骤一旦进了 CLI，就不会因为赶时间被跳过。

## When to Apply

- 要改同事的 notebook 代码，而不是自建脚本。
- 用户要求"**先备份再改**"某一格。
- 需要证明"我只动了该动的那一格"（`verify --expect-changed`）。
- 要给一条还在 Colab 里的流水线做本地化迁移 —— 先用 `colab_kit` 摸清它、再迁。

## Examples

一次真实会话跑出来的数字：

| 观察 | 值 |
|---|---|
| `pytest colab_kit/tests -q` | **14 passed** |
| 改动规模 | notebook 29 → 31 cells（备份格 + 说明格） |
| `guard --expect <过期值>` | **exit 2**（正确拒绝） |
| `find --text "merged_sku = "` | 命中 **2 格** → 证明 `sed` 该拒绝多命中 |
| `verify --expect-changed ""` | 无差异，exit 0 |
| 本地命令 vs 真实 31 格 notebook | `cells` / `diff` / `syntax` 全通 |

## Related

- `colab_kit/README.md`、`colab_kit/AGENT_HANDOFF.md` —— 命令表与踩坑
- `docs/solutions/developer-experience/colab-notebook-drive-api-editing.md` —— 做法与原理（正文）
- `docs/solutions/developer-experience/colab-shell-out-filename-spaces.md` —— 同批踩到的 `!zip` 坑
- `tooling-decisions/ce-okf-conversation-wrapup-skill.md` —— 同类先例：把一段固定动作固化成 skill 而不是每次手打
- `pb_orders/` —— 把 Colab notebook 本地化迁入仓库的先例
