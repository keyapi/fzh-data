---
okf: v0.1
type: Reference
title: 钉钉 OA 附件 API 与归档规则
timestamp: 2026-09-09
---

# 钉钉 OA 附件 API 与归档规则

## 权限

| 权限 | 用途 |
|------|------|
| Workflow.Instance.Read | GET 实例详情、按 processCode 列实例 |
| Workflow.Instance.Write | 下载附件（官方下载接口要求写权限） |
| Workflow.Form.Read | 列可见模板（销售收款确认单可能不在可见列表里，已知 processCode 仍可查） |

列实例 `POST /v1.0/workflow/processes/instanceIds/query` 文档写明仅**企业内部应用**。new-api 应用虽显示 Client ID，原 AgentId 仍按内部应用拿 token，已实测可列、可读、可下。

## 端点

1. `POST /v1.0/oauth2/accessToken`
2. `POST /v1.0/workflow/processes/instanceIds/query`（窗口 ≤120 天）
3. `GET /v1.0/workflow/processInstances?processInstanceId=`
4. `POST /v1.0/workflow/processInstances/spaces/files/urls/download` → `downloadUri` 15 分钟

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
