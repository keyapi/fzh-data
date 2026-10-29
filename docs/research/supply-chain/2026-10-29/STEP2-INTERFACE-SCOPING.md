---
okf: v0.1
type: Reference
title: 第二步：supply-facts 接口限域、filters 白名单与分页契约
date: 2026-10-29
owner: claude-worker
status: implemented-locally-tests-green; test-station deploy pending
scope: read-only; no production deploy; no business data writes
---

# 第二步：接口限域与分页

> 依据：`EN-CHAIN-REVIEW-2026-10-29.md` 第 6 项、`JACK-EN-REQUIREMENTS-2026-10-29.md` §1.3。
> 复用 #314 的 supply-facts 计算与原子导出；**没有另建一套平行算法**。

## 1. 接口

```text
GET/POST /api/method/key_test.supply_facts.get_supply_facts
参数：filters = JSON object（推荐）
     或 Frappe 会拆成同名字段；未在 filters 中的顶层参数一律报错
```

### 1.1 完整 filters 示例

```bash
# 单 SO（推荐写法：全部放在 filters）
curl -G 'https://<site>/api/method/key_test.supply_facts.get_supply_facts' \
  --data-urlencode 'filters={"sales_order":"SO-26-00103","limit":50}'

# 单行 + 已发完行
filters={"sales_order":"SO-26-00103","so_line":"SOI-...","include_delivered":1}

# SKU / 客户码
filters={"item_code":"CENCord995-DKGrey-97","limit":100}
filters={"customer_item_code":"TT0031038K0062927","limit":100}

# 仓库 / 阶段（阶段是事实层过滤）
filters={"sales_order":"SO-26-00103","warehouse":"美中-FZH-DANEEY","stage":"in_production"}

# 第二页
filters={"sales_order":"SO-26-00103","limit":50,"offset":50}
```

### 1.2 filters 白名单与语义

| filter | 类型 | 语义 | 影响分页/总数 |
|---|---|---|---|
| `sales_order` | string | SO 名称；单 SO 请求只返回该 SO | 是（行选择） |
| `so_line` | string | `Sales Order Item.name`；单行精确过滤（SQL 层） | 是 |
| `customer` | string | SO 客户 | 是 |
| `item_code` | string | SO 行物料编码 | 是 |
| `customer_item_code` | string | SO 行客户物料号 | 是 |
| `warehouse` | string | **SO 行目标仓**（`Sales Order Item.warehouse`）；不是生产组件仓/目的仓 | 是 |
| `stage` | string | 事实层 `stage_balances` / `availability_schedule` 的阶段过滤；不改变行分页 | 否（只裁剪事实行） |
| `from_date` / `to_date` | date | SO `transaction_date` 范围 | 是 |
| `as_of` | date | 仅支持当前快照；历史日期拒绝 | 否 |
| `include_delivered` | bool | 是否包含已发完行；默认 false | 是 |
| `limit` | int | 每页行数；默认 500，最大 2000 | 分页 |
| `offset` | int | 起始行；≥0 | 分页 |

- **未知 filter**：`Unknown filter(s): ...; allowed: ...`，直接报错。
- **顶层误传**（如 `sales_order=...` 不放进 `filters`）：`Unknown parameter(s): ...; wrap supported filters in filters`，直接报错，不再静默扩大为全量。
- Frappe 分发注入的 `cmd` / `csrf_token` / `_` 由服务端忽略；其它顶层参数仍拒绝。
- 当前 `implementation_version = key_test.supply_facts@2026-10-29.1`；接口/分页行为变更必须 bump，混合版本继续拒绝。
- `stage` 只接受契约中的阶段值（`not_planned` / `in_production` / `produced_pending_dn` / `shipped_in_transit` / `arrived_not_sellable` / `delivered_sellable` / `cancelled` / `returned` / `draft_dn` / `unknown` / `over_produced`）。
- 日期时间仍按契约：`as_of` 只允许当前快照；历史 `as_of` 由服务端拒绝。

