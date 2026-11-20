---
okf: v0.1
type: Reference
title: 钉钉 aflow 导出工具 UI 漂移：表单改名与日期控件选择器失效
date: 2026-11-19
category: developer-experience
module: web_automation
problem_type: developer_experience
component: tooling
severity: medium
symptoms:
  - "dispatch --check 是 READY，但实跑报 FAILURE_CODE=FORM_NOT_FOUND"
  - "登录成功、组织已选，卡在等待 .ant-cascader-menu :text-is(\"销售收款确认单\")"
  - "表单能选后，又卡在等待 [title=\"2026-09-03\"] 的日期面板"
root_cause: ui_drift
resolution_type: workaround_plus_code_fix
tags: [dingtalk, aflow, web-automation, playwright, ui-drift]
---

# 钉钉 aflow 导出工具 UI 漂移：表单改名与日期控件选择器失效

## Problem

`web_automation/legacy-compatible/dingtalk_aflow_receipt.py` 的 `--mode excel` 在 2026-11
实跑时两处失败：

1. 表单名称级联找不到「销售收款确认单」——钉钉里该表单已改名为 **「收款确认单」**
   （列表里还有「新平台收款确认单」，容易误匹配）。
2. 日期 RangePicker 的 `[title="YYYY-MM-DD"]` 与 `.dtd-picker-header-view` 不再匹配，
   日历面板不会翻到目标月，最终超时。

注意：`dispatch --check` 只检查脚本存在/环境，**不会发现 DOM 选择器失效**，所以它仍是 READY。

## Symptoms

```
[错误] 选表单失败: Locator.click: Timeout 30000ms exceeded.
      waiting for locator(".ant-cascader-menu :text-is(\"销售收款确认单\")")
FAILURE_CODE=FORM_NOT_FOUND
```
```
[错误] 设置发起时间失败: Locator.click: Timeout 30000ms exceeded.
      waiting for locator("[title=\"2026-09-03\"]")
FAILURE_CODE=INVALID_ARGUMENT
```

## What Didn't Work

- 重新扫码登录：登录本身是成功的（`已勾选自动登录…已选择组织：方州汇国际`），问题在选择器。
- 继续用默认 `--form`：租户已改名，必须显式传新名。

## Solution

1. **表单名**：显式传 `--form "收款确认单"`；`select_form` 增加容错——精确匹配失败时，
   先 dump 级联菜单项文本，再按“包含”匹配。修复见
   `web_automation/legacy-compatible/dingtalk_aflow_receipt.py`（`select_form`）。
2. **绕过日期控件**（附件下载不需要重新导出）：
   - 从已有宽窗导出 xlsx 中用 openpyxl **只保留目标审批的行**（保留两行表头/超链接）；
   - 直接跑 `--mode attachments --from-xlsx <裁剪表> --all-originators --fields 账期明细`，
     按 `数据id` 打开实例详情下载附件。
   - 本次就用这个办法成功下载了离职发起人的附件。

## Why This Works

附件模式的入口是导出表里的 `数据id`，不依赖表单名称与日期筛选；把导出表裁到目标行后，
浏览器只需打开实例详情并点击附件，绕开了两个失效的选择器。

## Prevention / 下一步

- 每月导出前先跑 `dispatch.py dingtalk.aflow.receipt.export --check`，再实跑一次小窗口；
  `--check` 通过不代表 UI 选择器可用。
- **待修**：日期 RangePicker 选择器（需要 dump 当前 DOM 的 `.dtd-*` 类名）；
  表单名建议做成配置并在启动时列出候选，而不是硬编码默认值。
- 失败时优先 dump 选择器命中情况，不要把超时当成“没登录”。

## Related

- `web_automation/legacy-compatible/dingtalk_aflow_receipt.py`
- `web_automation/capabilities.yaml`（`dingtalk.aflow.receipt.export` / `.attachments`）
- `docs/solutions/workflow-issues/amazon-period-cross-bucket-attachment-misfile.md`
