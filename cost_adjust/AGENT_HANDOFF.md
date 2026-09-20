# cost_adjust — Agent 接手文档

赛狐**已入库库存成本**的修改能力舱。三条路径，按「能不能自动化」和「有没有 Excel 入口」选。

## 职责边界

| 做什么 | 不做什么 |
|---|---|
| 改**已入库**库存的采购成本 / 头程（单位费用） | 创建商品、改数量以外的库存属性 |
| 定位「该改哪些单据/批次」 | 库存数量同步（那是「其他入库单」/库存调整单的事） |
| 走赛狐原生单据（成本补录单 / 备货单编辑），不绕后台 | 直接改数据库 |

## 三条路径（先看这张表再动手）

| | A. 成本补录单 API | B. 备货单头程 API | C. 导入 xlsx + UI |
|---|---|---|---|
| 脚本 | `sellfox_cost_adjust_api.py` | `sellfox_restock_headfee_api.py` | `build_saihu_cost_adjust.py` + dispatch |
| 改什么 | **采购单价**（总货值） | **单个头程费用**（库存「单位费用」） | 采购单价 |
| 适用形态 | 海外仓按单据（单张、少量） | **唯一能改头程的路径** | 批量 / 多规则 / 非海外仓按 SKU |
| 交互 | create + audit，无点击 | 读整单 → 改 → edit，无点击 | 生成文件 → 页面上传 → 人工审核 |
| 成本字段 | `newPurchaseCost` / `newTotalPurchaseCost` | `headFee`（+派生 `logisticsCost`/`totalHeadFee`） | 模板列 |

> **头程走不了 A**：成本补录单在「海外仓备货单」类型下**不许填单位费用**。
> 两条 Excel 模板也都不含该字段（实测表头：`pickingOrderUpdateTemplate` 零费用字段；
> `overseaPickingListFee` 是物流信息层且无 UI 入口）。**B 是唯一路径。**

## 快速运行

```bash
cd cost_adjust

# 0) 先定位：这个 SKU 的库存来自哪些单据/批次（改之前必做）
uv run --project ../web_automation python probe_batches.py KS0248-DM-60-WHITE

# A. 改采购成本（默认 dry-run）
uv run python sellfox_cost_adjust_api.py --no OWS294A9T700030 --sku test001-white --new-cost 1.48
uv run python sellfox_cost_adjust_api.py --no OWS294A9T700030 --sku test001-white --new-cost 1.48 --apply

# B. 改头程（默认 dry-run，会打印批次构成与单位费用预测）
uv run python sellfox_restock_headfee_api.py --pick-id 11462 --sku KS0248-DM-60-WHITE --new-fee 4.08
uv run python sellfox_restock_headfee_api.py --pick-id 11462 --sku KS0248-DM-60-WHITE --new-fee 4.08 --apply

# C. 批量：规则表 → 导入文件
uv run python build_saihu_cost_adjust.py --dry-run
```

两个 API 脚本都需要**浏览器登录态**：默认用 `web_automation/sellfox-profile`，
先 `uv run --project ../web_automation python web_automation/scripts/bootstrap.py` 建环境。
profile 没登录时会停在登录页等（没有自动登录）。

## 关键坑（都是实测踩出来的）

1. **写入是「读→改→整坨回发」**（A 和 B 都是）。payload 是读接口结果的**逐字段回填**，
   自造字段可能被静默改写或拒绝。
2. **A 的反直觉字段**（照抄，别自己造）：`warehouseId` 是**虚拟仓库**、`targetWarehouseId` 才是真实仓；
   `newPerFee` 传 `0` 而 `oriPerFee` 是 `null`；`oriTotalPerFee` 是**空字符串**。
3. **B 的 500 行单写一次要 16~18 秒**（超线性）。脚本已把 `edit` 超时放到 300s，**不要并发**。
4. **B 的 `page.json` 搜索必须 `searchType='sku'`** —— 传 `commoditySku` 等其它值被**静默忽略**，
   返回未过滤全量列表（会误判"搜不到"）。`data.totalSize` 也不可信，用 `rows`。
