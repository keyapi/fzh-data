---
okf: v0.1
type: Reference
title: 第二步：supply-facts 接口限域、filters 白名单与分页契约
date: 2026-10-29
owner: claude-worker
status: functional-acceptance-passed; permission-acceptance-pending
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
- **覆盖数按身份去重**：`manifest.coverage.sales_orders` / `so_lines` 用唯一 SO / SO 行集合；`so_lines_total` 用各 scope 的范围总数（不按页累加）；DN 从 links 的 source/target 身份去重；Shipment 只统计 `target_is_record=true` 的已匹配记录，`target_is_record=false` 的运单号占位不计。
- **分页连续性校验**：每页校验 `limit/offset/returned/total` 与实际一致，`next_offset == offset + rows`，跨页 `total` 不变，`exhausted` 时唯一行数必须等于 `total`；不一致直接失败，不写新版本、不切换 `latest`。

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
- `key_test/key_test/tests/dispatch_support.py`
  - 导入守卫：只有 `ModuleNotFoundError.name == "frappe"` 才返回 skip；业务模块导入错误继续抛出。
- `supply_chain_visibility/tests/test_supply_facts_export.py`
  - 501 行单 SO / 客户码导出、覆盖数去重、分页连续性/总数对账、
    异常分页保留 old latest 指针、排序、版本混合拒绝；
  - `target_is_record` 仅运单号/匹配 Shipment/混合重复链接的覆盖数测试。
- fzh-data 镜像同步：
  - `supply_chain_visibility/key_test/key_test__supply_facts.py`
  - `supply_chain_visibility/key_test/key_test__tests__test_supply_facts.py`

测试结果（本地，只读）：

```text
key_test full: 121 passed, 3 skipped
  （dispatch 三项因本地未安装 Frappe 跳过；bench 上执行：）
  bench --site <site> run-tests --module key_test.tests.test_supply_facts_dispatch

fzh-data supply_chain_visibility: 98 passed + 5 subtests
  （含 501 行单 SO/客户码导出、覆盖数去重、分页连续性/总数对账、
   异常分页保留 old latest 指针、排序、版本混合拒绝、Shipment 占位排除）
```

真实 Frappe 分发探针（测试站，只读、未部署）：用测试站 `frappe.call/get_newargs` 调新代码的 `_normalize_filters`：
- 携带 `cmd` / `csrf_token` / `_` 的合法请求：返回 `sales_order=SO-TEST`、`limit=500`，未被拒绝；
- 顶层误传 `sales_order`：被拒绝（无 site 上下文的探针抛 `RuntimeError: object is not bound`；在 bench site 上应抛 `frappe.ValidationError`，见 `test_supply_facts_dispatch.py` 的 endpoint 用例）。

## 7. 未解决 / 下一阶段

1. 测试站部署已完成（2026-10-29 12:32 重启，app `dccd6e8`），功能验收见第 8 节；**权限验收待完成**（受限角色真实 HTTP 会话未验证，缺凭证、未获豁免，不作为通过项）；生产未部署。
2. `warehouse` 仍定义为 SO 行目标仓；若业务要求按 `stage_balances.warehouse` 过滤，需新增 `stage_warehouse` 并单独评审。
3. 通途 PO/入库/目的仓来源仍未接入；`manifest.partial=true` 保持。
4. 导出器仍有 200 页上限；分页字段已可供未来改为 `next_offset`/`next_cursor`。
5. 第三步（生产证据分层）与第四/五/六步尚未开始，待本阶段审核通过。

## 8. 测试站验收记录（2026-10-29）

**第二步状态：功能验收通过，权限验收待完成。** 第 1/2/4/5 项通过；第 3 项 Guest 拒绝通过，受限角色真实 HTTP 会话尚未验证，**未获得豁免，不作为通过项**。在权限验收完成前，第二步不作为生产发布验收依据。

### 8.1 环境与提交

| 项 | 值 |
|---|---|
| key_test 本地 | `feature/supply-facts-delivery-mvp` @ `dccd6e8`，工作区干净 |
| 测试站 key_test | `apps/key_test` @ `dccd6e8`；回滚 tag `step2-pre-sync-20261029` 保留 |
| fzh-data | `feature/supply-facts-delivery-mvp` @ `588a92c9` |
| 镜像一致性 | `key_test__supply_facts.py` / `key_test__tests__test_supply_facts.py` / `dispatch_support.py` 与 key_test 源文件逐字节一致 |
| 测试站重启 | 2026-10-29 12:32:22（+0800），web worker 已加载新代码 |
| HTTP 实现版本 | `key_test.supply_facts@2026-10-29.1`（12/12 次采样一致） |