## 2. 分页契约

响应新增：

```json
{
  "applied_filters": {"sales_order": "SO-26-00103"},
  "pagination": {
    "limit": 50,
    "offset": 0,
    "returned": 50,
    "total": 173,
    "next_offset": 50,
    "next_cursor": "SOI-...",
    "exhausted": false,
    "partial": true,
    "termination_reason": "page_limit",
    "sort": ["so", "so_line"],
    "unique_key": "so_line"
  },
  "manifest": {
    "scope": {"sales_order": "SO-26-00103", "limit": 50, "offset": 0},
    "pagination": { "...": "同上" },
    "truncated": true,
    "termination_reason": "page_limit",
    "partial": true,
    "partial_reasons": ["external sources not integrated: ..."]
  }
}
```

规则：

- `total` = 过滤后、分页前的 **SO 行数**（不是 SO 数）。
- 排序固定 `so, so_line`；唯一键 `so_line`（`Sales Order Item.name`），跨页不重不漏。
- `exhausted=true` 表示分页已取完；`pagination.partial` 只表示**本页是否被 limit 截断**（`page_limit`）。
- `manifest.partial` 只表示**业务来源是否完整**（权限受限、通途 PO/入库/目的仓未接入等）；**即使 `exhausted=true`，`manifest.partial` 仍可为 true**。
- `next_cursor` 是本页最后一行的 `so_line`；服务端当前仍以 `offset` 为准（keyset 游标可作为后续优化，不改变本页语义）。
- `manifest.truncated` / `manifest.termination_reason` 与分页一致；导出程序仍用自身的 `page_limit` 标记作为最终文件级标记。

### 2.1 导出器：所有模式统一消费分页

- `--all` / `--so` / `--codes` **都走同一个 `_paginate`**，直到 `pagination.exhausted=true`；不再对单 SO/客户码只请求一次。
- 每页检查 `next_offset` 必须前进、`so_line` 唯一键不得跨页重复；空页未 exhausted 视为错误。
- 旧服务端无 `pagination` 时回退到 `rows < page_size`，但仍保留 200 页上限与 `page_limit` 标记。
- `--page-size` 限制 1..2000；单 SO/客户码 501 行会请求 500+1 两页，最终 `truncated=false`、`termination_reason=exhausted`。

## 3. 单 SO / 订单行语义

- `filters.sales_order="SO-…"` 在 SQL 层限制 SO；`so_line` 在 SQL 层限制行。
- 单 SO 请求的 `lines`、`stage_balances`、`milestones`、`availability_schedule`、`links` 只来自该 SO。
- `warehouse` 是**SO 行目标仓**；`stage_balances` 行仍保留实际仓库（可能是生产/组件仓）；两者不混同。
- `stage` 是事实层过滤：行的 `stage_balances`/`availability_schedule` 被裁剪，`pagination.total` 仍是行级总数；`applied_filters.stage` 会回显。
- 不再有“先 limit 再按 so_line 过滤”的顺序问题；`so_line` 已进入 SQL。

## 4. 错误行为

| 请求 | 结果 |
|---|---|
| `filters={"bogus":1}` | `Unknown filter(s): bogus; allowed: ...`（ValidationError） |
| `?sales_order=SO-...`（顶层） | `Unknown parameter(s): sales_order; wrap supported filters in filters` |
| `cmd` / `csrf_token` / `_`（Frappe 注入） | 忽略，不报错 |
| `filters={"limit":0}` / `limit>2000` | `limit must be between 1 and 2000` |
| `filters={"offset":-1}` | `offset must be >= 0` |
| `filters={"stage":"foo"}` | `Unknown stage: foo` |
| `filters={"as_of":"2026-10-01"}` | 历史 as_of 拒绝（现有保护） |
| 无匹配 / 全部受限 | 空行 + `coverage`/`external_sources`/`empty_reason` + `pagination(exhausted=true)` + `manifest.partial=true` |

