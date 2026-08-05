---
okf: v0.1
type: Solution
title: ChatGPT UPS/FedEx Zone 分析与路由引擎架构参考
description: 同事分享的 ChatGPT 分析链接内容摘要，包含 UPS/FedEx Zone 定价、四层路由架构、Quote vs Cost 等关键概念
tags: [sellfox-shipping, chatgpt-reference, carrier-analysis, routing-engine]
timestamp: 2026-07-22
source: https://chatgpt.com/share/6a5ef1f2-06f8-83eb-86f6-af9abff5041a
---

# ChatGPT UPS/FedEx 分析参考

## 来源

同事分享的 ChatGPT 分析链接，内容已保存至桌面 `UPS FedEx.md`。

## 核心概念

### UPS/FedEx Zone 定价

- Zone 2~8：美国大陆48州运输分区
- Zone = f(发件ZIP3, 收件ZIP3)：由邮编查表得出
- 同地址不同仓 → Zone 完全不同（NJ→LA=Z8, TX→LA=Z4）

### 四层路由架构

```
赛狐 OMS → 自研路由引擎 → 尾程平台 → Carrier
```

1. 获取订单
2. 判断发货仓库
3. 判断物流商
4. 获取各物流报价
5. 选择最优方案
6. 创建面单
7. 回写赛狐

### Quote ≠ Cost

| 概念 | 说明 |
|------|------|
| Quote | Rate API 返回的预估价格 |
| Invoice Cost | 几周后物流商发来的真实账单 |
| 反弹费 | 真空压缩产品运输中涨包，被收取额外费用 |
| Variance = Invoice - Quote | 差异分析 |

### Expected Cost

```
Expected Cost = Quote + Carrier历史偏差 + SKU反弹风险
```

例：UPS Quote $12, 但历史补收 +25% → Expected Cost $15
FedEx Quote $13.5, 但历史补收 +6% → Expected Cost $14.3  
→ 选 FedEx（即使 quote 更贵）

## 本项目应用情况

| 概念 | 状态 |
|------|------|
| Zone 矩阵 | 暂不实现（Rate API 直接返回价格） |
| 四层路由架构 | ✅ 采纳（简化版） |
| Rate API 比价 | 待实现（需对接各承运商 API） |
| Expected Cost | 待 Invoice 数据积累后实现 |
| Carrier Profile | 待 Invoice 数据积累后实现 |
| SKU Risk | 待数据积累后实现 |
