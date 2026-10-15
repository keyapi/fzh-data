---
okf: v0.1
type: Reference
title: EN 按「绍兴发货方式」组合绍兴成本的实现核实（报表列 绍兴总成本 vs 订单同步字段 绍兴发货成本）
description: 只读核实 ERPNext V2 报表与通途订单同步里「皮壳/半成品/成品」三档各自把哪些绍兴成本列加进成本；是否区分 分公司/FBA/海外仓；三档目的地加工成本列取自哪个物料的 BOM total_cost；头程与发货方式的联动点；并用 3693 行报表快照反证「绍兴总成本 = 皮壳+半成品+成品 三段简单相加」
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, shaoxing, shipping-method, bom, erpnext, reference, read-only]
---

# EN 按「绍兴发货方式」组合绍兴成本的实现核实

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build；临时 SQL 只落服务器 `/tmp`）。
> 相关前作：[en-shaoxing-ship-method-taxonomy-spec.md](en-shaoxing-ship-method-taxonomy-spec.md)（`custom_shipment_type_to_branch` 取值域）、[en-ustx-bom-wage-rate-spec.md](en-ustx-bom-wage-rate-spec.md)（加工成本 = BOM `total_cost`）、[en-pl-finished-processing-nonzero-spec.md](en-pl-finished-processing-nonzero-spec.md)（`pllc_cover` 链路）、[colab-cost-engine-spec.md](colab-cost-engine-spec.md)（下游 Colab 业务引擎）。

## 结论摘要

1. **「按发货方式组合绍兴成本」在 EN 里有落点的只有两处，且口径不同**：
   - **报表列「绍兴总成本」`sx_cost_all`**（`bom_cost_list_v2.py:1496-1530`）——**不是**三段式。实际只有两分支：**(a) 成品 + 自采购**（`shipping_method=="成品"` 且 `cost_fg≠0` 且 `cost_sxbzcp==0` 且 皮壳 BOM 自引用主物料）→ `sx_cost_all = 皮壳成本`；**(b) 其余**（皮壳/半成品/成品/空，只要皮壳 BOM 与 绍兴包装成品 BOM 都在）→ `sx_cost_all = 皮壳成本 + 绍兴包装成品成本`。半成品只做**剔除**（见下），**从不把「绍兴包装半成品成本」加进去**。
   - **通途订单同步字段「绍兴发货成本」`sx_shipping_cost`**（`order_sync.py:2919-3013`）——**这才是用户回忆的三段式**，且**带 FBA 分支**：FBA 仓库无条件取「绍兴总成本」；非 FBA 仓库按发货方式：**皮壳 → 皮壳成本 / 半成品 → 皮壳成本 + 绍兴包装半成品成本 / 成品 → 绍兴总成本（= 皮壳成本 + 绍兴包装成品成本）**。（另有一组 SKU 后缀特例 `-COVER` / `-PPCOTTON` / `-FOAM`。）
2. **是**，区分「分公司 / FBA / 海外仓」。两处机制：
   - **报表侧按价格表名**（`bom_cost_list_v2.py:1542` / 列声明 `:910`、`:972`）：`if not any(k in price_list for k in ["FBA","HWC"])` → FBA 价格表只出「成品运费 + 发成品尾程前成本」，非 FBA 才出「皮壳运费 / 半成品运费 / 发皮壳尾程前成本」。
   - **订单同步侧按仓库分类**（`order_sync.py:2919-2931`）：`is_fba_warehouse = "FBA" in warehouse_classification.upper()`。
   - **海外仓**（`warehouse_classification=美国海外仓`）**不含 "FBA"** → 订单同步走「非 FBA 按发货方式」；报表侧其成本列由 `Tongtu Shipping Warehouse` 配置**映射到美中 USTX**（加工成本=美中加工成本USTX；皮壳/半成品头程=美中USTX；成品头程=USFBA）。
