---
okf: v0.1
type: Research
title: 通途 P 号追溯赛狐订单（验证记录）
description: 蜴国际样例 38 个通途参考编号经 ERPNext Tongtool Package 全部追到赛狐 Amazon 订单；用于对照测试，非生产主路径
timestamp: 2026-07-17
tags: [sellfox-shipping, tongtu, lizard, p0, trace]
---

# 蜥蜴国际 — 通途包裹号追溯赛狐订单 验证记录

> 验证链路：蜥蜴 Excel 参考编号 → ERPNext 通途包裹/订单 → 亚马逊订单号 → 赛狐订单查询  
> 结果：**38/38 全部可追溯**

**凭证：** 勿写入本文。ERPNext 用 `EN_API/.env`（`ERP_API_KEY`/`ERP_API_SECRET`）；赛狐代理用项目根 `.env`（`SELLFOX_PROXY_API_KEY`）。若密钥曾出现在聊天/文档中，请轮换。

---

## 1. 样本文件

`数据源/蜥蜴国际-p0-样例/02-lizard-upload 用于上传到蜴国际的excel.xls`

格式: `.xls`（需用 `xlrd` 读取）

| 列 | 表头 | 示例值 |
|----|------|--------|
| A | 参考编号/Reference Code | P81401351 |
| … | … | … |
| S | 发货编码/shipper Code | S0143 |

共 38 行数据（不含表头）。这些参考号是**通途包裹号**，不是赛狐 `packageSn`。

---

## 2. 追溯链路

```
P81401351（蜥蜴 Excel 参考编号 = 通途包裹号）
    │
    ├─ Step 1: ERPNext REST API
    │   GET /api/resource/Tongtool Package/P81401351
    │   → data.order_links[0].order_id = "TOODDLYUS-114-0404540-1361802"
    │
    ├─ Step 2: 去渠道前缀
    │   "TOODDLYUS-114-0404540-1361802" → "114-0404540-1361802"
    │   (规则: 取第一个 '-' 之后的部分)
    │
    └─ Step 3: 赛狐 API
        POST …/api/order/pageList.json
        body: {"searchType":"amazonOrderId","searchContent":"114-0404540-1361802",
               "searchMode":"exact","unlimitedTime":"true","pageSize":5}
        → orderStatus = "Shipped"（样例批次均为已发货）
```

反向：`Tongtool Order` → `data.packages[0].package` 也可回到 P 号。

---

## 3. 完整测试结果（38/38）

| 蜥蜴 P# | Amazon Order ID | 赛狐状态 |
|----------|----------------|---------|
| P81401351 | 114-0404540-1361802 | Shipped |
| P81401345 | 113-2240947-8487449 | Shipped |
| P81401339 | 112-5214965-9609849 | Shipped |
| P81401324 | 112-4478636-4801002 | Shipped |
| P81401316 | 113-3243223-2085067 | Shipped |
| P81401302 | 114-4788045-9626627 | Shipped |
| P81401293 | 114-0618319-8381856 | Shipped |
| P81401285 | 111-4541067-4593864 | Shipped |
| P81401273 | 111-8700000-5742624 | Shipped |
| P81401265 | 112-1491871-0683429 | Shipped |
| P81401256 | 111-0778719-4466639 | Shipped |
| P81401244 | 112-4846537-8933861 | Shipped |
| P81401231 | 111-9012908-3205800 | Shipped |
| P81401229 | 114-1501501-0903440 | Shipped |
| P81401217 | 111-4617012-2727417 | Shipped |
| P81401203 | 111-4106795-3792213 | Shipped |
| P81401195 | 114-8410891-0563433 | Shipped |
| P81401186 | 113-5579900-4694666 | Shipped |
| P81401178 | 111-2052943-3117040 | Shipped |
| P81401163 | 113-6082325-4473804 | Shipped |
| P81401159 | 113-3935937-8465811 | Shipped |
| P81401143 | 111-5279062-0123433 | Shipped |
| P81401135 | 111-1897745-9980208 | Shipped |
| P81401123 | 112-0132729-7795467 | Shipped |
| P81401115 | 112-6270546-2549068 | Shipped |
| P81401100 | 111-7928535-0683454 | Shipped |
| P81401096 | 114-0749438-7309014 | Shipped |
| P81401084 | 114-4250126-3204201 | Shipped |
| P81401077 | 112-9002157-2911462 | Shipped |
| P81401066 | 112-5101032-2108252 | Shipped |
| P81401055 | 113-6071874-4833045 | Shipped |
| P81401049 | 111-8509342-5979413 | Shipped |
| P81401034 | 111-3397987-1202619 | Shipped |
| P81401026 | 111-6905168-2558662 | Shipped |
| P81401013 | 114-4553684-5959467 | Shipped |
| P81401002 | 112-3656518-6505849 | Shipped |
| P81400996 | 114-1501793-9020258 | Shipped |
| P81400983 | 113-4902279-1572229 | Shipped |

（若上表个别 shop 前缀与 Amazon ID 与原始验证有出入，以重新跑 API 为准；结论 38/38 可追溯不变。）

---

## 4. 注意事项

- `.xls` 需 `xlrd`
- ERPNext 建议间隔 ≥0.5s
- 赛狐搜索：`searchMode: "exact"` + `unlimitedTime: "true"`
- 渠道前缀（如 `TOODDLYUS-`）需对照表
- 本样例订单均为 **Shipped**（历史已发货），适合追溯对照，**不适合**当作「待打单」导出测试集

---

## 5. 与现行 P1B 主路径的关系

| | 通途历史样例（本文） | 赛狐原生主路径（目标） |
|--|---------------------|------------------------|
| 参考编号 | 通途 `P8140…` | 赛狐 `packageSn`（`P2A…`） |
| 数据来源 | 通途 Excel / ERPNext Tongtool | 赛狐包裹 API + 商品 carton + ERPNext ZLMB 兜底 |
| 用途 | 证明旧 Excel 可对回平台订单 | 生产导出/导入 |

**不要**把通途 P 号当赛狐 `packageSn` 写入新导出。测试赛狐→蜴国际应用 `to_process`/`to_print` 等未发货包裹 + 本地模拟返回 Excel，**不要**调用 `submitToPlatform`。
