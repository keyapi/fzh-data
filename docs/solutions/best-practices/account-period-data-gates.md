---
okf: v0.1
type: Reference
title: 账期/成本全链路门禁：账号、币种、金额、merge、期间
date: 2026-11-20
category: best-practices
module: sellfox_settlement
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "写账期/成本/渠道账号相关 join 或 pandas merge"
  - "出现账号未匹配、币种空、金额为0、行数对不上"
  - "准备自动写 Google Sheet 或定稿财务数字"
  - "设计 1.7.0 特殊规则、附件定稿、Tax/FBA 链路"
tags: [data-gates, pandas-merge, account-period, data-quality, finance]
---

# 账期/成本全链路门禁

## Context

账期链路里最贵的错误不是报错，而是**静默继续**：账号没匹配就变 `null`、币种名不干净就 RMB=0、附件的 100 倍错数直接进表、FX 别名展开让规则重复执行。2026-11 的 WFDANEEYUS 缺别名、AllegroHU 零宽字符、AMZJohnaSE 100 倍、8 月 Tax 重复附件，都是同一类缺口。

## Guidance

### 1. 门禁分级

- **FAIL（阻断）**：会导致金额/账号/期间错，且不能自动解释。
- **WARN（列清单后继续）**：业务上合理的差异（仅 OA/仅通途、零成本非商品、展示尾差），必须把行/账号/金额/原因留在报告里。
- **PASS 不能靠“退出码 0”**：WARN 必须有明确原因；未知/未就绪不能当 PASS。

### 2. 必加门禁（最小集）

| 门禁 | 规则 | 级别 |
|---|---|---|
| 账号覆盖 | 订单/ OA 的原始账号（非空）必须经 alias 映射到主账号 | FAIL |
| 别名唯一 | 一个 alias 只能指向一个主账号；alias 维表键唯一 | FAIL |
| merge 基数 | 订单×别名 m:1 不放大；join 前后行数/键集合可解释；空键不互配 | FAIL |
| 运营人员 | 有金额账号必须有当月运营人员；一账号多人员先列出 | FAIL / WARN |
| 币种/汇率 | 外币金额>0 必须有币种、汇率、RMB>0；币名先 NFKC/去 Cf/全角转半角 | FAIL |
| FX 唯一 | `ISO+月份` 单一汇率；别名展开后同 ISO 多行只提示，不直接进 merge | FAIL / WARN |
| 金额尺度 | OA 提交值 vs 附件金额比值偏离 1（含 100 倍/0.01 倍） | FAIL |
| 成本恒等 | `产品成本 = 皮壳+绍兴二次+二次加工`；`总成本 = 四段` | FAIL |
| 有量无成本 | 发货数量>0 但总成本=0：非商品/大件云仓/皮壳可 WARN，其余查缺成本 | WARN |
| 预留恒等 | `销售额−费用=应收+应收账款`；`应收账款=本期预留−返还上期` | FAIL |
| Tax/附加费 | OA `人民币` 与 `附加费&Tax` 合计一致；附加费=四分项 | FAIL |
| 来源新鲜度 | `账号` ws 与 `写回` 不一致时不得当成本源；旧特殊写回/旧 pivot 不得当当前 | FAIL |
| 规则版本 | 只允许 `黄-特殊规则-订单改销售额成本`；Jeck/旧 206 条只作历史 | FAIL |
| 期间 | 04–03 收入 vs 月度成本要写清；跨桶附件/跨期退款要列 | WARN/FAIL |
| 写前基线 | 写 GS 前记录目标表/全簿状态；任何 FAIL 不 `clear`；写后回读行数/合计 | FAIL |

### 3. 已知事故 → 对应门禁