3. **各目的地加工成本列** (`usnj_valuation_rate` / `ustx_valuation_rate` / `pl_valuation_rate`) = **对应目的地包装成品物料**（`USNJBZCP#` / `USTXBZCP#` / `PLBZCP#`，由 `{美东USNJ|美中USTX|波兰PL}包装成品#{KS组}` → `custom_model_id` + `-size` 拼出）的 **active+default BOM 的 `total_cost`**，无此 BOM 则回退 `Item.valuation_rate`，`disabled=1` 置 None。**FBA/海外仓没有第二套加工成本 BOM**：FBA 仓库配置里 `processing_cost_name=NULL`（根本不写加工成本）；海外仓复用「美中加工成本USTX」。**不存在 `HEAD-USFBA` 之类的加工成本列**（`HEAD-*` 是下游 Colab 的头程编码，不是 EN 加工成本）。
4. **头程与发货方式的联动只在「头程运费」三列 + `order_sync.first_freight` 上**（皮壳头程 / 半成品头程 / 成品头程三选一，`-FOAM` 取差额）。**用户回忆的「当月头程是否成品=='成品' 时把列名里的 皮壳 换成 成品」不在 EN 报表、也不在 `order_sync.py`**，它只出现在**下游 Colab 业务引擎**（`colab-cost-engine-spec.md:82`）。
5. **数据反证成立**：对 2026-09-03 报表快照 **3693 行**逐行核对四列——`绍兴总成本 = 皮壳成本 + 绍兴包装成品成本` **约 3215~3404 行**、`= 0` **478 行**；
   关键是 **167 个「绍兴包装半成品成本 ≠ 0」的行里，「含半成品」命中 0 行**（149 行 = 皮壳+成品、18 行总成本为 0）→ **「绍兴总成本 = 皮壳+半成品+成品」被否证**。
   > 主线复核补充：若把「半成品成本 = 0」的行也算进去，`== 皮壳+半成品+成品` 会**假命中 3255 行** —— 那只是「半成品为 0」撑出的假象，**不能当作三段相加的证据**。

## 按发货方式的绍兴发货成本组合（代码事实）

### A. 报表列「绍兴总成本」`sx_cost_all`（`bom_cost_list_v2.py:1496-1530`）

代码逐字（节选）：

```python
# :1504-1515  半成品口径的「剔除」（只减，不加）
if str(shipping_method or "").strip() == "半成品" and cached_info.get("bom_sxbzcp"):
    deduct_qty = frappe.db.get_value("BOM Item",
        {"parent": cached_info.get("bom_sxbzcp"), "item_code": cached_info.get("item_sxbzbcp")}, "qty")
    if deduct_qty:
        deduction = get_sxbzbcp_deduction(...) * flt(deduct_qty)
        cost_sxbzcp_val = max(cost_sxbzcp_val - deduction, 0)
        row["cost_sxbzcp"] = cost_sxbzcp_val

# :1518-1528  只有两个分支
if shipping_method == "成品" and (cost_fg or 0) != 0 and cost_sxbzcp_val == 0:
    if bom_fg and bom_has_item(bom_fg, bom_main_item):   # 皮壳 BOM 自引用主物料 → 自采购
        sx_cost_all_val = cost_fg or 0
else:
    if bom_fg and cached_info.get("bom_sxbzcp"):
        sx_cost_all_val = (cost_fg or 0) + (cost_sxbzcp_val or 0)
```

| 发货方式 | 报表「绍兴总成本」取值 | 备注 |
|---|---|---|
| 皮壳 | `皮壳成本 + 绍兴包装成品成本` | 若缺 皮壳 BOM 或 绍兴包装成品 BOM → `0` |
| 半成品 | `皮壳成本 + (绍兴包装成品成本 − 剔除额)` | 剔除额 = 半成品 BOM 的 `operating_cost` + 半成品 BOM 内「包装箱/包装袋」子树物料 `amount`（`get_sxbzbcp_deduction` `:224-252`），乘 绍兴包装成品 BOM 引用半成品整件的 qty |
| 成品 | ① 若 `绍兴包装成品成本==0` 且 皮壳 BOM 自引用 → `皮壳成本`；② 否则 `皮壳成本 + 绍兴包装成品成本` | 分支②与皮壳同口径 |
| 空 | `皮壳成本 + 绍兴包装成品成本` | 同皮壳 |

**关键：任何分支都不含 `绍兴包装半成品成本`**（半成品路径只把它当作被剔对象）。这与用户回忆的「半成品 = 皮壳 + 半成品成本」**不同**。

