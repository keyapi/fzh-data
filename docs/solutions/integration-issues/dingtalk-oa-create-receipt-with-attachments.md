---
okf: v0.1
type: Reference
title: 钉钉原生「销售收款确认单」可用 API 带附件发起
date: 2026-11-02
category: integration-issues
module: dingtalk_oa_approval
problem_type: integration_issue
component: tooling
severity: medium
applies_when:
  - "要用 API 替运营发起钉钉销售收款确认单"
  - "发起时报 Storage.UploadInfo.Read / Storage.File.Write / SignatureDoesNotMatch"
  - "已有 Workflow.Instance.Write 但仍交不上附件"
tags: [dingtalk, oa, approval, attachment, storage, workflow]
---

# 钉钉原生「销售收款确认单」可用 API 带附件发起

## Context

本模块原先只**读**原生 OA「销售收款确认单」（列实例、下附件、对照 NAS）。2026-11 第一次用同一套企业内部应用**发起**一张带 CSV 附件的单。读接口已经通，不代表写附件能通：下载走 `Workflow.Instance.Write`，上传要另开钉盘存储权限，OSS PUT 还不能用 Python `urllib` 默认头。

## Guidance（本学习沉淀的做法）

1. **发起接口**（官方 `POST /v1.0/workflow/processInstances`）：`originatorUserId` + `processCode` + `deptId` + `formComponentValues`。模板码见 `dingtalk/dingtalk_oa_approval/AGENT_HANDOFF.md`。明细是 `TableField`，`value` 为二维 JSON 数组字符串 `[[{"name":"选择平台","value":"新平台"}, …]]`；附件是 `DDAttachment`，`value` 为 `[{spaceId,fileId,fileName,fileSize,fileType}, …]` 的 JSON 数组字符串。
2. **带附件的三步上传**（先授权空间，再 OSS，再 commit）：
   - `POST /v1.0/workflow/processInstances/spaces/infos/query`（`userId` + `agentId`）→ 审批钉盘 `spaceId`
   - `POST /v1.0/storage/spaces/{spaceId}/files/uploadInfos/query?unionId=` → `HEADER_SIGNATURE` 的 URL + 请求头；**PUT 只带这些签名头**
   - `POST /v1.0/storage/spaces/{spaceId}/files/commit?unionId=` → `dentry.id` 即 `fileId`
3. **权限要分步开、每开一次发布新版本**。已有 `Workflow.Instance.Write` 只能读实例、拿 `spaceId`。实测缺项会 403 并给出申请链：
   - `Storage.UploadInfo.Read`（拿上传凭证）
   - `Storage.File.Write`（commit 入库）
   开完必须**发布新版本**，旧 token 仍会 403。
4. **unionId**：新通讯录 `GET /v1.0/contact/users/{userId}` 可能 404；旧接口 `POST https://oapi.dingtalk.com/topapi/v2/user/get?access_token=` 仍能返回 `unionid` / `dept_id_list`。存储上传必须用 unionId，不能用 OA 的 originatorUserId 顶替。
5. **OSS PUT 不要走 `urllib.request`**。带 `data=` 时它会擅自加 `Content-Type: application/x-www-form-urlencoded`，OSS 回 `SignatureDoesNotMatch`。用 `requests.Session()`，`sess.headers.clear()` 后再 PUT，只转发钉钉返回的签名头。
6. **发起前确认上一张同内容单的状态**。已撤销是 `TERMINATED`。上一张仍是 `RUNNING` 就不要再发一张。
7. **不要把计算控件当必填手填项**。模板里「账期收款额 / 占比 / 回款率」是 `CalculateField`；手填「销售额」等金额源字段即可。平台相关的一长串账户下拉在 UI 里按「选择平台」显隐，API 只填实际用到的那几个（与上一张已通过的单对齐）。

## Why This Matters

- 读附件权限面 ≠ 发起带附件。缺存储两个 scope 时，会在 PUT 已成功之后才在 commit 上 403，看起来像「文件传上去了但单发不出去」。
- `urllib` 签名失败会浪费在 OSS 层排查，其实是客户端自己改了头。
- 同一套 new-api 应用能发原生 OA 单，就不必再开浏览器代填；但仍建议以后把 OA 读写拆到专用内部应用（权限面过大的旧结论仍然成立）。

## When to Apply

- 运营说「用 API 交销售收款确认单 / 权限不够告诉我开什么」。
- 上传附件 403 或 OSS `SignatureDoesNotMatch`。
- 要代发前先核对上一张是否已撤销。

## Examples

权限不够时的典型顺序（都要发布新版本后再测下一步）：

1. `Storage.UploadInfo.Read` 未开 → uploadInfos 403
2. 开了读、未开写 → PUT 200，commit 403 `Storage.File.Write`
3. `urllib` PUT → 403 `SignatureDoesNotMatch`
4. 上一张未撤 → 会并发生成第二张 `RUNNING` 单

表单控件名（与模板一致）：收款账户明细表 `TableField-K2K6QXPZ`；账期明细 `DDAttachment-K2K7DF54`。

## Related

- 模块交接：`dingtalk/dingtalk_oa_approval/AGENT_HANDOFF.md`
- API 参考：`dingtalk/dingtalk_oa_approval/docs/reference/oa-attachment-api.md`
- PB 每月交什么（日行 + 日 CSV + 月合并 CSV 垫底，不交月合计行）：`docs/solutions/conventions/pb-dingtalk-receipt-monthly-package.md`
- 摘单后 CSV 丢表头（会让下游少读一张票）：PR #297 `docs/solutions/workflow-issues/pb-invoice-csv-header-loss.md`（合并前在该分支）