5. **改一张备货单只影响它自己那个批次**：`Δ单位费用 = ΔheadFee × (本批次可用量 / SKU总可用量)`。
   先跑 B 看它打印的批次构成与预测值。
6. **批次 `type` 决定跟不跟随**：`3`=库存调整-**增加**（**自建独立批次，不跟随**）、
   `4`=库存调整-**减少**（共享批次，跟随）、`5`=海外仓备货单。
   **调整单-增加产生的批次没有自动化入口可以改。**
7. **A 的公开 OpenAPI 读接口会间歇 `40021`**，重试即可；`sellfox_cost_adjust_api.py` 走浏览器会话不受影响。
8. **写操作范围必须先确认**：默认只用测试商品，绝不擅自扩大。

## 不可逆操作（红线）

- **成本补录单 `audit` 一旦执行即生效并改库存成本**（无审批流账号下 `create` 就已经直接完成落账）。
- **库存调整单已完成 → 不可删除、不可撤销**（`仅【待调整】、【待提交】状态的单据可删除`），
  `+N` 后用 `-N` **回不去**（扣减按 FIFO 吃最老批次）。→ 见 `docs/solutions/integration-issues/sellfox-adjust-order-write-chain.md`
- 因此：**任何写操作先列范围（SKU/仓库/单据号/预期影响/回滚方案）让用户点头，再动手。**

## 文件清单

| 文件 | 作用 |
|---|---|
| `build_saihu_cost_adjust.py` | 规则表 → 成本补录单导入 xlsx（按SKU/按单据两模式） |
| `probe_batches.py` | 定位「该改哪些单据」：从海外仓批次接口反推在库批次及其来源单 |
| `sellfox_cost_adjust_api.py` | 成本补录单纯 API 客户端（读明细/建单/审核/驳回/删除） |
| `sellfox_restock_headfee_api.py` | 备货单头程纯 API 客户端（读整单/批次构成/预测/提交） |

## 相关文档

- `docs/solutions/integration-issues/sellfox-cost-adjust-api.md` — 成本补录单完整契约
- `docs/solutions/integration-issues/sellfox-restock-headfee-api.md` — 头程完整契约
- `docs/solutions/integration-issues/sellfox-adjust-order-write-chain.md` — 调整单语义与不可逆性
- `docs/research/2026-09-18-sellfox-private-api-terminology.md` — 私有接口 vs 公开 OpenAPI
- `docs/research/2026-09-18-sellfox-cost-accounting-fifo.md` — 批次成本口径与 FIFO
- `web_automation/docs/reference/sellfox-pitfalls.md` — 页面侧踩坑（vxe-table、弹窗、批次警告）

## 未解决

| 项 | 状态 |
|---|---|
| 成本补录单 `edit` / `updateRemark` | 端点存在但**成本补录单页面无触发入口**，payload 未解析 |
| 库存调整-**增加**批次的成本修改 | **未找到任何入口** |
| 其他入库单（`inRecord/v2.json`）产生的批次行为 | 未验；它 `perPurchase` 必填 + `shipFee/otherFee`，是**带成本的入库**正路 |
| `oversea/inventory/syncInventory.json` 等三方仓库存端点 | **已探，未能验证**：本账号这些端点返回空、三方仓配置接口报 `系统异常`，推测**未开通三方仓功能**。若开通值得重探 |
| `detail.json`（成本补录单） | 参数名未试出；`detailByRelationNo.json` 已覆盖需求 |

## 数量同步场景：看这份文档

「用调整单把外部库存数量同步进赛狐」是一条**长期积累成本债**的路 ——
**这不是用错工具**（赛狐自己的三方仓模块就有「生成调整单」功能，权限
`MOD_OVERSEA_WAREHOUSE.CREATE_ADJUST`），问题在**调整单批次的成本是快照且不可修正**。

完整成因、量化证据与三个选项见
[`docs/solutions/workflow-issues/sellfox-inventory-sync-cost-drift.md`](../docs/solutions/workflow-issues/sellfox-inventory-sync-cost-drift.md)。
