---
okf: v0.1
type: Reference
title: 赛狐踩坑与选择器参考
description: 赛狐 ERP 的关键选择器模式、DOM 知识、Excel 导入陷阱
tags: [sellfox, pitfalls, playwright, element-ui, selectors, excel-import]
timestamp: 2026-05-25
---

# 赛狐踩坑与选择器参考

## 关键选择器模式

- **下拉框**: `input[placeholder="全部仓库"]` — el-select 组件
- **按钮**: 可能是纯图标（如 `.icon_sf_download`），页面搜不到文字
- **弹窗**: `el-dialog` 组件，标题在 `.el-dialog__title`
- **表格**: `el-table` 或 `vxe-table`
- **复选框**: `el-checkbox`

## Element UI 弹性窗定位

**永远**用 `.filter(d => d.getBoundingClientRect().width > 0)` 过滤 —— 赛狐页面有 20+ 个隐藏的 `.el-dialog__wrapper`，`querySelector` 默认拿第一个（是隐藏空壳）。

## 登录检测（双重判定）

1. **URL 检测**：`"login" not in page.url`（登录后跳离 login.html）
2. **用户元素检测**：`page.locator('text=克勇').first.is_visible()`（用户名出现）

登录成功 → 立刻检测 `page.url`：
- 如果在 dashboard → `page.goto(PAGE_URL)` 跳到仓库页
- 如果已在仓库页 → 直接继续

## 赛狐 Excel 导入

- **必须 sheet_name='商品'**：模板文件有 3 个 sheet (`['商品','hidden1','hidden2']`)，`pd.to_excel()` 默认 `Sheet1` 会被赛狐拒绝
- **禁止 pd.read_excel(模板)**：读模板会带 hidden sheet，`to_excel` 后丢失这些 sheet → 导入卡死
- **正确做法**：只取表头列名 → `pd.DataFrame()` 构造数据 → `ExcelWriter(sheet_name='商品')` 写入
- **文件上传**：Python Playwright 用 `expect_file_chooser` + `set_files()`，或直接用 `set_input_files`
- **上传后弹窗**：`POST /excel/import.json` (multipart/form-data) 返回 200+taskID，但前端等 WebSocket 通知

## el-dropdown-menu__item 不可见

Playwright click 超时 (element not visible) → 使用 `page.evaluate("item.click()")` 绕过可见性检查。

## 禁止坐标点击（硬规则）

**不许用 `page.mouse.click(x, y)` / 坐标定位元素。** 坐标会随视口、横向滚动、列宽变化而失效，
且无法沉淀成可复用脚本。MCP 探路时也一样 —— 探路结论必须能直接翻译成选择器。

- 元素看不见（在横向滚动区外）→ 用 `locator.scrollIntoViewIfNeeded()`，Playwright 会自动滚。
- 需要「第 N 行的某列」→ 先定位行 `locator(...).nth(i)`，再在行内定位列。
- 只为了取元素位置而算坐标 = 信号用错了，回去找选择器。
- 例外仅限：canvas / 地图 / 拖拽排序这类无 DOM 语义的场景（赛狐常规表格不在此列）。

## 赛狐 vxe-table：固定列与滚动列是两张平行表

`stockOrder` 详情/编辑页的「商品信息」表用 `vxe-table`。固定列（图片/品名SKU/店铺/FNSKU）
和滚动列（采购单价…单个头程费用）分属 **两个独立表**：

- `.vxe-table--fixed-left-wrapper tbody tr` ← 固定列
- `.vxe-table--body-wrapper.body--wrapper tbody tr` ← 滚动列

两表 `tr` **按行号一一对应**。要读「某 SKU 的完整行」必须先在其中一张表找到行号 `idx`，
再用 `.nth(idx)` 取另一张表的同一行。直接对单表 `tr.innerText.includes(sku)` 只会拿到半行。

## 赛狐 成本补录单 / 备货单头程

- **成本补录单入口**：`web/fba/adjust/index.html`（仓库 → 成本补录 → 成本补录单）。
  只有「导入成本补录单」，模式选 **`按SKU导入`**；模板 `batch_import_adjustment_by_sku.xlsx`
  表头 9 列（`*仓库 *SKU 店铺 FNSKU 专属类型 采购单价 总货值 单位费用 总费用`），
  必填只有 `*仓库`+`*SKU`，单文件 ≤5000 条。**模板含 2 个 data validation，必须 `shutil.copy` 复制模板再写，不能重建表头。**
