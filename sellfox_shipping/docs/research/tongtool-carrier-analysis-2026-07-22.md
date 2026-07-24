---
okf: v0.1
type: Research
title: 通途 US 仓库实际承运商分析 — 路由规则数据基础
description: 从 EN 生产系统分析通途自发货订单，获取实际承运商分布、包裹尺寸数据，为路由规则设计提供数据依据
tags: [sellfox-shipping, carrier-analysis, tongtool, routing-engine, data-analysis]
timestamp: 2026-07-22
---

# 通途 US 仓库实际承运商分析

## 1. 背景

### 1.1 问题

赛狐系统中关于蜴国际等承运商的数据是**测试数据**（显示 "蜴国际-FedEx 占 89.3%"），与实际生产不符。需要从 **EN 生产系统 (ERPNext)** 查询通途 (Tongtool) 订单的真实承运商使用情况。

### 1.2 参考来源

- ChatGPT 分享链接分析（UPS/FedEx Zone 定价、四层路由引擎架构、Quote vs Cost 区分）
- [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — 赛狐尾程打单系统架构规划

## 2. 查找逻辑

### 2.1 系统

| 项目 | 值 |
|------|-----|
| 系统 | `https://erpnext.vilavi.cn`（生产） |
| Doctype | `Tongtool Order` |
| API 认证 | `Authorization: token <key>:<secret>` |
| 凭证来源 | `EN_API/.env` → `PROD_ERP_API_KEY` + `PROD_ERP_API_SECRET` |

### 2.2 过滤条件

```
1. order_status = "已发货"
2. order_type = "自发货"
3. despatch_complete_time >= "2026-04-01 00:00:00"
4. despatch_complete_time <= "2026-06-30 23:59:59"
5. warehouse_name LIKE "%CENTRADE%" OR warehouse_name LIKE "%DANEEY%"
```

### 2.3 排除条件

```
raw_data.platformCode IN ("WF", "OS", "PB")   # Wayfair, Overstock, Pottery Barn（平台物流）
raw_data.merchantCarrierShortname = "Tiktok物流"  # TikTok Shop
```

### 2.4 承运商提取

**仅从 raw_data JSON 提取 `merchantCarrierShortname`**，不回退到主表字段。

### 2.5 包裹尺寸

每个 SKU 从 `goodsInfo.tongToolGoodsInfoList[]` 提取：

| 字段 | 含义 |
|------|------|
| `packageLength` | 包裹长 (cm) |
| `packageWidth` | 包裹宽 (cm) |
| `packageHeight` | 包裹高 (cm) |
| `productWeight` | 重量 (g) |

### 2.6 多 SKU 合并算法

```
最终长 = max(所有SKU的packageLength)
最终宽 = max(所有SKU的packageWidth)
最终高 = sum(所有SKU的packageHeight)
```

例：SKU1=48×42.2×15, SKU2=76×48×18 → **合并后 76×48×33**

## 3. 分析结果

### 3.1 数据量

| 指标 | 数值 |
|------|------|
| CENTRADE 原始 | 6,124 |
| DANEEY 原始 | 8,292 |
| 去重合计 | 14,416 |
| 排除 WF/OS/PB | 4,747 |
| 排除 Tiktok物流 | 23 |
| **最终有效** | **9,646** |

### 3.2 承运商分布

| 排名 | 承运商 | 数量 | 占比 |
|------|--------|------|------|
| 1 | **VITE-Fedex** | 6,679 | **69.2%** |
| 2 | **M6180蜴国际** | 2,523 | **26.2%** |
| 3 | US-FedEx | 410 | 4.3% |
| 4 | CENTRADE(自营) | 19 | 0.2% |
| 5 | postPony | 15 | 0.2% |

### 3.3 仓库分布

| 仓库 | 数量 |
|------|------|
| CENTRADE | 4,957 |
| FZH-DANEEY-皮壳仓库 | 2,422 |
| FZH-DANEEY-退货产品仓 | 1,731 |
| FZH-DANEEY-半成品仓 | 312 |
| FZH-DANEEY-成品仓 | 224 |

### 3.4 承运商 × 仓库

| 承运商 | CENTRADE | DANEEY各仓 |
|--------|----------|-----------|
| VITE-Fedex | 2,737 | 3,942 |
| M6180蜴国际 | 1,788 | 735 |
| US-FedEx | 409 | 1 |

### 3.5 承运商 × 平台（路由规则核心依据）

| 平台 | 主承运商 | 备选 |
|------|---------|------|
| AMZCTRDUS | VITE(2,694) / 蜴国际(1,761) | US-FedEx(406) |
| AMZBAINAUS | VITE(2,170) | 蜴国际(185) |
| AMZDANEEYUS | VITE(385) / 蜴国际(237) | — |
| AMZRosoonUS | VITE(481) | 蜴国际(23) |
| AMZTOODDLYUS | VITE(365) | 蜴国际(115) |

### 3.6 包裹尺寸（9,633 SKU 合并后）

| 维度 | 中位数 | 平均 | 范围 |
|------|--------|------|------|
| 长(cm) | 57.5 | 59.7 | 5~162 |
| 宽(cm) | 48.0 | 42.9 | 5~75 |
| 高(cm) | **18.0** | 19.2 | 2~116 |
| **体积重(kg)** | **9.7** | 9.3 | 0~57.6 |

### 3.7 承运商 × 平均尺寸

| 承运商 | 数量 | 平均长 | 平均宽 | 平均高 | 平均体积重 |
|--------|------|--------|--------|--------|-----------|
| **蜴国际** | 2,518 | 50.4cm | 40.0cm | **14.5cm** | **5.62kg** |
| **VITE** | 6,671 | 63.8cm | 43.9cm | **21.2cm** | **10.71kg** |
| US-FedEx | 410 | 51.2cm | 44.4cm | 16.4cm | 8.30kg |

### 3.8 月度趋势

| 月份 | Top 承运商 |
|------|-----------|
| 4月 | VITE(1,815) > 蜴国际(380) > US-FedEx(76) |
| 5月 | VITE(2,134) > 蜴国际(473) > US-FedEx(80) |
| 6月 | VITE(2,717) > 蜴国际(1,669) > US-FedEx(254) |

## 4. 关键发现

1. **赛狐数据不可信**：fbmCost 全部为 0，承运商"蜴国际 89%"为测试数据
2. **实际承运商**：VITE 69.2%, 蜴国际 26.2%, US-FedEx 4.3%
3. **90%+ 按体积重计费**：中位数 9.7kg 体积重 vs 4.6kg 实际重
4. **平台→承运商强绑定**：WFUS→US-FedEx, OSTKUS→Overstock 等
5. **蜴国际扁平轻件**（14.5cm高, 5.62kg），**VITE高重件**（21.2cm高, 10.71kg）

## 5. 对路由规则的启示

- 初期直接比价（不设复杂评分公式）
- 蜴国际适合扁平轻件，VITE 适合高重件
- 先积累 Invoice 数据，后续再做 Expected Cost 预测

## 6. 分析脚本

`scripts/analyze_tongtool_carriers.py` — 分页拉取 + 过滤 + 分析
