---
okf: v0.1
type: Reference
title: PB 弧形海绵带圆柱颈枕 — 报价历史与旧/新通途 SKU 切换
tags: [pb, orders, sku-migration, quotation, inventorive-sleep, tongtu, arc-pillow]
timestamp: 2026-11-06
---

# PB 弧形海绵带圆柱颈枕：报价历史与 SKU 切换

> 适用：Tracy Miller / PB「Inventive Sleep: Adjustable Orthopedic Support Pillow」。
> 2026-11 周一部分颜色上线；PB 料号不变，订单仍带 2024 年登记的旧通途 SKU，
> 而旧 SKU 已无库存，有货的是 2025-07-15 建档的改版 SKU。
> 转换工具：[`arc_sku_migration.py`](../../arc_sku_migration.py)；
> 映射数据：[`sku_maps/pb_arc_foam_cylinder.json`](../../sku_maps/pb_arc_foam_cylinder.json)。

## 1. 两代产品对照

| | 旧版（PB 已登记） | 新版（当前有货） |
|---|---|---|
| 通途品名 | 带圆柱弧形海绵靠枕 涤麻 50×30×65cm | 圆柱颈枕弧形海绵靠枕 涤麻 50×22×55cm |
| 通途 SKU | 灰 `TT0031058K0062965` / 白 `TT0031059K0062966` | 灰 `TT0312672K0064328` / 象牙白 `TT0312673K0064329` / 深蓝 `TT0312674K0064330` |
| 通途建档 | 2023-08-04 | 2025-07-15 |
| EN 产品 | `KS0165` | `KS0470` |
| PB 品名 | Inventive Sleep: Adjustable Orthopedic Support Pillow | 本地无记录 |
| PB SKU | `5938375`（Grey）/ `4020032`（Ivory） | 本地无记录 |

证据：

- 旧 SKU：`D:\Work\美国\Tracy Miller\产品报价\SKU Worksheet_PB_Adjustable Orthopedic Wedge 20241008 filled.xlsx`，`SPECIFICATIONS` 表 V3/V4。
- 通途档案：直连 `goodsQuery` 实测（2026-11-06），5 个 SKU `productStatus=1`。
- EN 变体：`KS0165-DM-65-GREY/WHITE`、`KS0470-DM-50x22x55-GREY/IVORY/DEEPBLUE`。

## 2. 报价时间线

| 日期 | 文件 | 内容 |
|---|---|---|
| 2024-03-08 | `报价 5个新品 20240308.xlsx` | 涤麻白色，累积成本 ¥184.86；报价 **$62.5**，表内注「Tracy 嫌太高」 |
| 2024-04-19 | `井 方州汇国际 - 美国价格体系 20240419.xlsx` | 零售 $69.99、Dropship **$43.3938**、Wholesale **$33.3938**；涤麻与菱形复合绒布同价 |
| 2024-04-19 后 | `报价 成本 利润 20240314 5个新品.xlsx` `P13` | PB 按 **$43.3938** 供货 |
| 2026-08-28 | `打折活动Promotion\Christine download Centrade retail and costs 20260828_filled_for_Tracy.xlsx` | PB SKU 5938375/4020032：零售 $99、供货 **$43.39** |

结论：

- **价格改过一次**：$62.5 → $43.3938，对应旧版 50×30×65。
- **只报过白色、灰色两个颜色**。老 SKU 没有深蓝；全部本地文件中深蓝均无报价记录。
- **改版后（50×22×55）没有任何本地书面报价**：2026-01-22 最后修改的
  `产品报价\弧形海绵带圆柱 床楔形枕头 产品信息.xlsx` 仍用旧 SKU、旧尺寸、$43.3938；
  2026-08-28 PB 价格表也仍是旧 PB 料号。

## 3. 当前库存（2026-11-06，美中-FZH-DANEEY）

| SKU | 颜色 | 可用 | 说明 |
|---|---|---:|---|
| `TT0312672K0064328` | 灰色 | 42 | 新，可发 |
| `TT0312673K0064329` | 象牙白色 | 22 | 新，可发 |
| `TT0312674K0064330` | 深蓝色 | 32 | 新，但未报价/未登记 PB |
| `TT0031058K0062965` | Grey | 0 | 旧 |
| `TT0031059K0062966` | Ivory | 0 | 旧 |

复跑：`uv run python pb_orders/arc_sku_migration.py status`

## 4. 颜色映射与「写反」纠正

2025-07-31 的 `SKU Mapping_PB Inventive Sleep_Orth Plw_Gap Plw Tracy邮件20250731好消息.xlsx`
把两个旧 SKU 写反了：

- 该文件：`TT0031059=Grey`、`TT0031058=Ivory`
- 2024 filled worksheet、通途品名、EN 变体三处一致：`TT0031059=白色`、`TT0031058=灰色`

以三处一致者为准：