### B. 订单同步字段「绍兴发货成本」`sx_shipping_cost`（`order_sync.py:2919-3013`）

```python
warehouse_classification = warehouse_config.get('warehouse_classification') or ""
is_fba_warehouse = 'FBA' in warehouse_classification.upper()      # :2921
if is_fba_warehouse:                                              # :2924
    item.sx_shipping_cost = 绍兴总成本 * qty * factor              # :2928
    item.first_freight    = 头程成品运费 * qty * factor            # :2931
else:                                                             # :2932
    shipping_mode = (bom_row.get(shipping_method_field) or "").strip()
    # :2935 皮壳 / :2959 成品 / :2984 半成品
```

| 发货方式 | 非 FBA 仓库：`sx_shipping_cost` | 头程 `first_freight` |
|---|---|---|
| **皮壳** | `皮壳成本`（`:2956`） | `头程皮壳运费`（`:2958`） |
| **半成品** | `皮壳成本 + 绍兴包装半成品成本`（`:3005-3010` `cost_sum`） | `头程半成品运费`（`:3013`） |
| **成品** | `绍兴总成本`（`:2981`）；即 `皮壳成本 + 绍兴包装成品成本` | `头程成品运费`（`:2983`） |
| FBA 仓库（三档合一） | `绍兴总成本`（`:2928`），**不看发货方式** | `头程成品运费`（`:2931`） |

**SKU 后缀特例**（仅非 FBA 仓库，逐档各自判断）：

| 后缀 | 皮壳 | 半成品 | 成品 |
|---|---|---|---|
| `-COVER` | `皮壳成本` + 皮壳头程，**加工成本=0**（`:2947-2953`） | `皮壳成本` + 皮壳头程，**加工成本=0**（`:2989-2995`） | `皮壳成本` + 皮壳头程，**加工成本=0**（`:2964-2970`） |
| `-PPCOTTON` | `绍兴发货成本=0`、`头程=0`（`:2941-2945`） | — | — |
| `-FOAM` | — | `绍兴包装半成品成本`，头程 = `半成品头程 − 皮壳头程`（`:2997-3003`） | `绍兴包装成品成本`，头程 = `成品头程 − 皮壳头程`（`:2972-2978`） |

→ **用户回忆的三段式在这里完全成立**（非 FBA、无后缀）。差别只在：用户把它当成了**报表的「绍兴总成本」列**，实际它是**订单同步的「绍兴发货成本」字段**，且 FBA 仓库会**忽略**发货方式一律取绍兴总成本。

### C. 「发皮壳/发半成品尾程前成本」`pllc_cover`（`bom_cost_list_v2.py:1562-1583`）

另一处按发货方式分流（但这是「尾程前成本」列，不是「绍兴总成本」）：

```python
if str(shipping_method).strip() == "半成品":                       # :1562
    pllc_cover = 皮壳成本 + 绍兴包装半成品成本 + 半成品头程 + 目的地加工成本   # :1569
else:                                                              # :1578 皮壳/成品/空
    pllc_cover = 皮壳成本 + 皮壳运费 + 目的地加工成本                  # :1580
# 两分支各有「任一项为 0 → 整列置 0」的守卫（:1571 / :1582）
```

以及成品侧 `pllc_fg = 绍兴总成本 + 成品运费`（`:1600`，`:1602` 守卫）。

## 是否区分 分公司 / FBA / 海外仓

**是**，但两处用的是**不同判据**：

| 侧 | 判据 | 代码 |
|---|---|---|
| 报表 | **物流价格表名** 含 `FBA`/`HWC` | `bom_cost_list_v2.py:1542`（计算）、`:911`、`:973`（列声明） |
| 订单同步 | **仓库分类** 含 `FBA` | `order_sync.py:2920-2921` |

