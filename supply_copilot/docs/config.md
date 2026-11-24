---
okf: v0.1
type: Reference
title: 版本化默认配置 supply-config/v1
description: 补货与需求协同默认参数的加载/校验/哈希/来源说明，含文件格式、示例、版本规则与回退
tags: [supply-copilot, config, defaults, governance]
---

# 版本化默认配置 `supply-config/v1`

参数口径来自 `decision-defaults.md`（2026-11-24，状态 `proposed-not-activated`）。
本层**只提供配置对象与校验**：`decide.py` / `refresh.py` / 页面**尚未消费**它，
加载配置不改变任何决策结果。

## 1. 命令（只读）

```bash
uv run python -m supply_copilot config show                 # 全部参数：值/来源/范围
uv run python -m supply_copilot config validate             # 校验内置默认，输出 JSON 摘要
uv run python -m supply_copilot config hash                 # 内容哈希（规范 JSON 的 sha256）
uv run python -m supply_copilot config validate --config my.json
```

`show` 的来源列：`default`（内置默认）/ `file`（--config 覆盖）/ `override`（程序化覆盖）。

## 2. 文件格式

```json
{
  "schema_version": "supply-config/v1",
  "config_version": "cfg-2026-11-24.1",
  "scope": {"branch": "USNJ"},
  "values": {
    "review_period_R": 10,
    "moq": {
      "value": 120,
      "scope": {"branch": "USNJ", "sku": "KS0001", "warehouse_pool": "美东USNJ",
                "physical_form": "成品", "uom": "个",
                "period": ["2026-11-01", "2026-11-30"]},
      "expires_at": "2026-12-01",
      "reason": "供应商合并批次"
    }
  }
}
```

- 顶层只允许 `schema_version` / `config_version` / `scope` / `values`，多一个键即拒绝。
- `values` 里未出现的参数用默认值，计入 `defaulted`；未知参数拒绝并给近名建议。
- 条目可为裸值（继承文件级 `scope`）或包装对象 `{value, scope, effective_at, expires_at, reason, evidence, author, approver}`。
- **作用域**：`SKU 例外 > 分公司×商品分型 > 分公司 > 全局`（`scope_rank`）；未匹配回上层；
  未知事实**不通过继承变成 0**。SKU 例外必须同时带 `warehouse_pool` / `physical_form` / `uom` / `period`。
- **受保护硬约束**（`auto_order` / `write_en_business` / `allow_self_approval` / `unknown_as_zero`）
  恒为 `false`，配置文件中出现即拒绝——管理员也不能解除。

## 3. 参数摘要（49 项）

数值全部来自 `decision-defaults.md` 默认值列。`null` = 明确不设约束。

| 组 | 键 | 默认 | 允许范围 / 枚举 | 作用域 |
|---|---|---|---|---|
| 硬约束 | `auto_order` `write_en_business` `allow_self_approval` `unknown_as_zero` | `false` | 只允许 `false` | 仅默认层 |
| 分型 | `segmentation_basis` | `frozen_abc_xyz` | `frozen_abc_xyz` / `unknown` | 全局/分公司/分型 |
| | `abc_breaks` | 累计 0.80 / 0.95 | 两个 0–1 严格递增分界 | 分公司/分型 |
| | `xyz_basis` | trained_pattern_labels + smooth/intermittent/lumpy | 方法枚举 | 分公司/分型 |
| 服务 | `service_beta_target` | A .95 / B .90 / C .85 / D .90 | 0.80–0.99 | 分公司/分型 |
| | `service_alpha_target` | `null`（不设硬门槛） | null 或 0.80–0.99 | 分公司/分型 |
| | `quantile_preset` | balance：A q95 / B q90 / C q85 / D q85 | 仅 q85/q90/q95 | 分公司/分型/SKU |
| | `q95_downgrade_gate` | 观察 2–4 次；改善 10–30%；库存比 1.5；一次降 1 档 | 见 defaults.json | 分公司/分型 |
| | `hard_service_infeasible` | 不承诺硬 β；网格 β .90/.95/.99 × L 60/90/120 × R 7/30 | 冻结网格 | 全局/分型 |
| 策略 | `inventory_policy` | `order_up_to_weekly` | order_up_to_weekly / rop / proven_demand / manual_observe | 分公司/分型 |
| | `review_period_R` | 7 日 | 1–30 | 分公司/分型 |
| | `protection_period` | `L+R` | 仅 `L+R` | 分公司/分型 |
| | `safety_stock_method` | `protection_period_quantile` | 三种方法 | 分型 |
| | `history_fallback` | 短史 12 月 → D 档 | 6–24 月 | 分型/SKU |
| 约束 | `hard_budget` | `null` | null 或 ≥0 金额 | 分公司 |
| | `soft_budget_warning` | 金额/数量比 1.20；阈值 10–100% | 见 defaults.json | 分公司/分型 |
| | `moq` / `order_multiple` | `null` / `null`（自有工厂无 MOQ；不凑箱） | null 或 ≥0 / ≥1 | 分公司/SKU/供应商 |
| 交期 | `lead_time_quantile` | 端到端 p90、自然日 | 0.50–0.95 | 分公司/路线/分型 |
| | `lead_time_evidence` | 回看 12 月、≥20 条；兜底情景 60/90/120 天 | 6–24 月；10–50 条 | 分公司/路线 |
| | `eta_unknown` / `po_on_time` | `true` / 三态口径 | 三态受保护口径 | 全局/分公司 |
| 新鲜度 | `inventory_refresh` | 每日 05:17 快照、05:45 检查、Asia/Shanghai | 每日 1–24 次；宽限 15–120 分 | 分公司 |
| | `demand_recommend_refresh` | 周一 06:00；1–14 日间隔；事件按需 | 见 defaults.json | 分公司/分型 |
| | `inventory_age` | ≤24h 可用 / >24h WARN / >48h HOLD | ok≤warn<hold | 分公司 |
| | `forecast_age` | ≤7d / >7d WARN / >14d HOLD | ok≤warn<hold | 分公司/分型 |
| | `so_evidence_age` | ≤7d / >7d WARN / >14d HOLD（证据龄按抽取覆盖时点） | ok≤warn<hold | 分公司 |
| | `critical_unknown` / `readiness` | `hold` / `research` | 枚举 | 全局/分公司 |
| 身份 | `operator_scope` | 空列表 = 拒绝，禁通配 | 显式列表 | 分公司/分型 |
| | `reviewer_scope` | 空列表 = 拒绝；自批恒 `false` | 显式列表 | 分公司/分型 |
| | `system_manager_scope` | 空业务范围 = 拒绝 | 显式列表 | 全局/分公司 |
| 试点 | `pilot_scope` | `["USNJ"]`，`row_list_ref=null`（行名单不进仓库） | 版本化名单 | 分公司/SKU |
| | `pilot_window` | 6 周影子（2/4/6 周复核），上限 8 周 | 4–8 周 | 分公司 |
| | `special_cny_owner_hold` | `true`（逐行 HOLD） | 布尔 | 分公司/分型/SKU |
| 评估 | `fva_window` | 冻结后 4 周滚动、累计 8 周复核 | 4–12 周 | 分公司/分型 |
| | `fva_metric` | 主报 `fva_wape` + 5 辅报；可增补 mase/pinball | 指标冻结 | 全局/分型 |
| | `override_degradation` | 连续 2 窗 FVA<0；β −2 点；库存 +20%（容忍 0–5 点 / 10–50%） | 见 defaults.json | 分公司/分型 |
| 写入 | `accept_auto` | `explicit_accept_only` | 仅显式接受 | 分公司/行 |
| | `override_quantity` | 须总量/增量、原因、证据、期间；禁负最终量 | 布尔集合 | 行/期间 |
| | `override_priority_threshold` | 绝对比例 20%；零基准新增优先复核 | 10–100% | 分公司/分型 |
| | `event_only` / `period_override` | 只报事件 / 改期间先重算 | 枚举 | 行/分型 |
| | `weekly_grain` | 7 日，允许 7/14/28；`enabled=false`（试点期禁用） | 见 defaults.json | 分公司/分型 |
| | `weekly_freeze` | 周三 12:00 冻结；周二 18:00 提交、周三 11:00 审核截止 | 枚举/时间 | 分公司 |
| | `reapproval` | 有效期 7 天；输入版本变即重审 | 1–7 天 | 分公司/行 |