### 8.2 命令与通过/失败/跳过数量

| 范围 | 命令 | 结果 |
|---|---|---|
| key_test 全量 | `uv run python -m pytest key_test/tests -q` | **121 passed, 3 skipped** |
| supply_chain_visibility 全量 | `uv run python -m pytest supply_chain_visibility -q` | **98 passed, 5 subtests passed** |
| 导出器（fzh-data） | `uv run python -m pytest supply_chain_visibility/tests/test_supply_facts_export.py -q` | **21 passed** |
| Frappe 真实分发 | `sudo -n -u frappe /usr/local/bin/bench --site erpnext.vilavi.cn run-tests --module key_test.tests.test_supply_facts_dispatch` | **Ran 3 tests, OK（0 skipped）** |

### 8.3 HTTP 参数与分页（只读）

| 检查 | 结果 |
|---|---|
| 合法 GET / POST（`SO-26-00030`, `limit=2`） | 200；`total=11`，返回 2 行 |
| 未知 filter `{"bogus":1}` | 417 `ValidationError` |
| 非法 stage `{"stage":"foo"}` | 417 `ValidationError` |
| 顶层误传 `?sales_order=...` | 417 `ValidationError` |
| `limit=0` / `offset=-1` | 417 `ValidationError` |
| 分页遍历（`limit=2`） | 6 页：2/2/2/2/2/1；唯一 `so_line` **11/11**，无重复；`next_offset` 2→4→6→8→10→null；末页 `exhausted=true`、`partial=false`；每页 `total=11` |
| 越界页 `offset=21` | 200；`total=11`、`returned=0`、`exhausted=true`、`empty_reason=offset_out_of_range` |
| 排序/唯一键 | `sort=["so","so_line"]`、`unique_key="so_line"` |
| Guest（无认证） | 403 `PermissionError` |

### 8.4 完整导出与覆盖数

- **SO-26-00030**（`run-20261029_133217-f5d80c4ba0e1`）：
  - 行数：`lines=11`、`stage_balances=11`、`milestones=22`、`availability_schedule=11`、`links=11`；
  - 覆盖：`sales_orders=1`、`so_lines=11`、`so_lines_total=11`、`delivery_notes=0`、`shipments=0`；
  - `manifest.truncated=false`、`termination_reason=exhausted`；
  - JSON 行数、Excel 行数/表头、manifest `counts`、文件 SHA-256 全部一致。
- **SO-26-00026**（覆盖数实证，`run-20261029_133317-c27857b4a0f1`）：
  - `lines=3`、`delivery_notes=3`、`shipments=1`（`target_is_record=true`），运单占位 0；
  - links：`order_line=3`、`planned_by=3`、`produced_by=5`、`tracking_number=2`、`shipped_by=3`、`waybill=1`；
  - JSON/Excel/manifest/hash 校验全部通过。
- 运单占位不计入 Shipment：本地单测 `test_merge_coverage_waybill_only_is_not_a_shipment`、`test_merge_coverage_matches_only_real_shipments_and_dedupes` 通过；本次真实数据中未出现未匹配运单占位。

### 8.5 失败保护（本地模拟，不改测试站业务数据）

| 场景 | 结果 |
|---|---|
| HTTP 500 请求失败 | `rc=1`，旧 `latest.json` 不变，无新 run 目录 |
| 分页 `next_offset` 断裂 | 同上 |
| 批次 `implementation_version` 混合 | 同上（`BatchVersionError`） |

### 8.6 §4.3 受限角色 HTTP

- **Guest 拒绝：通过**（403 `PermissionError`）。
- **受限角色真实会话：尚未验证**。缺少受限用户凭证；未获得豁免，**不作为通过项**。管理员（System Manager）与 Guest 的结果不能替代普通角色验证。
- **剩余验收条件**：使用已有受限用户的合法会话验证权限 —— 确认无权数据及关联信息不泄露、`manifest.partial` 与权限提示正确；**不要为测试扩大其权限**。
- 在权限验收完成前，第二步**不作为生产发布验收依据**。

### 8.7 产物与边界

- 证据（`EN_API/out/` 已 gitignore，不提交）：`EN_API/out/supply_facts/_acceptance/http_admin.json`、`export_and_failure_verify.json`、`verify_exports_failures.py`；导出 run 目录见 8.4。
- 未修改测试站业务数据；未部署生产；未合并 main；未推进第三至第六步。