- **三档分公司**（USNJ美东 / USTX美中 / PL波兰）：三套独立成本列，目的地加工成本按价格表名 `USNJ`/`USTX`/`PL` 选（`:1553-1558`）。
- **FBA 仓**（美国/欧洲/日本/英国 FBA，`warehouse_classification` ∈ {美国FBA, 欧洲FBA, 日本FBA, 英国FBA}）：报表侧只产「成品运费 + 发成品尾程前成本」；订单同步侧 `is_fba_warehouse=True` → 绍兴发货成本 = 绍兴总成本。
- **海外仓**（大件云仓 / 星链海外仓，`warehouse_classification=美国海外仓`）：**不含 "FBA"** → 订单同步走「非 FBA 按发货方式」；报表侧其成本列由配置映射到**美中 USTX**（见下表）。
- ⚠️ 报表 gate 里的 **`HWC` 在生产库无对应价格表**（`Logistic Price` 只有 7 个价格表：`头程-CNSX-{USNJ,USTX,PL,USFBA,DEFBA,UKFBA,JPFBA}`）→ **`HWC` 是保留关键字、实际未生效**；海外仓之所以仍只出成品列，是因为其配置指向 `USFBA` 成品头程列。

### 证据：`Tongtu Shipping Warehouse` 配置（只读全量，42 行）

`_get_warehouse_cost_config`（`order_sync.py:2193-2242`）把仓库 → 列名映射读出来；`label_to_fieldname`（`:2853-2860`）再把列名映射到 BOM 报表字段名。**关键差异**：

| 仓库分类 | 代表仓库 | 加工成本列 | 皮壳头程 | 半成品头程 | 成品头程 |
|---|---|---|---|---|---|
| USNJ美东分公司 | CENTRADE、美东-*、WayfairCG-Cranbury仓 | 美东加工成本USNJ | 美东USNJ | 美东USNJ | 美东USNJ |
| USTX美中分公司 | DANEEY、FZH-DANEEY-*、WayfairCG-McDonough仓 | 美中加工成本USTX | 美中USTX | 美中USTX | 美中USTX |
| PL波兰分公司 | FZHPoland-*、波兰公司 | 波兰加工成本PL | 波兰PL | 波兰PL | 波兰PL |
| **美国海外仓** | **大件云仓、星链海外仓** | **美中加工成本USTX** | **美中USTX** | **美中USTX** | **USFBA** |
| 美国FBA / 欧洲FBA / 日本FBA / 英国FBA | 美国FBA仓、德国FBA仓… | **NULL（无加工成本）** | NULL | NULL | USFBA / DEFBA / JPFBA / UKFBA |

→ **海外仓 = 借用 USTX 加工成本与皮壳/半成品头程，但成品头程用 USFBA**；**FBA 仓完全没有加工成本列**。

## 各目的地加工成本取值

- 取数函数 `get_item_valuation_rate(item_code)`（`bom_cost_list_v2.py:541-567`）：
  `BOM(item=该物料, is_active=1, is_default=1).total_cost` **优先**，无此 BOM 回退 `Item.valuation_rate`；同时返回 `is_disabled`。
- 物料拼装（各 `get_*bzcp_info`）：`supporting_item_group = f"{美东USNJ|美中USTX|波兰PL}包装成品#{item['item_group']}"` → 反查 `custom_model_id` → `item = f"{custom_model_id}-{size}"`（例：`USTXBZCP#KS0001-100`）。
- 三列定义：`美东加工成本-USNJ` = `usnj_valuation_rate`（`:1280` 附近）、`美中加工成本-USTX` = `ustx_valuation_rate`、`波兰加工成本-PL` = `pl_valuation_rate`；**`disabled=1` 的物料该列置 None**（`:1177`/`:1190`/`:1203`）。
- **FBA/海外仓没有第二套加工成本**：概念链路只有「绍兴 BOM 复制 → 海外**包装成品** BOM」（前缀 `波兰PL包装成品#/美东USNJ包装成品#/美中USTX包装成品#`），**无「FBA 加工 BOM」**。用户问题里的「例如 `HEAD-USFBA`」不是 EN 加工成本列——`HEAD-*` 是**下游 Colab 的头程来源编码**（`colab-cost-engine-spec.md:79-82`）。

## 头程与发货方式的联动

