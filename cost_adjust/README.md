# cost_adjust — 赛狐成本补录单导入（改仓库/单据维度的采购成本）

按「仓库+SKU」或「单据+SKU」修正**已入库**库存的采购成本，走赛狐原生「成本补录单」，
不需要清零重入。

## 快速运行

```bash
cd cost_adjust

# 0) 先定位：这个 SKU 的库存来自哪些单据（哪张备货单还有货）
uv run --project ../web_automation python probe_batches.py KS0248-DM-60-WHITE

# 1) 生成导入文件
uv run python build_saihu_cost_adjust.py               # 生成导入文件
uv run python build_saihu_cost_adjust.py --dry-run     # 只看对照表，不生成文件
```

## 两条写入路径

| | A. 纯 API（`sellfox_cost_adjust_api.py`） | B. 导入 xlsx（`build_saihu_cost_adjust.py` + UI） |
|---|---|---|
| 适用 | **海外仓按单据**改采购成本 | 批量、多规则、非海外仓按仓库+SKU |
| 交互 | 一次 create + 一次 audit，无点击 | 生成文件 → 页面上传 → 人工点审核 |
| 依赖 | 浏览器 cookie 登录态 | 浏览器 cookie 登录态 |
| 状态 | 2026-09-18 实测跑通 | 既有路径 |

```bash
# A. 纯 API：改 test001-white 的采购单价，dry-run 先看 payload
uv run python sellfox_cost_adjust_api.py --no OWS294A9T700030 --sku test001-white --new-cost 1.48
uv run python sellfox_cost_adjust_api.py --no OWS294A9T700030 --sku test001-white --new-cost 1.48 --apply
```

### 为什么写要借浏览器会话

`成本补录单` 在**公开 OpenAPI 下只有查询一个端点**（`/api/fba/cost/adjustment/pageList.json`，
且 `status` / `warehouseIds` / `createTime` / `searchField=sku` 等过滤字段一律返回
`40021 访问的接口暂无权限`）。创建与审核是**内部接口**，必须带赛狐站点 cookie：

```
读  GET  /api/fba/cost/adjustment/getItemsByNoAndSearchValue.json?adjustType=6&no=<备货单号>
写  POST /api/fba/cost/adjustment/create.json   body = 完整 items 回填后整坨
    POST /api/fba/cost/adjustment/audit.json    body = [adjustId, ...]
    POST /api/fba/cost/adjustment/delete.json   body = [adjustId, ...]
    POST /api/fba/cost/adjustment/reject.json   body = {"adjustId": N, "reason": "..."}
```

所以 `sellfox_cost_adjust_api.py` 走 Playwright 的 `page.request`（复用登录态），
而不是裸 `requests`。契约细节见 `docs/solutions/integration-issues/sellfox-cost-adjust-api.md`。

## 先回答「改哪张单」

成本补录单**只能按单据**改，备货单头程也只能**逐单**改。但一个 (仓库,SKU) 常有几十上百张
历史单，绝大多数货已出完。真正要改的是**货还在库里的批次**的来源单 —— 用 `probe_batches.py`：

```
SKU: KS0248-DM-60-WHITE
  批次总数 128，有货批次 4，可用总量 150
  加权采购单价 104.38   加权单位费用 8.12

  来源单号              仓库      type  备货单  批次  可用量  采购单价  单位费用
  OWS294A9T700007      DANEEY   5     是     1    139    104.38   8.12
  AD2609040001         DANEEY   3     否     1    7      104.38   8.12
  AD2609150001         DANEEY   3     否     1    3      104.38   8.12
  AD2609180001         DANEEY   3     否     1    1      104.38   8.12
```

数据来自**海外仓批次**接口（`/api/overseaBatch/page.json`）：`goodsAva>0` = 还在库，
`oriNo` = 来源单号，`inventoryCost`/`transportCost` = 该批次的采购成本/头程。
加权后可与【库存明细】的 `采购单价(￥)`/`单位费用(￥)` 对账。

> `type=5` 且 `oriNo=OWS…` 才是**海外仓备货单**；`AD…` 是库存调整单，
> **没有「单个头程费用」可改**。库存常是混合来源，改之前先看清构成。

