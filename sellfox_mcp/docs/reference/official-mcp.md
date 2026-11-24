---
okf: v0.1
type: Reference
title: 赛狐官方托管 MCP — 新协议（发现目录 + sf_discover/sf_describe/sf_execute）实测参考
description: api-mcp.sellfox.com/mcp 的当前形态：无状态、两条鉴权路径（子账号 X-MCP-Key 已开通）、371 个业务工具的发现目录、契约分片与 SHA 校验、只读与写能力干探测结论
tags: [sellfox, mcp, reference, ads, auth, catalog]
timestamp: 2026-11-24
---

# 赛狐官方托管 MCP — 操作参考（2026-11 版）

> 决策与可行性背景见 [`docs/research/2026-09-20-sellfox-official-mcp-feasibility.md`](../../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md)。
> 本文只记**当前怎么用、怎么复现**。9 月版的「23 个扁平工具」已作废，见文末变更说明。

---

## 一、端点与传输

| 项 | 值 |
|---|---|
| URL | `https://api-mcp.sellfox.com/mcp` |
| 传输 | `streamable-http`（响应可为 `text/event-stream` 或 `application/json`） |
| 协议版本 | `2025-06-18` |
| 服务端标识 | `{"name":"sellfox-api","version":"1.30.0"}` |
| 会话 | **无状态** —— 不再返回 `mcp-session-id`，每次请求自包含 |

> 2026-09 时服务端是**有状态**的（`initialize` 后必须带 session）。现在不是了；旧结论不要照搬。

### 服务端自带的调用纪律（`initialize` 的 `instructions` 字段原意）

- 不知道 `tool_id` 时用 `sf_discover` 传**完整业务问句**；`original_user_input` 必须**逐字**传入当前用户提问原文，不得摘要/改写。
- `sf_describe` 只按已知 `tool_id` 取契约，不是关键词搜索；契约未变时不要重复调。
- `sf_execute` 的 `params` 只放 `inputSchema` 字段；不得附带 ctx、凭证、URL、SQL 或代码；不得猜测资源 ID 与财务口径。
- 已发布的读写能力都开放，业务权限由上游（赛狐）校验。

---

## 二、鉴权：两条独立路径

| | **路径 A** | **路径 B（子账号，推荐）** |
|---|---|---|
| 请求头 | `X-Sellfox-Client-Id`<br>`X-Sellfox-Client-Secret` | `X-MCP-Key`（单头） |
| 值来源 | 赛狐 API 账号的 App ID / App Secret | 赛狐「MCP管理」为子账号生成的独立 key |
| 状态 | ✅ 可用 | ✅ **2026-11 起已开通**（9 月是 `40027 未启用MCP功能`） |
| 权限模型 | 继承 API 账号 | **与子账号角色一致**：查询角色=只读；写入角色=可改（如调广告预算） |
| 适用 | 服务端脚本 / 自己人 | 个人 Agent（key 可按人签发、可单独重置） |

> 子账号拿到的 key 自带该账号的**数据范围与操作权限**。接进 Agent 前先确认这把 key 是「查询」还是「写入」角色。

### 凭据纪律

- 生产凭证**不进仓库**：`SF_MCP_KEY` 只放 ① 本机用户级 MCP 配置（`~/.claude.json`）② 父仓库 `.env`（gitignored，供脚本读）。
- 脚本一律从环境变量读：`SF_MCP_KEY` / `SF_ID` / `SF_SECRET`。
- 对外只报结构不报数据：店铺名、订单号、金额一律不写进文档或提交。

---

## 三、工具面：3 个元工具 + 371 个业务工具

`tools/list` 只返回 3 个：

| 元工具 | 作用 | 必填 |
|---|---|---|
| `sf_discover` | 从发现目录里找 `tool_id`（可按 domain / platform / operation 收窄） | `original_user_input` |
| `sf_describe` | 按 1–5 个 `tool_id` 取当前契约（含 `inputSchema`、`contract_version`） | `tool_ids` |
| `sf_execute` | 执行一个 `tool_id` | `tool_id` / `params` / `contract_version` |

业务能力都在发现目录里，**实测 371 个**（2026-11-24 全量翻页）：

| 维度 | 取值 |
|---|---|
| domain | advertising / analytics / customer_service / finance / logistics / orders / products / reports / shops |
| platform | amazon / aliexpress / ebay / walmart / wayfair / temu / tiktok / shopee / shopify / ozon / otto / cdiscount / coupang / joom / lazada / mercado(libre) / rakuten / shein / woocommerce / multiplatform / all / custom |
| operation | `read` / `write` |