| PB SKU | PB 颜色 | 旧通途 SKU | 新通途 SKU |
|---|---|---|---|
| `5938375` | Grey | `TT0031058K0062965` | `TT0312672K0064328` |
| `4020032` | Ivory | `TT0031059K0062966` | `TT0312673K0064329` |

`arc_sku_migration.py` 会用 `Buyers Catalog or Stock Keeping #` 与 `Vendor Style` 做交叉校验；
一旦 PB 料号配错旧 SKU（例如 5938375 配了 TT0031059），直接判定冲突并停止。

深蓝 `TT0312674K0064330` 没有旧 SKU、没有 PB 料号、没有本地报价记录，列为 `unconfirmed`；
任何转换遇到它都默认非零退出，必须人工确认。

## 5. Web 服务（https://api.vilavi.cn/pb/）行为

- 页面顶部**常驻提示**：说明旧→新 SKU 自动转换、PB 料号校验、深蓝会中止。
- 出件任务默认开启 `JobOptions.sku_migration=True`：
  - 读 SPS 订单 CSV，遇到旧 SKU 自动改写为新 SKU，再进入原有通途 xlsx / 标签 / 背贴流程；
  - 转换后的 CSV 作为产物 `转换后订单 CSV（新 SKU）` 提供下载，便于审计；
  - 任务报告新增「SKU 自动转换」区块，列出每个旧→新 SKU 的转换行数。
- **PB 料号交叉校验**：`Buyers Catalog or Stock Keeping #` 必须与 `Vendor Style` 匹配。
  例如 PB `5938375` 只能配 `TT0031058K0062965` 或 `TT0312672K0064328`；
  配成 `TT0031059K0062966` 会直接判冲突。
- 冲突、深蓝、未登记的菱形绒布 SKU：任务**失败并停止出件**，页面显示具体行号与原因；
  不会生成标签/通途 xlsx。
- 断货清单与库存预检支持**旧/新 SKU 互为别名**：断货清单写新 SKU 也能命中订单里的旧 SKU，
  反之亦然。
- 部署：Web 与 worker 是两个容器，改完需在 `/opt/pb-orders` 重新
  `docker compose build && docker compose up -d`；只重启 Web 不会更新 worker。

## 6. 周一 Runbook

1. 从 SPS 导出当天 `checked0stock order ...csv`。
2. `uv run python pb_orders/arc_sku_migration.py status`
   确认新 SKU 有货、旧 SKU 为 0。
3. `uv run python pb_orders/arc_sku_migration.py map-order --csv "<原CSV>" --out "<..._新SKU.csv>"`
   - 默认遇到深蓝/冲突会停止且不写文件；确认后才可加 `--allow-unmapped`。
4. 用转换后的 CSV 跑现有流程：
   `run_stock_check.py --csv <新CSV>` → `run_pb_orders.py --csv <新CSV>`。
   下游通途导入 xlsx、标签、背贴会自然使用新 SKU；PB 侧 ASN/invoice 仍用 PB 料号，不受影响。
5. 出件前确认 Google Sheet `US SKU Name` 已包含 3 个新 SKU（背贴名称来源）。
   本机当前无 `us_sku_name_cache.csv`，且 Google API 直连不通，需提前预热或连代理。

## 7. 待确认（业务）

1. 周一实际上线颜色：是否只有灰/象牙白；深蓝是否已报价并被接受。
2. 改版后供货价是否仍为 $43.39（本地无书面记录）。
3. PB SPS 后台 Vendor Part Number 是否仍为旧 SKU；长期是否由 Diane 改为新 SKU。
4. 2025-07-31 映射表的旧 SKU/颜色写反，是否同步更正给 PB。

## 8. 部署记录（2026-11-06）

- 服务器：`sh-erpnext-test`（8.133.254.66），部署目录 `/opt/pb-orders`。
- 服务器上的 `service.py / repository.py / tasks.py` 比本分支新（已有 API Key、幂等键、
  订单号占用登记）。本次**没有整文件覆盖**，而是先把目标文件行尾归一为 LF，再用
  `patch -p1` 只叠加本功能；`stock_precheck.py / style.css / 三个模板` 与基线一致，直接打补丁。
- 新增 `arc_sku_migration.py` 与 `sku_maps/pb_arc_foam_cylinder.json` 已上传。
- `docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
  + `docker compose up -d`，web/worker 均已重建并 healthy。
- 服务器 `/opt/pb-orders/pb_orders/data/us_sku_name_cache.csv` 已追加三个新 SKU 的中/西语名
  （原文件已备份为 `us_sku_name_cache.csv.bak-*`）。
- **遗留**：缓存来源 Google Sheet `US SKU Name` 仍需补这三行；否则下次从 Sheet 刷新缓存会覆盖掉。

## 8. 历史事实

PB 从未订过此品：1689 个历史订单 CSV 与所有 open order 报告均无 `5938375/4020032`。
因此没有真实订单可以反推颜色映射，上线首单必须按本文件的交叉校验走。