- **备货单头程**：列表页点「详情」→ 详情页底部点「编辑」。编辑页「商品信息」表里
  `采购单价`/`指定采购单价` 是**只读文本**，只有 `物流费用(CNY)`/`报关税费(CNY)`/`其他费用(CNY)`/
  `单个头程费用(CNY)` 可编辑。改 `单个头程费用` 会**反向联动** `物流费用` = 单价 × 数量，
  `总头程费用` 为只读自动值。
- **表内 SKU 定位框**：编辑页「商品信息」表右上角有常驻 `input[placeholder="请输入SKU"]`，
  填 SKU + 回车会把目标行加上 `table_sku_search_match_row table_sku_search_current_row` 类名（高亮）。
  不要用表头那个 `i.icon_sf_search` 图标（点了不出输入框）。
- **保存前必弹批次警告**：「将改动该批次商品的头程费用，若其他单据使用该批次商品也将同步修改」
  → 头程修改按**批次**生效，不是单单据。

## 网页私有接口与共享浏览器

- 赛狐前端调 `/api/fba/cost/adjustment/{create,edit,audit,delete}.json`、`/api/oversea/edit.json`
  等私有接口（公开 OpenAPI 里没有）。按约定**需另行批准并验证后才能用，不能当稳定合同**。
- **MCP 的 Playwright 浏览器是跨 worktree 共享的**（profile 落在某个 worktree 的 `.playwright-mcp/`）。
  多个会话同时用会互相干扰。**写操作一律走 `web_automation/scripts/dispatch.py` 自带的
  `web_automation/sellfox-profile`**，不要用共享 MCP 浏览器。
- 微前端（wujie）沙箱下 `fetch` 时有时无；页面内发请求优先用 `XMLHttpRequest` 包 Promise。

## 备货单列表「搜索内容」输入框：placeholder 随搜索类型变

`stockOrder` 列表第二行的搜索输入框，**placeholder 不是固定的**：

| 搜索类型 | placeholder |
|---|---|
| 备货单号（默认） | `搜索内容` |
| SKU | `双击可批量搜索内容` |

按 `input[placeholder="搜索内容"]` 定位会在切成 SKU 后超时。**先选搜索类型，再按当时实际 placeholder 定位**。
（`双击可批量搜索内容` 的框单点可直接输入；双击会弹 `nav_search_container` 批量粘贴弹窗，
该弹窗会 intercept pointer events，挡住其它按钮 —— 用完要 `Escape` 关掉。）

切精确/模糊：`.search_type_btn i`，class 在 `icon_sf_fuzzy` ↔ `icon_sf_precise` 之间切。
**模糊搜索会返回无关单据**（用单号搜能搜出一堆别的单），做定位一律切精确。

## 赛狐成本口径：仓库+SKU 的采购单价/单位费用怎么变（实测）

2026-09-18 在真实环境用测试品 `test001-white`（POLAND）实测。

**库存明细报表口径 = 移动加权平均**（`SELLFOX_API/.../库存明细/查询库存明细.md:302` 原文：
「采购单价,移动加权平均计算」）。`单位库存成本 = 采购单价 + 单位费用`。

### 实测记录（同仓同 SKU，逐笔叠加）

| 步骤 | 库存 采购单价 | 库存 单位费用 | 在库总费用 |
|---|---|---|---|
| 初始（无库存） | 0.0000 | – | 0.00 |
| 收货 030（采购1.5 / 头程0.20 ×1000） | 1.5000 | 0.2000 | 200.00 |
| 收货 029（采购1.5 / 头程4.08 ×1000） | 1.5000 | **2.1400** ＝(0.2+4.08)/2 | 4,280.00 |
| **改已完成单 029 的头程 4.08→1.00** | 1.5000 | **0.6000** ＝(0.2+1.00)/2 | 1,200.00 |

### 结论

- **「单个头程费用」是唯一驱动力**：改备货单的这一列 → 库存 `单位费用` 按**加权平均实时重算**。
  - **已完成（已入库）单改头程 ✅ 有效**（上表第 4 行，硬刷新后仍生效）。
  - 收货前改也有效，收货时按当时值计入。