## 数据流

```
激励成本规则.xlsx（仓库/SKU/[单据号/单据类型]/规则类型/规则值）
  + 赛狐库存明细导出（可选，取当前采购单价做「前值」对照与比例/差额基准）
  → 复制官方模板 → 逐行填 → 分批输出(≤5000条/文件)
  → dispatch.py sellfox.cost-adjust.import 导入
  → 【人工】在成本补录单页点「审核通过」才生效
```

## 两种模式（由是否有「单据号」列自动判定）

| 模式 | 触发条件 | 模板列 | 适用 |
|---|---|---|---|
| **按SKU** | 规则表**无**单据号 | `*仓库 *SKU 店铺 FNSKU 专属类型 采购单价 总货值 单位费用 总费用` | 非海外仓 |
| **按单据** | 规则表**有**单据号 | `*单据号 *单据类型 *SKU 组合SKU 店铺 FNSKU 专属类型 MSKU 货件号 采购单价 总货值 单位费用 总费用` | **海外仓只能走这个** |

`单据类型` 可选值：`发货单 / 采购单 / 其他入库单 / 调拨单 / 海外仓备货单 / 移除入库单 / 多平台发货单`
（海外仓用 `海外仓备货单` + 备货单号）。

> 生成器会**主动拦掉**以下情况并在「跳过」sheet 里写明原因：
> - 海外仓走按SKU（赛狐报 `创建类型为按sku时,不能为海外仓`）
> - 单据类型属于 `发货单/海外仓备货单/多平台发货单` 却填了 `单位费用`
>   （赛狐报 `发货单、海外仓备货单、多平台发货单填写单位费用、总费用无效，导入失败`）

## 规则表

必填列 `SKU`、`规则类型`、`规则值`，另需 `仓库`（按SKU）或 `单据号`（按单据）。可选 `单据类型`、`基准值`、`单位费用`。

规则类型：`固定值`（=规则值）/ `按比例`（=基准值×规则值）/ `按差额`（=基准值−规则值）。
基准值缺省时从库存明细导出里取该 仓库+SKU 的当前采购单价。

## 关键结论（2026-09-18 实测）

- **头程（单位费用）成本补录单改不了** —— 海外仓备货单类型不许填。改头程走备货单的
  「单个头程费用」，**两条 Excel 模板都不含该字段**，只能走私有接口：
  `uv run python sellfox_restock_headfee_api.py --pick-id <id> --sku <SKU> --new-fee <值>`。
  详见 `docs/solutions/integration-issues/sellfox-restock-headfee-api.md`。
- ⚠️ **改一张备货单只影响它自己那个批次**：`Δ单位费用 = ΔheadFee × (本批次可用量 / 该SKU总可用量)`。
  实测 `KS0248-DM-60-WHITE`@DANEEY 改 8.12→4.08，本批次占 139/150，单位费用只从 8.12 到 4.3763
  —— 另 11 件来自 3 张**库存调整-增加**单，它们各自新建独立批次、**不跟随**，且没有自动化入口。
  改之前先跑 `sellfox_restock_headfee_api.py`（它会打印批次构成与预测值）。
- **补录单需审核**：建单后是「待审核」，**审核通过后才改动库存成本**；待审核期间不动。
  可页面点「审核通过」，也可走 API `audit.json`（`sellfox_cost_adjust_api.py --apply`）。
- 生效后库存按**加权平均**重算（只重算受影响的批次份额）。
- **实际影响 = 剩余数量 × 价差，不是原始数量 × 价差**。实测把某批次单价 1.50→1.48，
  该批次原 1000 件但当时只剩 997 件，最终库存成本只降 `997 × 0.02 = 19.94` 而非 20。
- **两仓库不是笔误**：`warehouseId` 是**虚拟仓库**（FBA 侧来源），`targetWarehouseId`
  才是真实海外仓（如 POLAND）。照抄，别自己拼。

详见 `docs/research/2026-09-18-sellfox-cost-accounting-fifo.md` 与
`web_automation/docs/reference/sellfox-pitfalls.md`。
