---
okf: v0.1
type: Reference
title: 能力矩阵与路由合同
description: 版本化能力矩阵解释：四种 mode、允许/禁止回退、验证与最近验证日期
tags: [capability-matrix, routing, api, browser, fallback]
---

# 能力矩阵与路由合同

定义在 `web_automation/capabilities.yaml`，`runtime.py` 读取，`dispatch.py` 执行。矩阵每个动作（`platform.action`）声明 mode、risk、通道、回退规则与验证方式。**弱模型只读结果，不自行推理路由策略。**

## 四种 mode

| mode | 含义 |
|------|------|
| `API_ONLY` | 只用正式 API，无浏览器路径 |
| `API_FIRST_BROWSER_FALLBACK` | 先 API，仅命中允许回退错误时走浏览器 |
| `BROWSER_ONLY` | 只能浏览器（通途主流程、赛狐未覆盖写流程） |
| `MANUAL_CONFIRM` | 写操作：必须先返回 `NEED_USER_CONFIRMATION`，确认范围后才执行 |

## 回退纪律

- **禁止回退错误**（认证/权限/参数/业务校验）：命中即 `BLOCKED`，绝不静默掩盖。
- **允许回退错误**（端点缺失/不支持/服务不可用）：仅当该动作在矩阵中显式列出时才允许。
- 旧脚本只返回普通非零码时统一映射 `UNCLASSIFIED_FAILURE` → `BLOCKED`，不猜测后回退。

## 合同稳定性

- `contract: ui` — 依赖页面 DOM，赛狐/通途改版可能失效，需重新探路。
- `contract: private-cookie-api` — `sellfox_auto_export.py --api` / `sellfox_restock_api.py`
  依赖浏览器持久化 cookie 调私有 HTTP 接口，**不是**正式 Sellfox OpenAPI（`SELLFOX_API/`）。
  二者合同稳定性不同，不可混用、不可互称。

## 最近验证日期

每次成功跑通某动作后，更新对应 `last_verified: "YYYY-MM-DD"` 并提交；矩阵列与真实脚本不一致时以脚本为准并同步矩阵。

## 当前动作

| task | mode | 通道 | 风险 |
|------|------|------|------|
| tongtu.stock.export | BROWSER_ONLY | browser | read |
| tongtu.sales.export | BROWSER_ONLY | browser | read |
| sellfox.stock.export | API_FIRST_BROWSER_FALLBACK | api→browser | read |
| sellfox.other-inbound.import | MANUAL_CONFIRM | browser | write |
| sellfox.other-outbound.import | MANUAL_CONFIRM | browser | write |
| sellfox.restock.import | MANUAL_CONFIRM | browser | write |
| web.generic.explore | BROWSER_ONLY | mcp | interactive |