- **「指定采购单价」→ 库存 `采购单价(￥)`**（本例 1.5000）。
- **在途口径不跟**：改**待收货**单的头程，库存明细的「在途总费用」**不变**（实测 029 在途期间改 0.20→4.08，
  在途总费用仍 400）。在途是快照值，不要用它验证头程改动。
- ⚠️ 之前误判过一次：拿一张**库存已被调整单清零**的单（024）改头程，看库存不变就以为「改完不回写」。
  实际是那张单的货已经不在仓库了，没有可重算的库存。**验证成本传导必须选「当前确实有库存」的单。**

### 出库结转口径（与报表口径不同）

官方帮助 `sellfox.com/help/features/batch-cost-fifo`：赛狐的**批次成本=按店铺站点维度先进先出**，
开关在【**设置】**>【**业务设置】**>【**先进先出】**；开启后批次成本影响【财务】>【利润报表】的商品成本。
出库成本取值优先级：**关联发货单的成本 > 导入库存成本（重置成本）> 商品模块固定成本**。
页面另有【财务】>【批次成本】可按批次入库/出库核对（出库类型含 订单出库/货件出库/库存移除…）。

→ 所以「库存明细」看加权平均，「利润报表/订单成本」看 FIFO 批次——两套口径并存，别混用。

### 备货单状态机（实测）

`待配货 → (分配) → 待发货 → (发货) → 待收货 → (收货) → 已完成`

- 列表操作列：`待配货→分配库存`、其余状态→`详情`；详情页底部才有 `编辑`。
- **分配/发货/收货 是列表工具栏按钮**，且**必须先勾选单据**否则按钮 disabled。
- 详情页按状态给不同动作（待配货=`分配库存`；待发货/待收货=`发货`/`收货`；已完成=`编辑/撤销`）。
- `发货` 会弹 **「确定发货后，将扣减库存」**；`收货` 页先点「全部数量」再点「收货」。
- 状态可能滞后：顶部标签显示旧状态时，操作会报「待收货状态下不允许进行该操作」。
  **每次点击后都要截图看结果弹窗，不要只看 DOM。**

## 成本补录单：海外仓只能「按单据导入」，且不许改单位费用（实测）

2026-09-18 实测（`test001-white` @ POLAND），三条硬规则都是**导入报错原文**：

1. **按SKU导入不支持海外仓**
   > `成本补录单中创建类型为按sku时,不能为海外仓`

   → 海外仓（POLAND/DANEEY/CENTRADE…）**必须走「按单据导入」**。

2. **按单据导入的模板与「单据类型」可选值**
   模板 `batch_import_adjustment_by_order.xlsx`，列：
   ```
   *单据号 | *单据类型 | *SKU | 组合SKU | 店铺 | FNSKU | 专属类型 | MSKU | 货件号 | 采购单价 | 总货值 | 单位费用 | 总费用
   ```
   `*单据类型` 的下拉（data validation）：
   `发货单, 采购单, 其他入库单, 调拨单, 海外仓备货单, 移除入库单, 多平台发货单`
   → 海外仓备货单用**备货单号**做「单据号」即可关联。

3. **发货单/海外仓备货单/多平台发货单 不许填 单位费用/总费用**
   > `发货单、海外仓备货单、多平台发货单填写单位费用、总费用无效，导入失败`

   → 这三类单据的补录单**只能改采购单价/总货值**。这解释了为什么「成本补录单改不了头程」。

4. **补录单需要审核**：导入后状态 `待审核`，要在详情页点「审核通过」→ 弹「确认审核通过?」→ 确定，
   变 `已通过` 后才生效（页签：全部/待审核/已通过/已驳回）。

5. **生效后库存按加权平均重算**（实测）：
   补录 CA26091800001 把 029 的 1000 件采购单价 1.5→1.2，库存从
   `采购单价 1.5000 / 在库总货值 3,000` 变成 `1.3500 / 2,700`
   ——`(1000×1.5 + 1000×1.2)/2000 = 1.35`，只重算了受影响的批次份额。`单位费用` 不受影响。

### 汇总：入库后改成本的两条路

| 成本项 | 路径 | 是否传导到库存 |
|---|---|---|
| **采购成本** | 成本补录单（**按单据导入**，类型=海外仓备货单，**需审核**） | ✅ 加权平均重算 |
| **头程（单位费用）** | 成本补录单 ❌ 不支持 → 改备货单 `单个头程费用` | ✅ 加权平均重算 |