- **EN 报表侧**：头程是**按价格表**出的**三列并存**——`头程皮壳运费` / `头程半成品运费` / `头程成品运费`（列名经 `transform_logistic_header`，`:834-858`；`:854` 注释「发皮壳尾程前成本 不要头程」）。报表本身**不做**「头程是否成品 → 换列名」的动作。
- **订单同步侧**：`first_freight` 按发货方式**三选一**（皮壳→头程皮壳运费、半成品→头程半成品运费、成品→头程成品运费；`-FOAM` 取差额），见上表 B。
- **用户回忆的规则不在 EN**：`当月头程是否成品=='成品' 时把列名里的 皮壳 换成 成品` **在 `bom_cost_list_v2.py` 与 `order_sync.py` 全库 grep 均 0 命中**，唯一出现在 `colab-cost-engine-spec.md:82`（**下游 Colab 业务引擎**：merge `头程运费来源编码-EN成本列名对照表` 得到 `EN成本列名` 后按此规则改名）。→ 这是**业务引擎**的列选择逻辑，不是 EN 报表/同步的产生逻辑。

## 数据验证（带命中数）

### 1. 「绍兴发货方式」取值分布（三口径）

| 口径 | 皮壳 | 成品 | 半成品 | NULL | 空 | 合计 |
|---|---|---|---|---|---|---|
| **Item Group**（`custom_model_id LIKE 'KS%'`） | 156 | 165 | 62 | 12 | 6 | **401** |
| **物料 `SXBZCP#%`** | 401 | 372 | 125 | 9 | 12 | **919** |
| 物料 `PLBZCP#%` | 392 | 233 | 125 | 10 | 12 | 772 |
| 物料 `USNJBZCP#%` | 359 | 85 | 125 | 2 | 12 | 583 |
| 物料 `USTXBZCP#%` | 373 | 96 | 125 | 3 | 12 | 609 |
| **报表行**（2026-09-03 快照，去重后） | **2853** | **639** | **167** | — | **34** | **3693** |

### 2. 用四列反证「绍兴总成本 = 皮壳+半成品+成品」（3693 行逐行核对）

| 关系 | 命中行数 |
|---|---|
| `绍兴总成本 = 皮壳成本 + 绍兴包装成品成本` | **3215** |
| `绍兴总成本 = 0`（含缺 BOM 情形） | **478** |
| **`绍兴总成本 = 皮壳成本 + 绍兴包装半成品成本 + 绍兴包装成品成本`（三段相加）** | **0** |

补充：全表另有 3255 行**数值上**满足三段式，但**全部因「绍兴包装半成品成本 = 0」而平凡成立**（退化为两段式）。
**决定性证据**：在 **167 行「绍兴包装半成品成本 ≠ 0」** 的行里——

| 半成品成本≠0 的行 | 命中 |
|---|---|
| 计入 `绍兴总成本`（三段相加） | **0** |
| `= 皮壳成本 + 绍兴包装成品成本`（忽略半成品成本） | 148（半成品） + 1（成品）|
| `= 0` | 18（半成品） |

→ **「绍兴总成本 = 三段简单相加」被否证。**

### 3. 逐行数值核对（BOM `total_cost` 精确相等）

| 样本（发货方式） | 皮壳成本 | 绍兴包装半成品成本 | 绍兴包装成品成本 | 绍兴总成本 | 对应 BOM/校验 |
|---|---|---|---|---|---|
| `KS0495-FHXWXNERSZSRB-143x84x88-DARKRED`（半成品） | 149.995 | 337.0406667 | 398.3743333 | **548.3693333** | 皮壳=`BOM-KS0495-…-003`；半成品=`BOM-SXBZBCP#KS0495-143x84x88-001`；成品=`BOM-SXBZCP#KS0495-143x84x88-001`；**总成本 = 149.995 + 398.3743333（取成品列，未含半成品 337.04）** |
| `KS0187-HLR-60-GREY`（成品） | 56.341 | — | 90.685 | **147.026** | = 56.341 + 90.685 |

（样本 1 是「半成品行仍用 皮壳+成品」的直接反证；样本 2 是「成品行 = 皮壳+成品」的对照。）

## 与用户回忆的差异

