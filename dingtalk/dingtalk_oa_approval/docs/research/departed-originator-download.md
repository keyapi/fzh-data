---
okf: v0.1
type: Research
title: 离职发起人审批附件 userNotExist
description: 标准下载接口按发起人钉盘授权导致离职账号失败；官方出路是 OA 高级版专享下载接口。
tags: [dingtalk, oa, attachment, userNotExist]
timestamp: 2026-09-09
resource: dingtalk/dingtalk_oa_approval/probe_premium_download.py
---

# 离职发起人附件下载

标准接口 `POST /v1.0/workflow/processInstances/spaces/files/urls/download` 对已离职发起人（公开叙述 LN/LYX 等）返回 `userNotExist`。实例详情仍可读。

## 根因

该接口 body **没有 userId**，只收 `processInstanceId` + `fileId`。应用 accessToken 有效（能 GET 实例、能下在职发起人附件）。失败发生在后续钉盘授权：内部用实例 `originatorUserId` 去 cspace；通讯录里该人已失效 → `userNotExist`。

审批钉盘是企业唯一、客户端不可见的空间，不是个人钉盘「所有者」。管理员在客户端能打开，是因为**查看者是在职用户**，和服务端这条 Grant 不是同一路径。

## 官方替代

| 接口 | 离职 | 说明 |
|------|------|------|
| `POST /v1.0/workflow/premium/processInstances/spaces/files/urls/download` | **文档明确支持** | OA 高级版专享；权限「OA审批工作流读写（专享）」 |
| 专享 `.../premium/.../spaces/infos/query`、`.../authDownload` | 支持离职 userid | 取 spaceId / 批量授权 |
| 标准 `spaces/infos/query`、`authDownload` | 必须传**在职** userId | 授权给管理员后再 Grant，**仍可能 userNotExist** |
| 旧版 `topapi/processinstance/file/url/get` | 同标准 | 2022 起不推荐 |
| 微盘 `storage/.../downloadInfos` | 未写可用于审批钉盘 | 不当正式方案 |
| `withCommentAttatchment` | 只影响评论附件 | 不解决发起人离职 |

专享失败常见 `benefit.status.invalid`（未开通或过期 OA 高级版）。

用户 `userAccessToken` **无官方保证**可绕过；标准 Grant 没有查看者字段。重新入职且 UserID 必须与旧 `originatorUserId` 完全相同才可能救标准接口，再入职默认可能换 ID，不是推荐路径。

未开通专享时：综合 DRM 已归档 + 在职人员 API 下载。

对照实验：`uv run python dingtalk/dingtalk_oa_approval/probe_premium_download.py`（只看是否有 `downloadUri`，不 GET 文件）。

2026-09-09 对一张失败单实测：标准接口仍 `userNotExist`；专享接口 `403 Forbidden.AccessDenied.AccessTokenPermissionDenied`，需开通权限 `Premium.Workflow.ReadWrite.All`（以及 OA 高级版权益）。申请入口在钉钉开放平台应用权限。

2026-09-10 实例：审批 `202607231544000528489` 账期日期 2026-07-18，附件名 `AMZRosoonSE-2026-07-18.txt` 已在表单「账期明细」；标准 Grant `userNotExist`；NAS 对应月桶无该文件。说明「核算有行」不等于「API 或 NAS 已有 txt」。未开通专享时用 DRM 已归档，或经 `web_automation` dispatch 走管理后台（人在职会话下载）。

## 文档

- [标准下载](https://open.dingtalk.com/document/orgapp/download-an-approval-attachment.md)
- [专享下载（支持离职）](https://open.dingtalk.com/document/orgapp/api-premiumgrantprocessinstancefordownloadfile.md)
- [专享取空间](https://open.dingtalk.com/document/orgapp/api-premiumgetattachmentspace.md)
- [专享授权](https://open.dingtalk.com/document/orgapp/api-premiumaddapprovedentryauth.md)
- [专享能力说明](https://open.dingtalk.com/document/orgapp/description-of-new-oa-approval-premium-exclusive-openapi-and-solutions.md)
