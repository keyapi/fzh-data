---
okf: v0.1
type: Research
title: 钉钉管理后台浏览器补下载账期 Excel/附件
description: 标准 API 对离职发起人 userNotExist、专享接口未开通时，用在职会话走管理后台。必须先 dispatch --check。公开叙述用人名首字母。
tags: [dingtalk, browser, web-automation, oa, attachment]
timestamp: 2026-09-10
resource: web_automation/scripts/dispatch.py
---

# 钉钉管理后台浏览器补下载

给**下一任 Agent**（计划用 Claude + 浏览器）的范围说明。本文件不是许可扩大到全历史。

## 为什么要走浏览器

- 标准 OA 下载按发起人钉盘授权。离职发起人常 `userNotExist`。实例详情仍可读，附件可能已经在表单上。
- 专享 `.../premium/.../urls/download` 文档支持离职，但本企业实测 `benefit.status.invalid` / `403 AccessTokenPermissionDenied`（未开通 OA 高级版或未授 `Premium.Workflow.ReadWrite.All`）。
- 管理员在钉钉客户端能打开，是因为**查看者是在职用户**，和服务端应用 Grant 不是同一路径。浏览器应用的是这条在职会话。

详见 [departed-originator-download.md](departed-originator-download.md)。

## 本轮最高价值目标

| 优先级 | 对象 | 说明 |
|--------|------|------|
| 1 | 审批 `202607231544000528489` | LYX 7/23 发起，账期日期 2026-07-18，账户 `AMZRosoonSE`，表单已有 `AMZRosoonSE-2026-07-18.txt`。标准 API 失败。7 月桶只有 7/4 那份。 |
| 2 | 销售收款确认单 **管理后台 Excel** | 核算导出截止之后的单，可用 OA `get_instance` 按导出列补行（`fill_aug_from_oa.py` 已对 CLB 9/9 六张做过）。浏览器下全表可减少漏行。 |
| 3 | 其它离职发起人、NAS 缺 txt 但表单有附件的单 | 先用 `july_amz_by_account.py` / manifest `userNotExist` 列清单，**不要**扫全历史。 |

不要把「有核算行」当成「NAS 已有 txt」。SE 7/18 就是反例。

## 必须先做的路由

仓库里还没有钉钉管理后台的 `web_automation` capability。下一任 **不得**自己拼外部绝对路径、选 venv 或直接装 OCR。

```text
uv run python web_automation/scripts/dispatch.py <task> --check
```

按输出状态字面执行：`READY` / `NEED_BROWSER` / `NEED_LOGIN` / `NEED_OCR` / `NEED_USER_CONFIRMATION` / `BLOCKED`。

若 `--check` 报没有对应 task / `BLOCKED`：停下来告诉用户，先加能力矩阵并确认范围，再写浏览器脚本。不要为了「先下下来」绕过 dispatch。

写操作（上传 NAS、改审批）无范围确认时必须是 `NEED_USER_CONFIRMATION`。本任务默认范围：

- 只补 **7 月 Amazon 已确认缺口**（SE 7/18；以及用户当场点名的其它单）
- 不要扩大到全店铺、全历史桶、9 月未开桶
- 下载落后盘到模块 `data/`（gitignore）或用户指定缓存；**不要写** `D:\NAS与我共享\`
- 真要进财务桶：NAS FileStation（`fzh.nas`），按**账期日期自然月**进已有桶

## 归档口径（下载后仍要遵守）

- 木已成舟：发起日 ≤ 2026-07-03 已进 6 月的，不要再改归 7 月
- Amazon 账期只认 `.txt`
- 21 位审批编号当文本
- NAS 人名夹 = 提交人，不是渠道负责人
- 真名文件夹只在本地 `person_folders.local.json`；公开叙述用拼音首字母

## 7 月对照结论（避免浏览器白跑）

赛狐 7 月 `groupPage` **95** 组。松口径有 NAS 或核算 **73**；打款 0 且两侧无 **21**；有打款且两侧无 **1**（`AMZRosoonIT` 7/8，**缺钉钉**，浏览器也下不到附件，补交找 SYX）。

浏览器解决不了「没交钉钉」。它只解决「单上有文件、API 下不来、NAS 没有」。

完整过程：[2026-09-10-july-amazon-period-reconcile.md](2026-09-10-july-amazon-period-reconcile.md)。
