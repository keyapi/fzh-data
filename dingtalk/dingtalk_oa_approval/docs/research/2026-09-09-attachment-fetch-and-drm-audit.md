---
okf: v0.1
type: Research
title: 2026-09-09 钉钉 OA 附件拉取与 DRM 两月桶对照审计
description: 441 张销售收款确认单的附件拉取结果、失败构成、与 DRM 按人归档两月桶的三方对照，以及限流与判读纪律。
tags: [dingtalk, oa, attachment, drm, nas, audit, userNotExist]
resource: dingtalk/dingtalk_oa_approval/audit_vs_drm.py
timestamp: 2026-09-09
---

# 钉钉 OA 附件拉取与 DRM 两月桶对照审计

公开叙述用人名**拼音大写首字母**。附件缓存与对照 xlsx 都在**仓库外**核算缓存目录，不要 commit。

## 拉取

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py --start 2026-06-01 --end 2026-09-09
```

- 范围 2026-06-01～2026-09-09，共命中 **441** 张销售收款确认单。
- 按 `fileId` 去重后约 **284** 张下载成功，**157** 张有失败。
- 失败累计 **205 次**，**全部**是 `userNotExist`，集中在已离职/账号失效的发起人 **LN / LYX / WHR / WZ**。实例详情仍可读，所以能看到文件名，只是拿不到文件。
- 判读纪律：**钉钉附件 API 不能当离职人员的漏交证据**。API 下不来 ≠ 没交。LN 的 37 张单里都有「账期明细」文件名（如 `AMZBAINACA-2026-07-08.txt`），其中 7 月提交窗应保留的约 **10** 张，与 NAS 上其人名文件夹里的 10 个 txt 对得上。
- 失败原因逐单记在缓存的 `manifest.jsonl` 的 `errors[]` 里。

## 过滤

- 按 `keep_approval`（完成/审批中，且结果 ≠ 拒绝）复盘：441 张里 **15 张**本就不该保留（**13 已撤销 + 2 拒绝**）。例：`202607151740000224691`、`202606171537000286397`。
- 图片控件（`DDPhotoField`）已改为一律跳过。
- 结果：从 441 降到 426 张保留单。

## 与 DRM 两月桶对照

DRM 的 7/8 月桶合计 **230** 个文件：txt **107** / csv **85** / xlsx+xls **34** / pdf **4**，**无图片**。她只收解析用得上的类型。

| 分组 | 数量 | 含义 |
|------|------|------|
| 她有、我们同名已下 | **187** | 在职发起人，API 工作正常 |
| 她有、我们未下 | **43** | 主要是离职账号 `userNotExist`、她自制的「合并 Amazon」表、以及她自己解压后的 csv |
| 我们有、她 7/8 桶没有 | **117** | 主要是 YTQ 的 invoice/summary PDF（她有意不收）与 ZKY 审批中的 csv |

结论：**她该下的 Amazon/平台明细，在职发起人的我们都下到了**；她下到的离职人员文件，API 补不了，要用她已归档的副本。她漏下的核算文件很少，不是大面积漏。

## 综合集（本地）

- `organized_jul_aug/`：我们下到的 **299** 个。
- `organized_jul_aug/_from_drm_api下不了/`：从她桶**只读**拷入的 **41** 个。
- `combined_jul_aug/`（按 `账期YYYYMMDD-YYYYMMDD/{提交人}/{原名}` 惯例）：从她桶拷入 **228** + API 补入 **21**。
- API 补入的 21 个只有她桶里没有的（LTZ 的迟交 Amazon txt、YB 的独立站 csv、LXJ、JHP 的 zip、SWY 一份 pdf 等），已上传 NAS 并留操作记录；8 月桶里会重复的已删。
- 显式**跳过**：YTQ 的 invoice PDF **94**、ZKY 审批中的 csv **19**。桶里已有同茎 csv 时不再加 zip（zip 要解压后才能对）。

## 限流与耗时

- 钉钉标准版约**每应用每接口 20 QPS**，超了报 `QpsLimitForAppkeyAndApi`；组织月调用量约 **1 万次**。
- 同一 Client ID 共享额度，**不要开很多 worker**。2 个 worker 合计压在约 10–12 QPS 才可能略快；串行已够用。
- 441 张单串行约 **3.1–6.5 分钟**（实例间隔 0.12s + 每附件 0.05s）。

## 关联

- 失败根因与官方替代接口：[departed-originator-download.md](departed-originator-download.md)
- 7 月 Amazon 对账结论：[2026-09-10-july-amazon-period-reconcile.md](2026-09-10-july-amazon-period-reconcile.md)
- 审计脚本：`audit_vs_drm.py`（对照 + 本地整理，不动 NAS）、`compare_local_nas.py`（三方只读）、`combine_jul_aug.py`（生成综合集）
