---
okf: v0.1
type: Research
title: 面单异步回传与 Webhook 口径（VITE / 蜴国际）
description: 用户确认的后台 Hook URL 现状、本地部署约束，以及承运商 IT 给出的轮询建议；对照本仓测试环境真测
timestamp: 2026-07-17
tags: [sellfox-shipping, vite, lizard, webhook, async-label]
---

# 面单异步回传与 Webhook 口径

## 用户确认事实

1. **VITE** 测试系统后台有 **API Hook URL** 字段，目前为空；生产系统估计也有同类配置（见 `vite-api/docs/webhooks/setup-guide.md`：EEVEE → 组织管理）。
2. **蜴国际** 生产系统后台也有 **Webhook 地址** 配置项。
3. 本阶段部署形态是 **本地测试**，没有稳定公网回调入口。

## 蜴国际 IT 原文（2026-07-17 用户转发）

> 4、因跨境网络影响面单及跟踪号都是异步返回，创建订单成功后调用面单及跟踪号查询接口获取面单(建议30秒请求一次)

含义：

- `createOrder` 成功 ≠ 已有面单 / 追踪号
- 必须随后调查询接口（文档侧多为 `getLabel`）
- **建议间隔约 30 秒/次**（跨境延迟；非即时）

## 与本仓 VITE 测试真测对照

| 项 | 观察 |
|----|------|
| createShipment | 同步返回 `pending` + `orderId`，虚拟余额立即扣费 |
| getLabel | 短时（~45s）可一直 `pending`；事后轮询可达 `OK` + tracking + PDF url |
| 实践 | 本地默认 **轮询**；超时宜按分钟级窗口，间隔可先用 5–30s |

VITE 官方亦支持 webhook（标签完成后推送），但 Hook URL 为空时只能轮询。见 [vite-api webhooks](../../../vite-api/docs/webhooks/setup-guide.md)。

## 架构口径（本地阶段）

| 路径 | 本地测试 | 将来公网部署 |
|------|----------|--------------|
| **轮询 getLabel** | **主路径**（VITE / 蜴国际 API 均适用） | 仍作兜底 / 对账 |
| **Webhook / API Hook** | **暂不填、不实现接收端**（无公网 URL、无订阅确认环境） | 可选加速「标签就绪」；须验签名、重复通知、乱序 |

**禁止假设：** Hook URL 填了就会在本机自动收到推送。本地开发若要用 webhook，需要隧道（如 ngrok）+ 公网 HTTPS + 订阅确认流程——当前不在范围内。

## 实现提示（未写代码）

- Adapter 层：`create` → 持久化 `orderId`/`requestId` → 后台/任务按间隔轮询至终态（`OK` / `failed` / `canceled`）或超时转人工。
- 蜴国际：优先采用 IT 建议的 **30s** 间隔；VITE 测试环境可先 5–30s，总窗口 ≥2–3 分钟（本仓 §21 真测）。
- Excel 路径（蜴国际现行）：人机异步，不依赖 webhook。
- 与赛狐 `submitToPlatform` 解耦：仅在本地已拿到可靠 tracking 后再走 P1C 回写。

## 相关

- [lizard-api-vs-excel-2026-07-17.md](lizard-api-vs-excel-2026-07-17.md)
- [session-progress-2026-07-16.md](session-progress-2026-07-16.md) §20–21
- `vite-api/docs/webhooks/`（main / 已合入模块）
