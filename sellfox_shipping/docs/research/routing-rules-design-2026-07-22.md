---
okf: v0.1
type: Research
title: 路由规则设计方案 — 基于通途真实数据
description: 基于通途 9,646 条真实数据 + ChatGPT UPS/FedEx Zone 分析，设计 5 层决策流路由引擎
tags: [sellfox-shipping, routing-engine, carrier-rules, architecture]
timestamp: 2026-07-22
---

# 路由规则设计方案

## 1. 参考来源

- ChatGPT UPS/FedEx Zone 分析：Zone 定价、四层路由架构、Quote vs Cost、Expected Cost
- 通途真实数据：9,646 条自发货订单，确认承运商 VITE 69.2%、蜴国际 26.2%
- 赛狐数据验证：fbmCost 为空，不可用
- [tongtool-carrier-analysis-2026-07-22.md](tongtool-carrier-analysis-2026-07-22.md)

## 2. 设计原则

1. **分层决策**：仓选择 → 承运人选择 → 服务选择 → 评分 → 执行
2. **可扩展**：新增承运人只加 Provider，不改核心算法
3. **数据驱动**：先用规则，用历史 Invoice 数据逐步优化
4. **可观测**：每次决策记录完整上下文（输入 + 输出 + 选择理由）

## 3. 5 层决策流

### 第 1 层：定仓（Warehouse Routing）

```
订单 → 前置过滤：
  ① 账号绑定 → 某些Amazon店铺固定走指定仓
     WFUS/OSTK → DANEEY（→ 这类走平台物流，不走自发货路由）
     AMZBAINAUS → DANEEY
     AMZCTRDUS → CENTRADE
  ② SKU绑定 → 特定SKU只能从某仓发
  ③ 库存过滤 → 仓没库存则切换
  ④ 如果以上都没命中 → NJ和TX都是候选仓
```

### 第 2 层：定承运人（Carrier Routing）

按收货地址国家 + 平台分流：

| 平台 | 首选承运商 |
|------|-----------|
| AMZCTRDUS | VITE / 蜴国际 |
| AMZBAINAUS | VITE |
| AMZDANEEYUS | VITE / 蜴国际 |
| WFUS / OSTKUS / PotteryBarnUS | 平台物流（不走自发货路由） |

### 第 3 层：选服务（Service Selection）

| 条件 | 推荐 |
|------|------|
| 住宅地址 | FedEx Home Delivery |
| 商业地址 | FedEx Ground |
| 超尺寸（体积重>30kg或长>120cm） | 蜴国际 |
| 超重（>50lbs/22.5kg） | FedEx Ground |
| 轻小件（<1kg） | USPS |

### 第 4 层：比价（Scoring）

初期直接比价：**谁报价低就用谁**。

数据积累后（需要 Invoice 数据）再做：
```
Expected Cost = Rate API 报价 + Carrier历史偏差率 + SKU反弹风险
```

### 第 5 层：执行

```
选择 → CreateShipment → Label + Tracking → SubmitToPlatform → 回写赛狐
```

## 4. 规则数据结构

```yaml
warehouse_rules:
  - name: "Amazon账号绑定仓"
    priority: 10
    conditions:
      shop_name: ["AMZBAINAUS", "AMZRosoonUS"]
    action:
      warehouse: "DANEEY"

  - name: "平台物流排除"
    priority: 5
    conditions:
      sale_account: ["WFUS", "OSTKUS", "PotteryBarnUS"]
    action:
      skip_routing: true

carrier_rules:
  - name: "美国主流"
    priority: 10
    conditions:
      destination_country: "US"
    candidate_carriers:
      - carrier: "lizard"
      - carrier: "vite"
      - carrier: "fedex_direct"

service_rules:
  - name: "住宅地址 → FedEx Home"
    conditions:
      address_type: "Residential"
    action:
      preferred_service: "FEDEX_HOME_DELIVERY"

scoring:
  default_weights:
    price_weight: 1.0  # 初期只看价格
```

## 5. 与 ChatGPT 分析的差异

| ChatGPT 建议 | 实际结论 | 原因 |
|-------------|---------|------|
| Zone Matrix 是基础 | **Zone 是中间变量，非必需** | Rate API 直接返回价格，Zone 可后续优化 |
| 四层路由架构 | ✅ 采纳，但简化 | 初期取消评分公式，直接比价 |
| Expected Cost | **数据积累后再做** | 需要 Invoice 数据（几周~几个月） |
| SKU Risk Profile | **暂不做** | 需要历史回弹费数据 |
| Carrier Profile | **暂不做** | 需要 Invoice 数据 |

## 6. 集成方案

新增 `routing/` 目录，核心类 `RoutingEngine` 插入现有 `submission_service.py` 的 `prepare_intents_for_package` 之前。

```
赛狐包裹 → RoutingEngine.decide() → CreateShipment → SubmitToPlatform
```
