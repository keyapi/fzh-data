# 客户物料「特殊标记」special_mark（碎海绵）— 交接

> **状态（2026-10-10）**：**生产已执行并回读通过** ✅
> 需求：把「2026年度FBA订单（新）」里出现过的通途SKU 对应的 EN 物料，在其**客户物料子表**上打
> `special_mark = 碎海绵`。子表原本没有该字段 → 先加字段（delivery_plan fixtures），再批量写值。

---

## 1. 口径

| 项 | 值 |
|---|---|
| 数据源 | `EN_API/数据源/2026年下单表.xlsx` → 工作表「**2026年度FBA订单（新）**」（表头在**第 2 行**，「通途SKU」= 第 7 列） |
| 映射 | 通途SKU == `Item.customer_items` 子表（doctype **`Item Customer Detail`**）的 **`ref_code`**（=客户物料号，全局唯一、大小写不敏感） |
| 写入 | 命中的子表行 `special_mark = 碎海绵` |

**REST 取子表口径**：`GET /api/resource/Item?filters=[["Item Customer Detail","ref_code","in",[…]]]` **可用**（子表直接 list 会 403，但按子表**过滤父单据**可以）。
⚠️ 两个坑：① 按子表过滤时父单据的 `customer_items` 返回 **null**，要再单独 `GET /api/resource/Item/<code>` 取行；
② 同一物料命中多行会在结果里**重复出现**，必须先对物料名去重再取文档，否则行数翻倍。

## 2. 结果：47 个 SKU → 47 个物料 / **54 条子表行**

- 表内 **115 行订单 / 47 个唯一通途SKU**，**47 个全部命中**。
- **7 个物料各有 2 条命中行**（美国公司+欧洲公司）：KS0002-DL-100-DEEPBLUE、KS0002-DL-100-IVORY、
  KS0195-DMNJB-58-GREY、KS0211-KJB-60-BEIGE、KS0211-KJB-90-BEIGE、KS0230-WGMSRKQCLG-60-WHITE、
  KS0479-KQCLXGSDSMZWB-74x48x15-WHITE。
- 两个不相交族群：`FoamFBA…/Foam…` 码（`KS0524-HLR-*` 碎海绵款，7 个物料）；`BNUSFBA-Velvet-…/TT…/CEN…` 码（常规款，40 个物料）。
- 明细：`EN_API/out/special_mark_stats_20261010_091203.csv`（含 item_code / row_name / ref_code / customer_group）。

## 2b. 范围修正（2026-10-10，生产已执行 ✅）

首轮把工作表出现的**全部 47 SKU / 54 行**都打了碎海绵；业务确认只应针对**三角 / 平条靠枕**，故做了收敛：
- **保留**（item_group 含「三角」或「平条」）= 三角靠枕20 + 三角靠枕(碎海绵款)8 + 三角靠枕无扣5
  + 三角带圆柱靠枕3 + 平条靠枕6 = **42 行 / 40 物料**。
- **清除**（范围外）= **12 行 / 7 物料**：沙发床头靠枕、可盘腿办公椅垫、软包墙围、侧睡两用楔形枕、
  手臂支撑枕、可调节趴睡枕。
- 工具：`set_special_mark.py fix-scope [--yes]`（先落快照 `out/special_mark_scopefix_snapshot_*.json`）。
- **独立 SQL 回读**：全库 `special_mark=碎海绵` = **42 行，越界 0**。

## 3. 字段（必须走 app fixtures，落 **delivery_plan**）

`Item Customer Detail-special_mark`，**Data**，标签「特殊标记」，`insert_after=ref_code`。
- 改测试机 `apps/delivery_plan/{hooks.py, fixtures/custom_field.json}`（**最小追加**，未跑 export-fixtures）。
- 片段与部署步骤见同目录 [`fixtures_snippet.md`](fixtures_snippet.md)。
- **测试机验证**：删字段 → `bench migrate` → 从 fixtures 重建成功（`special_mark varchar(140)`）。
- **生产**：用户部署 delivery_plan + `bench migrate`（2026-10-10），只读确认 `Custom Field` 记录与 DB 列都存在。

## 4. 生产执行记录（2026-10-10）

- 统计 → 用户确认 → dry-run（54 行现值全空）→ 快照 → 写入 → 独立回读。
- 快照（可回滚依据，写前 all-empty）：`EN_API/out/special_mark_snapshot_20261010_091404.json`。
- 写入：**zz_ Server Script（`script_type=API`）** 逐行 `frappe.db.set_value("Item Customer Detail", <row name>, "special_mark", "碎海绵")` → `frappe.db.commit()`。
- **独立回读（只读 SQL 探针，不走 REST 子表 meta）**：非空 `special_mark` 行 = **54**，与目标 **完全一致（0 缺 0 多）**，取值唯一 = 碎海绵。
- **zz_ 残留 = 0**（用完即删，已复查）。
- ⚠️ `Version.owner` = PROD key 所有者（高琪），非实际动手人。

## 5. 工具

`EN_API/item_customer_special_mark/set_special_mark.py`（默认 `--env prod`）：
```
python set_special_mark.py stats      # 只读盘点 → out/special_mark_stats_*.{csv,json}
python set_special_mark.py dry-run    # 只读打印 现值→目标
python set_special_mark.py apply --yes  # 快照 + zz_ 写入 + REST 回读(注意子表 meta 缓存)
python set_special_mark.py verify     # 只读回读
python set_special_mark.py rollback --snapshot <path> --yes   # 按快照还原
```
> 回读建议用**只读 zz_ SQL 探针**（`SELECT ... FROM \`tabItem Customer Detail\``）——REST 子表可能因 meta 缓存不带出 `special_mark`。

## 6. 回滚

- 数据：`rollback --snapshot out/special_mark_snapshot_20261010_091404.json --yes`（值为空即清空）。
- 字段：生产删 `Custom Field` 记录 `Item Customer Detail-special_mark` + migrate；或 revert app 提交后 migrate。

## 7. 坑（都踩过）

1. **REST 子表 meta 缓存**：字段已建、DB 列已在，但 `GET /api/resource/Item/<code>` 的 `customer_items` 行里**看不到** `special_mark` → 不能据此判定「没建列」。判列要用 SQL。
2. 按子表过滤父单据会**重复返回**同一物料（每个命中行一条）→ 必须先按物料名去重。
3. 测试机是**陈旧部分克隆**：这 47 个 SKU 在测试机 0 命中 → **数据只能写生产**。
4. Server Script REST 路径里的 `Server Script`（含空格）**必须 URL 编码**（`Server%20Script`），否则 `InvalidURL`。
   （曾因此：部署+写入成功但 `finally` 删脚本报错 —— 写入已落库，需独立回读确认。）

## 8. 待办 / 未决

- 是否要在**销售订单导入**环节回填/利用该标记（本轮只打标，未接任何下游逻辑）。
- `是否皮壳=海绵` 的 3 行（TT0031…，备注「外协海绵做好后发绍兴工厂包装」）与 `FoamFBA…`（KS0524 碎海绵族）
  是两种「海绵」概念；本轮按用户决定**不区分，全部 47 个 SKU 都打标**。