完整值与范围以 `supply_copilot/config/defaults.json` 和 `config show` 为准（本文不复制全部嵌套字段）。

## 4. 校验规则

| 规则 | 行为 |
|---|---|
| `schema_version` | 必须是 `supply-config/v1`（允许 `v1.x` 次版本）；`v2` 等主版本报 `unsupported_schema` |
| 未知键 | 顶层 / `values` 参数 / 对象内字段，一律拒绝并给允许集合（参数名带近名建议） |
| 类型 | `bool` / `int` / `float` / `str` / `object` / `list`；`bool` 不算 `int` |
| 范围 | 数值区间；对象内逐字段 |
| 枚举 | 只允许列出的取值；受保护项枚举为 `[false]` |
| 跨字段 | 年龄门槛 `ok ≤ warn < hold`；ABC 分界严格递增；`improvement_min ≤ max`；`validity_min ≤ max` 等 |
| 作用域 | 参数级白名单；SKU 例外四维齐全；空作用域仅供默认层或全局参数 |
| 受保护 | 四硬约束不可覆盖（文件与 overrides 均拒绝） |

错误一次性汇总（`ConfigError`），带 `参数路径: 原因`；CLI 退出码 2。

## 5. 哈希与版本

- `config_hash = sha256(规范化 JSON)`：`{"schema_version","values"}` 按 `sort_keys` 序列化，
  所以**同内容不同键序/不同 `config_version` 得同一哈希**，便于逐次运行固定与审计比对。
- 哈希覆盖生效值（默认+文件+override 合并后），**不含** `config_version`、`path`、来源标记。
- 版本号规则（对齐 `unified-data-contract` §6.1/§7.4）：
  - 加参数/加对象字段 → 次版本（`supply-config/v1.N`），读取端忽略未知字段；
  - 改枚举或语义 → 主版本 + 迁移脚本；
  - 每次发布记录 `config_hash`，运行侧固定它。

## 6. 回退

1. **回退 = 发布新版本指向旧值**（旧 `config_version` 的 `values` 原样抄进新文件，改 `config_version`），
   不删日志、不覆盖历史快照。
2. 回退前跑 `config validate`：受保护硬约束同样受检查，回退不能恢复 `auto_order=true` 之类状态。
3. 校验失败 → 保留上一个有效文件继续用（CLI 退出码 2 不算发布成功），并在运行记录里标 `last_attempt`。
4. 例外默认 7 天到期（1–28 天，审核人可改）；到期回上层政策，相关未执行判断重新审核。

## 7. 已知边界（未核实 / 未接线）

- 本层**不消费**配置：`decide.py` / `refresh.py` 行为不变，`explain()` 的“来源”只描述配置层。
- 优先级解析只提供 `scope_rank()`，**尚未实现**多作用域合并求解（SKU 例外命中逻辑待接线）。
- `pilot_scope.row_list_ref` 只存引用，296 行名单属私有数据，不进仓库。
- 参数范围是 `decision-defaults.md` 的**试点建议**，非行业标准或已验证最优值；
  默认值不激活、不部署。