## 5. 版本与原子导出（保持不变）

- `schema_version` / `rule_version` / `implementation_version` / `as_of` 的混合批次拒绝逻辑不变。
- `EN_API/supply_facts_export.py` 仍先写临时目录，校验后原子 rename；失败不切换 `latest.json`，旧成功版本保持可读。
- 新增分页字段不改变导出器的批次合并语义；导出仍按 `lines` 数翻页，直到 `rows < page_size`。

## 6. 代码与测试

改动文件：
- `key_test/key_test/supply_facts.py`
  - 新增 `_normalize_filters` / `_pagination` / `FILTER_KEYS` / `STAGE_VALUES` / 默认与最大 limit；
  - `get_supply_facts(filters=None, **kwargs)`：拒绝未知顶层参数/未知 filter；
  - `load_lines`：`so_line` 进入 SQL、返回 `total_lines`；`limit/offset` 明确；
  - 响应新增 `applied_filters`、`pagination`；`manifest` 新增 `pagination`/`truncated`/`termination_reason`/`partial_reasons`；
  - `stage` 事实层过滤。
- `EN_API/supply_facts_export.py`
  - 新增 `_paginate`：所有模式统一按 `pagination.exhausted/next_offset` 翻页；
  - 校验页前进、`so_line` 唯一键、空页/无前进；保留 200 页上限与 `page_limit`；
  - `--page-size` 限 1..2000。
- `key_test/key_test/tests/test_supply_facts.py`
  - 新增未知 filter/顶层参数、单 SO/单行、两页不重不漏、分页元数据、endpoint 回显、越界页、Frappe `cmd` 注入等测试。
- `key_test/key_test/tests/test_supply_facts_dispatch.py`
  - 真实 `frappe.call` / `get_newargs` 分发测试（本地无 Frappe 时 skip；在 bench 上运行）。
- `supply_chain_visibility/tests/test_supply_facts_export.py`
  - 501 行单 SO / 客户码导出、页前进/唯一键/page_limit、旧/新 implementation_version 混合拒绝。
- fzh-data 镜像同步：
  - `supply_chain_visibility/key_test/key_test__supply_facts.py`
  - `supply_chain_visibility/key_test/key_test__tests__test_supply_facts.py`

测试结果（本地，只读）：

```text
key_test full: 118 passed, 3 skipped
  （dispatch 三项因本地未安装 Frappe 跳过；bench 上执行：）
  bench --site <site> run-tests --module key_test.tests.test_supply_facts_dispatch

fzh-data supply_chain_visibility: 90 passed + 5 subtests
  （含 501 行单 SO/客户码导出、分页越界、排序、版本混合拒绝）
```

真实 Frappe 分发探针（测试站，只读、未部署）：用测试站 `frappe.call/get_newargs` 调新代码的 `_normalize_filters`：
- 携带 `cmd` / `csrf_token` / `_` 的合法请求：返回 `sales_order=SO-TEST`、`limit=500`，未被拒绝；
- 顶层误传 `sales_order`：被拒绝（无 site 上下文的探针抛 `RuntimeError: object is not bound`；在 bench site 上应抛 `frappe.ValidationError`，见 `test_supply_facts_dispatch.py` 的 endpoint 用例）。

## 7. 未解决 / 下一阶段

1. 测试站部署与普通角色端到端验证尚未做（需用户授权部署/重启）；生产未部署。
2. `warehouse` 仍定义为 SO 行目标仓；若业务要求按 `stage_balances.warehouse` 过滤，需新增 `stage_warehouse` 并单独评审。
3. 通途 PO/入库/目的仓来源仍未接入；`manifest.partial=true` 保持。
4. 导出器仍有 200 页上限；分页字段已可供未来改为 `next_offset`/`next_cursor`。
5. 第三步（生产证据分层）与第四/五/六步尚未开始，待本阶段审核通过。
