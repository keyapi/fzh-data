---
okf: v0.1
type: Reference
title: 钉钉 OA 附件 API 与归档规则
timestamp: 2026-09-09
updated: 2026-11-02
---

# 钉钉 OA 附件 API 与归档规则

## 权限

| 权限 | 用途 |
|------|------|
| Workflow.Instance.Read | GET 实例详情、按 processCode 列实例 |
| Workflow.Instance.Write | 下载附件（官方下载接口要求写权限）；拿审批钉盘 spaceId；发起实例 |
| Workflow.Form.Read | 列可见模板（销售收款确认单可能不在可见列表里，已知 processCode 仍可查） |
| Storage.UploadInfo.Read | 带附件发起：拿 OSS 上传凭证（`uploadInfos/query`） |
| Storage.File.Write | 带附件发起：commit 入库（`files/commit`） |

列实例 `POST /v1.0/workflow/processes/instanceIds/query` 文档写明仅**企业内部应用**。new-api 应用虽显示 Client ID，原 AgentId 仍按内部应用拿 token，已实测可列、可读、可下。

## 应用与权限选型

| 权限 | 要/不要 | 说明 |
|------|---------|------|
| `Workflow.Instance.Read` | **要** | 读实例详情、按 processCode 列实例 |
| `Workflow.Instance.Write` | **要** | 下载附件（下载接口虽然只读，官方仍要求写权限）；发起实例、查审批钉盘 spaceId |
| `Workflow.Form.Read` | 建议留 | 列可见模板、核对 processCode |
| `Storage.UploadInfo.Read` | 带附件发起时**要** | 拿 OSS 上传凭证。已有 Workflow 写权限不够。开完必须**发布新版本** |
| `Storage.File.Write` | 带附件发起时**要** | commit 入库。缺它时 PUT 已 200、commit 403。开完必须**发布新版本** |
| `qyapi_aflow`（审批流数据管理） | **不要** | 那是流程中心待办（把自有审批同步进钉钉），与读后台**原生** OA 单无关 |

当时这几个权限是**临时**加在 new-api 那套应用上的，注意两点：

- 登录应用（第三方企业应用）同时拿「写 + 下附件」权限，权限面过大。
- `instanceIds/query`（按提交窗自动扫全量）**只支持企业内部应用**。将来想按窗口自动扫，挂在第三方应用上会卡住。

**建议**：OA 附件单独用一个**企业内部 H5 微应用**（或已有的内部应用），只开上面的 `Workflow.*`（读）和按需的 `Storage.*`（带附件发起）；new-api 登录应用保持员工相关权限，并把 `qyapi_aflow` 拿掉。

加权限后通常还需要：**发布新版本 + 管理员重新授权**；内部应用有时要在 OA 里把该应用**关联到「销售收款确认单」模板**，否则实例详情/下载报 `noPermission` / `processGetFailedByParameter`。

## 端点

1. `POST /v1.0/oauth2/accessToken`
2. `POST /v1.0/workflow/processes/instanceIds/query`（窗口 ≤120 天）
3. `GET /v1.0/workflow/processInstances?processInstanceId=`
4. `POST /v1.0/workflow/processInstances/spaces/files/urls/download` → `downloadUri` 15 分钟
5. 带附件**发起**（2026-11 实测，详见 [dingtalk-oa-create-receipt-with-attachments.md](../../../docs/solutions/integration-issues/dingtalk-oa-create-receipt-with-attachments.md)）：
   - `POST /v1.0/workflow/processInstances/spaces/infos/query`（`userId` + `agentId`）→ 审批钉盘 `spaceId`
   - `POST /v1.0/storage/spaces/{spaceId}/files/uploadInfos/query?unionId=` → `HEADER_SIGNATURE` URL + 请求头
   - OSS **PUT 只带这些签名头**。Python `urllib.request` 带 `data=` 会擅自加 `Content-Type: application/x-www-form-urlencoded` → `SignatureDoesNotMatch`。改 `requests.Session()`，`sess.headers.clear()` 后再 PUT。
   - `POST /v1.0/storage/spaces/{spaceId}/files/commit?unionId=` → `dentry.id` 即 `fileId`
   - `POST /v1.0/workflow/processInstances`（`originatorUserId` + `processCode` + `deptId` + `formComponentValues`）
   - unionId：新通讯录 `GET /v1.0/contact/users/{userId}` 可能 404；旧 `POST https://oapi.dingtalk.com/topapi/v2/user/get?access_token=` 仍能返回 `unionid` / `dept_id_list`。存储上传必须用 unionId。
   - 表单：明细 `TableField` 的 `value` 是二维 JSON 数组字符串；附件 `DDAttachment` 的 `value` 是 `[{spaceId,fileId,fileName,fileSize,fileType}, …]` JSON 数组字符串。控件名：`TableField-K2K6QXPZ`、`DDAttachment-K2K7DF54`。
   - 已撤销 = `TERMINATED`。上一张仍 `RUNNING` 就不要再发。

表单「账期明细」=`DDAttachment`（fileId/fileName）；「图片」=`DDPhotoField`（`static.dingtalk.com` URL，不走下载接口）。评论附件默认下不了。

过滤：`keep_approval` = 状态完成/审批中（API `COMPLETED`/`RUNNING`）且结果不是拒绝（`refuse`）。已撤销 `TERMINATED`/`CANCELED`、拒绝单不下附件。图片控件不下。

下载接口对部分离职发起人返回 `userNotExist`。官方离职审计接口是 OA 高级版 `POST /v1.0/workflow/premium/processInstances/spaces/files/urls/download`。未开通前综合 DRM 已归档，或经网页自动化进管理后台（须 `web_automation` dispatch）。详见 [research/departed-originator-download.md](../research/departed-originator-download.md)。审批编号写出 Excel 必须当文本。

## Excel 导出

| 列 | API |
|----|-----|
| 数据id | processInstanceId |
| 审批编号 | businessId |
| 账期明细超链接 | processCode + processInstanceId + componentId=`DDAttachment-K2K7DF54~DDAttachment` |

pandas 读不到超链接，要用 openpyxl `cell.hyperlink.target`。

## 归档

DRM：`账期{提交窗}/{发起人姓名}/{原始文件名}`。原始文件名可能重。

本模块缓存：`data/files/{processInstanceId}/{fileId}__{原始文件名}`。

核算应放：按 `账期日期` 自然月对应的提交窗桶（迟交 Amazon txt 应从 8 月桶回到 7 月桶）。搬移只走 NAS，不改本地同步盘。