| 用户回忆 | 核实结果 | 差异性质 |
|---|---|---|
| 皮壳 → 皮壳成本 | ✅ 一致 | — |
| 半成品 → 皮壳成本 + 绍兴包装半成品成本 | ✅ 在**订单同步「绍兴发货成本」**里成立（`:3005-3010`）；❌ 在**报表「绍兴总成本」**里**不成立**（那里是 皮壳 + 成品成本，半成品只被剔除） | **对象错位**：是「订单同步字段」而非「报表绍兴总成本列」 |
| 成品 → 皮壳成本 + 绍兴包装成品成本 | ✅ 订单同步（`:2981`，等价于「绍兴总成本」）；报表侧同口径，另有「自采购 → 只取皮壳成本」特例（`:1518`） | 同口径，补充一个特例 |
| 未提及 FBA 分支 | ❌ **FBA 仓库无条件取「绍兴总成本」、忽略发货方式**（`:2924-2931`） | 遗漏分支 |
| 未提及 SKU 后缀特例 | `-COVER`（加工成本清零）/ `-PPCOTTON`（绍兴成本与头程清零）/ `-FOAM`（取半成品/成品成本，头程取差额） | 遗漏特例 |
| `当月头程是否成品=='成品' 时把列名里的 皮壳 换成 成品` | **不在 EN 报表、不在 order_sync**；只在**下游 Colab 业务引擎**（`colab-cost-engine-spec.md:82`） | 归属错位 |
| 疑似「绍兴总成本 = 三段相加」 | **否证**：三段相加 0 命中（3693 行） | 结论被推翻 |

## 未证实 / 存疑

1. **半成品剔除（`:1504-1515`）在 2026-09-03 快照上未见生效**：以样本 `KS0495-…-DARKRED` 为例，快照「绍兴包装成品成本」= 398.3743333 为**成品 BOM 的全额**；而当前生产库中 `BOM-SXBZCP#KS0495-143x84x88-001` 的子件**确实直接引用** `SXBZBCP#KS0495-143x84x88`（qty=1.000000000，amount=337.041000000），按现行代码 `deduct_qty` 非空、剔除路径**应当触发**。→ 快照早于该段代码（或该物料默认 BOM 之后变更），**属快照与代码的版本时序差，具体生效时点未证实**。本规格的「组合逻辑」以**当前代码**为准，「数据分布/否证命中数」以**快照**为准。
2. **报表 gate 的 `HWC` 关键字无对应价格表**（`Logistic Price` 仅 7 个 `头程-CNSX-*`）——推测为预留关键字，**其设计意图未查**。
3. **未按订单加权复算 `sx_shipping_cost` 的月度影响**：本页只做「列口径 + 分布 + 否证」；要给出金额影响需订单行/发货数量（本次未取）。
4. **海外仓成本列的映射由 `Tongtu Shipping Warehouse` 配置反查得出**（大件云仓/星链海外仓 → 美中 USTX + USFBA），**未逐单核对**真实取值。
5. **`绍兴包装半成品成本` 列的独立含义未展开**：本次只证实它**不参与** `sx_cost_all`（半成品路径被剔除），未核它在报表其他列/下游引擎的用法（下游 Colab `colab-cost-engine-spec.md:103-104` 另有「EN绍兴包装半成品成本」变体用法）。
6. **`KS0455-FHXWXNE-92x56x75-GREY` 等皮壳样本**在快照与现库不一致（因默认 BOM 事后变更），本页未逐条重算皮壳样本，仅列作口径说明。