两条路都行，不必清零重入。

### 补录单相关私有接口的两个坑（自动化必踩）

`POST /api/fba/cost/adjustment/pageList.json`（查列表）：

- **`createTimeStart` 只接受日期 `YYYY-MM-DD`**。传 `"2026-09-18 13:55:12"` 会返回
  `code=500 系统异常，请联系管理员！`，看起来像「查不到数据」，实际是参数被拒。
- **主键字段是 `adjustId`，不是 `id`**。补录单详情页 URL 用 `adjustId`：
  `/web/fba/adjust/DetailCostSupplement/index.html?...&id=<adjustId>`。
  写成 `row["id"]` 会得到 `id=undefined`，页面打不开。
- `status` 取值：`to_audit` / `has_passed` / `has_rejected`。
- 该接口在页面上下文可用 `page.request.post(...)` 直接调（与浏览器共享 cookie）。
  微前端沙箱里 `fetch` / `XMLHttpRequest` 时有时无，用 `page.request` 更稳。

### 导入成功 ≠ 生效

`sellfox.cost-adjust.import` 导入完只是落库为「待审核」。脚本 `approve_for_file()`
会在导入后按 **文件里的 SKU × status=待审核** 反查本次产生的补录单并逐张审核，
审核后用同一接口复核 `status == has_passed` 才算成功；`--no-approve` 可关掉这步。

### 定位「该改哪些单据」：海外仓批次接口

改成本必须落到**具体单据**，但一个 (仓库,SKU) 有几十上百张历史单，绝大多数货已出完。
真正要改的是**货还在库里的批次**对应的来源单。

`POST /api/overseaBatch/page.json`（页面：仓库 → 海外仓 → 海外仓批次，
`web/warehouse/batchManagement/index.html`）：

```json
{"warehouseIds":"","dateType":"","startDate":"2024-01-01","endDate":"2099-12-31",
 "searchType":"commoditySku","searchContent":"<SKU>","type":[],"brandIds":[],"state":"",
 "pageSize":200,"pageNo":1,"orderBy":"","desc":""}
```

- **筛 SKU 用 `searchType=commoditySku` + `searchContent`**。传 `commoditySku` 参数**不会过滤**
  （会把所有 SKU 的批次按时间倒序返回，看起来"过滤了"只是因为目标 SKU 最新）。
- `data.totalSize` 常为 0，**不能靠它判断翻页结束**；用「本页返回 < pageSize」判尾。
- 关键字段：

  | 字段 | 含义 |
  |---|---|
  | `oriNo` | **来源单号**（`OWS…`=海外仓备货单；`AD…`=库存调整单） |
  | `type` | 5=海外仓备货；3/4=库存调整（增加/减少） |
  | `goods` / `goodsAva` | 数量 / **可用量（>0 才是在库）** |
  | `inventoryCost` | 该批次**采购成本** |
  | `transportCost` | 该批次**头程费用**（即库存的「单位费用」） |
  | `warehouseName` / `batchNo` | 仓库 / 批次号 |

- 用 `goodsAva>0` 过滤、按 `oriNo + 仓库 + type` 分组，即可得到「该 SKU 的库存来自哪些单」，
  且加权平均后可**反算出库存明细的 `采购单价(￥)` / `单位费用(￥)`**（实测完全对上）。

> ⚠️ 库存常是**混合来源**：实测 `KS0248-DM-60-WHITE`@DANEEY 可用 150 件里，
> 139 件来自备货单 `OWS294A9T700007`，另 11 件来自 3 张库存调整单（AD…）。
> **调整单来源的批次没有「单个头程费用」可改**，所以只改备货单无法把整个 (仓库,SKU)
> 的平均成本拉到目标值——改之前先看清楚来源构成。

工具：`cost_adjust/probe_batches.py`（登录后直接打印上述分组与加权值）。

## 库存调整单只管数量，不涉及成本（实测）

2026-09-18 用 `test001-white` 核实（调整单 `AD2608140016`，`type=0 数量调整`，POLAND）。
三处证据一致，**没有任何成本字段**：