按名字前缀粗分：**读约 317 / 写约 54**（`edit_/create_/save_/update_/delete_/close_/confirm_/audit_/apply_/cancel_/allocate_/allot_/modify_/mark_/batch_/product_update_`）。
逐条以 `sf_describe` 的 `operation` 字段为准。

业务覆盖（按工具名统计，非实测数据量）：
- **利润** 43 个（`get_profit_report_by_*`、`get_settlement_profit_by_*`、多平台利润）
- **报表** 68 个（SP/SB/SD 小时报表、平台站内报表）
- **订单** 37 个（订单分页/详情、财务收付款、发货相关）
- **店铺** 31 个（各平台店铺/站点列表）
- **库存** 11 个（平台仓全量库存、AWD、FBA/FBM 库存、Temu/沃尔玛库存）
- **广告** 读写各半（SP/SB 活动、广告组、关键词/商品/否定投放）

### 发现接口的硬限制

- `limit` **只能 5–20**，越界返回 `status=failed` +「Business search limit must be 5–20」。
- `domain` 只在**查询命中**时收窄；查询不命中会回退整目录（`retrieval_mode=catalog_fallback`，每页约 211–215 条，需 `next_cursor` 续翻）。
- `candidates` 在回退模式下只给 `tool_id` + `display_name`，不给 domain/operation —— 分类只能靠命名或 `sf_describe`。

---

## 四、调用链与契约分片

```
sf_discover(业务问句) ──► tool_id
        │
        ▼
sf_describe(tool_ids) ──► inputSchema + contract_version
        │                  （大契约会被切成 contract_parts）
        ▼
sf_execute(tool_id, params, contract_version)
```

**契约分片**：`sf_describe` 返回 `contract_parts[]` 时，需按 `part_index` 顺序拼接 `json_fragment`，
再用该组 `sha256` 校验 UTF-8 字节；拼完再 `json.loads` 取 `inputSchema`。
实测 `edit_sp_campaign` 的契约分 3 片、SHA 校验通过。脚本已内置该逻辑。

**版本失配**：`contract_version` 必须来自当前 `sf_describe`；过期会报错，需重新 describe。

---

## 五、能力矩阵（2026-11-24 实测）

只读（代表性抽样，`--smoke-reads` 可复现）：

| 能力 | tool_id | 结论 |
|---|---|---|
| 店铺列表 | `get_shop_page_list` | ✅ `complete`，分页结构 `page_no/page_size/total_count/total_pages/rows` |
| 订单列表 | `get_order_page_list` | ✅ `complete`；**日期必须 `yyyy-MM-dd HH:mm:ss`**（只写日期报 `date_format`） |
| 利润报表（订单维度） | `get_profit_report_by_order` | ✅ `complete`；`begin`/`end` 必填，跨度 ≤31 天 |
| 平台仓全量库存 | `query_platform_warehouse_full_inventory` | ⚠️ `complete` 但默认 0 行 —— 建议带 `shop_id`，或该账号下无平台仓数据 |
| SP 广告活动 | `get_sp_campaign_list` | ✅ `complete`；`shop_id` 必填（schema 标 string，按店铺 id 实际值传） |

写工具干探测（`--probe-writes`，只发空参数，**不产生任何变更**）：

| 样本 | 结论 |
|---|---|
| `create_sp_campaign` / `edit_sb_campaign` / `edit_sp_campaign` / `edit_sp_targeting` / `edit_sp_ad_group` | ✅ `SCHEMA_VALIDATED_OK`（`INVALID_PARAMS`） |
| `save_fbm_package_remark` / `update_fbm_package_detail` | ✅ 同上 |
| `update_custom_report_index` / `delete_oversea_stock_order` | ✅ 同上 |
| `confirm_warehouse_in_orders` / `create_fba_shipping_order` / `apply_fbm_package_track_no` / `product_update_local_info` | ✅ 同上 |

判定口径：收到 `INVALID_PARAMS` + 缺字段清单 ⇒ **鉴权通、路由通、参数校验生效**；
若收到 `40027` / 401 / 403 则是 key 未开通或权限不足。本次 11+3 个样本全部为前者，**无 40027**。

> 干探测证明「写通道是通的」，**不等于**「真实修改会成功且副作用可控」。
> 真实写测试另需指定测试店铺 + 可回滚字段 + 明确授权，详见第七节。