## 证据清单（路径:行号 / SQL）

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`）

| 位置 | 内容 |
|---|---|
| `work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py:1496-1530` | `sx_cost_all`（绍兴总成本）两分支：成品自采购 → `cost_fg`；否则 → `cost_fg + cost_sxbzcp` |
| 同上 `:1504-1515` | 半成品剔除（只从「绍兴包装成品成本」减，不加半成品成本） |
| 同上 `:224-252` | `get_sxbzbcp_deduction()` —— 剔除额 = 半成品 BOM `operating_cost` + 包装箱/袋子树物料 `amount` |
| 同上 `:255-276` | `bom_has_item()` —— 自采购判定（BOM 主物料是否在自己的 items 里） |
| 同上 `:541-567` | `get_item_valuation_rate()` —— active+default BOM `total_cost` 优先，回退 `Item.valuation_rate`；返回 `is_disabled` |
| 同上 `:723-756` | `get_shipment_type_by_ks_code()` —— KS 号 → Item Group → `custom_shipment_type_to_branch` |
| 同上 `:881-1009` / `:910-911` / `:972-973` | 列生成：FBA/HWC 价格表不出 皮壳/半成品运费与发皮壳尾程前成本 |
| 同上 `:1254` / `:1265-1269` / `:1280+` | 列定义：`绍兴发货方式` / `皮壳成本` / `绍兴包装半成品成本` / `绍兴包装成品成本` / `绍兴总成本` / `usnj_valuation_rate` / `ustx_valuation_rate` / `pl_valuation_rate` |
| 同上 `:1177` / `:1190` / `:1203` | `disabled` → 加工成本列置 None |
| 同上 `:1542-1585` | `pllc_cover`（发皮壳/半成品尾程前成本）按发货方式分流 + 零值守卫 |
| 同上 `:1600-1603` | `pllc_fg = sx_cost_all + 成品运费`（发成品尾程前成本）+ 守卫 |
| 同上 `:834-858`（`:854`） | `transform_logistic_header()`；注释「发皮壳尾程前成本 不要头程」 |
| `tongtool_integration/.../sync/order_sync.py:2919-3013` | 订单同步：`is_fba_warehouse` 分支 + 皮壳/成品/半成品 三档 + `-COVER`/`-PPCOTTON`/`-FOAM` 后缀特例 |
| 同上 `:2193-2242` / `:2853-2860` | `_get_warehouse_cost_config()` + `label_to_fieldname` 列名映射 |
| 同上 `:3046-3051` | 仓库分类 → 公司名映射（USNJ/USTX→美国公司，PL→波兰公司） |

### SQL / 快照（均为只读）

- **Item Group 分布** —— `SELECT IFNULL(NULLIF(custom_shipment_type_to_branch,''),'<空/NULL>'),COUNT(*) FROM \`tabItem Group\` WHERE custom_model_id LIKE 'KS%' GROUP BY 1` → 皮壳 156 / 成品 165 / 半成品 62 / 空+NULL 18（共 401）。
- **物料分布（按前缀）** —— `SELECT SUBSTRING_INDEX(name,'#',1), ig.custom_shipment_type_to_branch, COUNT(*) FROM tabItem JOIN \`tabItem Group\` ig ON ig.custom_model_id=REGEXP_SUBSTR(name,'KS[0-9]+') WHERE name REGEXP '^[A-Z]+BZCP#KS' GROUP BY 1,2` → 见正文表。
- **`Tongtu Shipping Warehouse` 全量** —— `SELECT name,warehouse_classification,processing_cost_name,first_leg_{shell,semi_finished,finished}_freight_name …` → 42 行（FBA 仓 `processing_cost_name=NULL`；海外仓 = 美中 USTX + USFBA 成品头程）。
- **`Logistic Price` 价格表** —— `SELECT DISTINCT logistic_price_list FROM \`tabLogistic Price\`` → 7 个（无 HWC）。
- **BOM 样本** —— `SELECT name,item,is_active,is_default,docstatus,total_cost,operating_cost,raw_material_cost FROM tabBOM WHERE name IN ('BOM-SXBZCP#KS0495-143x84x88-001','BOM-SXBZBCP#KS0495-143x84x88-001','BOM-KS0495-…-003',…)`。
- **BOM 子件** —— `SELECT parent,item_code,qty,amount FROM \`tabBOM Item\` WHERE parent='BOM-SXBZCP#KS0495-143x84x88-001'` → `SXBZBCP#KS0495-143x84x88 × 1 @337.041` + `PPM1500-7D51-SILICONIZED-NEW × 5.55 @55.50`。
- **报表快照（仅用于数据分布/否证）** —— `out/profitability_audit/2026年7月订单_ustx2/en_bom_cost/EN产品BOM成本列表20260202.csv`（70 列；col3=`绍兴发货方式`、col11=`皮壳成本`、col12=`绍兴包装半成品成本`、col13=`绍兴包装成品成本`、col14=`绍兴总成本`；3693 行）。

### 本地复算脚本（scratch，`out/` 已 gitignore）

- `out/sx_ship_probe/bom_cost_list_v2.py`、`out/sx_ship_probe/order_sync.py`（EN 服务器副本，行号与服务器一致）
- `out/sx_ship_probe/q_sx_dist.sql` / `q_all_dist.sql` / `q_ig.sql` / `q_tw.sql` / `q_lp.sql` / `q_boms.sql` / `q_bomitem.sql`