| 来源 | 结论 |
|---|---|
| OpenAPI `POST /api/ware/adjust/create.json` | 只有 `type(0数量调整/1换标调整)`、`availableNum`、`defectiveNum`、货架位 —— 无成本 |
| 内部页面 `POST /api/gw/sellfox/sellfox-warehouse/sellfox/api/warehouse/adjust/pageList` | 主表字段：`adjustNo/type/adjustStatus/sum/remark/adjustmentReason/...` —— 无成本，只有 `sum` 数量合计 |
| 同上接口的 `itemList[]` | `available/defective/newAvailable/newDefective/targetAvailable/targetDefective` + 货架位 —— **成本字段 0 个** |

**结论：赛狐的库存调整单是纯数量调整，不碰成本。**
（对比：ERPNext 的库存调账可同单同时改数量与成本；赛狐不是。）

派生影响：

- 用 API 把通途库存写回赛狐（同事的做法）只能走**数量**，成本改不了。
- **调整单产生的批次会跟随其来源备货单的成本**（实测）：把 `OWS294A9T700024` 的
  `单个头程费用` 从 4.08 改成 7.77 后，由它产生的调整单批次 `20260529002385`
  的 `transportCost` 同步从 4.08 变成 7.77（`updateTime` 即改动时刻）。
  → 所以**不存在「调整单批次钉住成本、拉不动均价」的问题**；改备货单会连带更新其派生批次。
- 因此**改成本只需要盯「海外仓备货单」**；调整单只在**数量**维度影响库存。
  `probe_batches.py` 里出现 `AD…` 来源时，先确认它是不是由某张备货单派生
  （变更该备货单即可连带覆盖）。

## 单据号前缀 → 单据种类（别只记前缀）

`海外仓批次` 表「单据号」列的前缀对应（`类型` 列会直接写中文，核对用它）：

| 前缀 | 单据种类 | 批次表 `type` | 说明 |
|---|---|---|---|
| `OWS…` | **海外仓备货单** | 5 | 入库；可改「单个头程费用」、可做成本补录（按单据-海外仓备货单） |
| `AD…` | **库存调整单** | 3=库存调整-增加 / 4=库存调整-减少 | **只调数量，不涉及成本**（见上一节） |
| `P…` | **FBM订单出库**（销售出库） | 15 | 平台订单发货扣减 |

> `海外仓批次` 页面 仓库 → 海外仓 → 海外仓批次（`web/warehouse/batchManagement/index.html`）。
> 实操时**以「类型」列的中文为准**，前缀只是便于口头指代。

## 为什么「改备货单头程」会连带动到调整单批次 —— 不是 FIFO，是「批次即成本载体」

**赛狐的 `batchNo` 是库存的原子单位，成本（`inventoryCost`/`transportCost`）存在批次上，只存一份。**
出入库单据只是引用同一个 `batchNo` 并记录数量增减：

```
batchNo 20260529002385
  OWS294A9T700024   海外仓备货     +1000   createTime 2026-05-29
  AD2608140016      库存调整-减少  -1000   createTime 2026-08-14
  → 两行显示的成本是同一份；改备货单 -> 该批次成本变 -> 两行一起变
```

实测：83 行批次记录里只有 **42 个唯一 `batchNo`** —— **40 个批次被多张单据引用**。

所以「改备货单会连带更新它派生的调整单批次」**不是先进先出联动**，
而是「同一批次只有一份成本」的必然结果：备货单改的是**那个批次**，任何引用该批次的单据行都跟着变。

> 什么才是 FIFO：**出库时消耗哪个批次**（`海外仓批次` 里 `P…` FBM订单出库的行，
> 每行带具体 `batchNo` 和数量，看得见逐批扣减）。这决定订单成本取哪批，与上面的联动无关。
> 官方帮助说批次成本按店铺站点维度先进先出，开关在【设置】>【业务设置】>【先进先出】。

## Element UI checkbox

`cb.click()` 在 evaluate 中不改变 Vue 组件状态 → 必须用 Playwright `page.locator().click()` 真实点击。

## Playwright JS 绑定：first/nth 是方法不是属性

MCP 的 `browser_run_code_unsafe` 跑的是 Playwright **JS** API：`page.locator('x').first()`、
`.nth(i)`、`.count()` 都要加括号。写成 `.first` / `.nth` 会拿到函数对象并报
`row.locator is not a function`。