**零变更证据**：干探测前后对同一店铺 `get_sp_campaign_list`（20 条）做快照，
比对 `campaignId + budget + state`，两次完全一致。

---

## 六、坑（实测踩到的）

1. **`page_size` 不是「随便给个整数」**：`get_sp_campaign_list` 传 3 报 `anyOf` 校验失败；
   广告类工具按描述是 **20–50**，低于 20 会被拒。
2. **订单日期是 datetime 不是 date**：`yyyy-MM-dd` 报 `date_format`，必须 `yyyy-MM-dd HH:mm:ss`。
3. **一次 `sf_describe` 多 id 会分页**：批量 3 个 id 可能返回 `status=partial` + `next_cursor`，
   要顺着 cursor 取完；单 id 也可能因契约分片而 `partial`。
4. **`field_errors` 的 `path` 可能是空串**：错误定位以 `message` 和 schema 为准，别只信 path。
5. **目录回退不是匹配结果**：`catalog_fallback` 只是把整目录摊开，不代表用户要执行里面的工具。
6. **无状态但别并发打满**：上游仍限流（约 1 req/s），脚本默认串行。

---

## 七、写能力干探测的方法与边界

目的：判断写工具是**真接后端**还是空壳/未授权，同时保证**零副作用**。

做法（脚本 `--probe-writes` 已固化）：

1. `sf_describe` 取契约；若 `required` 为空 → **跳过**（空参数可能真的执行，不安全）。
2. 有必填字段时，才发 `params: {}` —— 必然被 schema 拒绝，不可能触达业务写逻辑。
3. 判据：`INVALID_PARAMS` ⇒ 通；`40027`/401/403 ⇒ 权限问题；其他 ⇒ 记录原样。
4. 前后用只读工具做快照比对，确认无变更。

**边界**：这不验证「参数正确时是否成功」「是否幂等」「失败是否回滚」。
真要验证，只能选**明确指定的测试店铺**、改一个可回滚字段、当场改回，并取得显式授权。

---

## 八、与自建 `sellfox-api-proxy` 的分工

| | 官方 MCP | 自有 `sellfox-api-proxy` |
|---|---|---|
| 位置 | 赛狐服务端 | 我们 VPS `api.vilavi.cn/sellfox` |
| 鉴权 | 赛狐签发的子账号 key（客户端持有） | 自签 `Bearer sk-...`（钉钉 OIDC），客户端拿不到赛狐凭证 |
| 覆盖面 | 371 个业务工具（含利润/结算/多平台） | catch-all，任意赛狐公开端点（443 篇文档） |
| 权限控制 | 跟随子账号角色 | per-key 限流 / 账号映射 / 可吊销 |
| 适合 | 个人 Agent 分析（本机 Claude Code） | 多人 / 团队自动化 / 需要审计与吊销 |

**结论**：两条并存。个人分析优先官方 MCP（工具面更宽、开箱即用）；
团队与需要凭证隔离、限流、审计的场景走 proxy。两者不冲突，数据口径一致（同一上游）。

---

## 九、未决

| # | 问题 | 怎么解 |
|---|---|---|
| 1 | 真实写执行是否成功、副作用是否可控 | 指定测试店铺 + 可回滚字段 + 显式授权后验证；**当前不做** |
| 2 | 契约分片是否有长度上限 / 是否所有大工具都分片 | 继续观察；脚本已自动拼接并校验 SHA |
| 3 | 371 个工具的 operation 字段是否与命名一致 | 抽样 describe 核对；命名前缀仅作粗分 |
| 4 | `query_platform_warehouse_full_inventory` 0 行是权限还是数据为空 | 带 `shop_id` 再试，或与后台页面比对 |

---

## 附：9 月版结论的变更说明

- 旧：23 个扁平工具（13 只读 + 1 非破坏性写 + 9 广告写）；有状态；路径 B `40027` 未启用。
- 新（2026-11-24）：3 个元工具 + 371 个业务工具；无状态；路径 B 已开通且按子账号角色授权。
- 旧脚本的 `--call` / 白名单逻辑已不适用，`scripts/probe_mcp.py` 已重写为 `--discover/--describe/--execute/--smoke-reads/--probe-writes`。

## 相关

- [`sellfox-api-proxy/`](../../../sellfox-api-proxy/) — 自有 VPS 代理
- [`SELLFOX_API/docs/api-reference/`](../../../SELLFOX_API/docs/api-reference/) — 443 篇公开端点文档
- [可行性调研](../../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md) — 9 月决策背景