- **WFDANEEYUS 缺 `WFUS-Daneey`**：订单 3 行、成本约 681.98，静默变 `null` → 账号覆盖 FAIL。
- **AllegroHU `‌匈牙利福林（HUF）`**：U+200C + 全角括号 → 汇率/RMB=0 → 币种/汇率 FAIL。
- **AMZJohnaSE 19,920 vs 199.20 SEK**：100 倍 → 金额尺度 FAIL。
- **8 月 Tax 重复附件/跨桶 7 月副本**：同 hash/同结算号 → 重复入账 FAIL；跨桶 WARN。
- **StruseryBE 8.25 EUR 实际 ES**：账号/市场归属错 → 审批/附件 marketplace 一致 FAIL。
- **`账号` vs `写回` 成本差 −556,373**：旧快照 → 源新鲜度 FAIL。
- **旧 `特殊规则_写回` 1,691 键不一致**：旧快照 → 版本/基线 FAIL。
- **规则限定列缺失会扩大命中**：c22 只在订单列存在时才加 `运营人员/发货区域/渠道账号/仓` 过滤；缺列时规则退化为“不限”，应 FAIL，不能静默放宽。
- **FX 别名展开**：735→800（7/8）、659→746（9），规则重复执行；同 ISO 同率金额不变，但必须 canonical 化 → FX 唯一 WARN/FAIL。
- **c82 负费用/净零行被删**：只保留费用和>0，NEG/ZERO_NET 丢失；且差额≤1 自动加最大行 → 不是批准的尾差政策，必须改。

### 4. 标准做法

1. **保留原始行**：坏数字、缺列、未匹配、负费用、净零分项都要保留原值和原因，不能填 0 后继续。
2. **先统一 key**：NFKC + 去 Cf + 折叠空白 + casefold；空/null/nan 用统一 sentinel，不参与匹配。
3. **每个 join 独立核账**：`validate`/`indicator`、前后行数、各来源金额守恒；`groupby` 用 `dropna=False`。
4. **同层控制数**：明细对明细、账号对账号；不要拿“明细备份”对“账号调整后”。逐账号舍入 0.02–0.05 属展示尾差，财务目前不要求说明，但控制数不能混层。
5. **写前校验**：三张 writer 在 `clear` 前先跑 `validate_account_period.py`；FAIL/异常不写。附件链路先跑独立 `validate_ingest.py`（manifest：hash/期间/V1V2/100 倍）。
6. **manifest 绑定**：月份、模式、源/规则/待写 payload hash、目标表 ID、校验版本；跨进程短效 token 不能替代源变更检查。已落地最小版 `snapshot_guard.py`：validate 时记录 5 个源表 `modifiedTime` + 待写 payload sha256，writer 在 `clear` 前 verify；源或 payload 变化即中止重跑。校验到写入之间仍有竞态，需所有写入方串行/协作锁。

### 5. 实测基线（2026-11-20）

`validate_account_period.py` 对 202607/08/09 × normal/special 六组：**FAIL 0，WARN 4**（G15b FX 别名多行、G39 有量无成本、G13 仅 OA/仅通途、G13b 主表无活动）。G39 抽样为非商品/大件云仓/皮壳，合理零成本；G15b 已用 canonical FX 修复，G15c 保证 ISO+月份单一汇率。

## Why This Matters

这些门禁挡的不是“报错”，而是**错数静默进财务表**。一旦写进 GS/发给财务，回头定位要同时查账号、汇率、附件、期间四层；前置 FAIL 的成本远低于事后追溯。

## When to Apply

任何账期/成本/渠道账号的 join、merge、分摊、写回；新增别名/币种/规则版本；每月 `账号-按应收` 与特殊规则簿；附件 ingest 与 OA 定稿。

## Examples

- 202607 普通/特殊报告：`账号-按应收` 均在 `账号` 紧左边，26 列，7 月负值保留。
- 202607 `WFUS-Daneey` 3 行并入 WFDANEEYUS，成本 681.98；202608/09 无该原始账号。
- 202609 tail：成本差 56,431.88、业绩差 56,431.86、未舍入 56,431.884276；规范不得用混算 56,431.91。

## Related

- `docs/solutions/workflow-issues/amazon-period-performance-report-pipeline.md`
- `docs/solutions/workflow-issues/amazon-settlement-period-cost-and-tax-decisions.md`
- `docs/solutions/best-practices/scanner-silent-data-loss-guard.md`
- 验证目录（仓库外）：`D:/Work/张晶/国内报税/Amazon账期非V2/技术验证/20261118/out_0708/`（`validate_account_period.py`、`validate_ingest.py`、`gate_audit_20261120.md`）
