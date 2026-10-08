---
okf: v0.1
type: Reference
title: 遗留系统审计交付物 — 活档案 + 机械自检（让人能独立评审）
date: 2026-10-08
category: best-practices
module: docs_solutions
problem_type: best_practice
component: documentation
severity: high
applies_when:
  - "审计/考古一套多年积累的 Colab + Google Sheet + EN 产物，要把结论交给别人独立评审"
  - "结论多到'人不可能逐条核对'，需要让评审者能自己复算而不是信你"
  - "要把某条推理过程（含被推翻的假设）留痕，供后续 Agent 少踩重复的坑"
tags: [legacy-audit, deliverable, self-check, evidence-grading, retracted-hypotheses, reviewability]
related_components: [tongtool_order_cost, colab_kit, docs_solutions]
---

# 遗留系统审计交付物 — 活档案 + 机械自检

## Context

一次真实审计：一套从 2022 年积累至今的 **Colab（227 cells）+ 多本 Google Sheet（~200 ws）+ EN 成本表** 成本链，因订单 `DY-LAPW-24868` 出现 `二次加工成本*数量 = 0.001` 而 `*系数 ≈ 186.8` 被要求查清。产物要交给**独立评审**（另一个 Agent / 人）。

第一版交付 = 4 份长文档 + 我的结论。用户反馈很关键：

> 细节倒是不错，不过给人看的话太长了，**我不可能挨个核对**。你自己想办法核对……我需要让它**独立评审**。

即：**审计结论的可审性本身就是交付质量的一部分**。本文记录为此采用的做法与踩过的坑。

## Guidance

1. **把结论变成可机械复算的断言。** 文档里每条可量化的主张，配一条自检脚本断言（本例 `tongtool_order_cost/scripts/verify_colab_cost_claims.py`，40 项）。评审者跑一条命令就看到 `OK/FAIL`，不必读长文、不必信你的转述。要求：只读、带退避重试与落盘缓存、脚本入库、**改文档同步改脚本**。
2. **每条断言带出处 + 证据分级。** 出处精确到 `cell 号 / ws 名 / 公式原文`；分级用 **已证实 / 高概率 / 无法确认**。评审者据此知道"哪些能当事实、哪些只是推断"。
3. **把"被推翻的假设"写进交付物。** 审计中我至少下过 4 个后来被数据推翻的结论（见 Examples）。只留最终结论，评审者无从判断推理可靠性，也无法复用"哪里容易想错"。
4. **上下文与结论分开交付。** 除结论外要给**推理链与领域知识来源**：PR body 写决策链、指明会话转录路径；**不要把几百 MB 的原始 transcript（jsonl）当交付物**——它是"可读但不可审"的。
5. **自检脚本自己也要被自检。** 脚本的 bug 会把 FAIL 说成 OK（本例 3 处：表格标题↔ID 判别、`"""` 块与注释行未排除、`= \` 续行语法未处理）。所以出现 FAIL 时**先判是"主张错"还是"检查器错"**，再只改一边。
6. **把"运行纪律"这类不可见约束写下来。** 本例"每月跑两遍、第二遍**不跑 4.6.1**、顺序不可颠倒"原文只写在 notebook 的 cell 标题里；不落文档必踩。
7. **区分"系统事实"与"本机事实"。** 例如"本机读 GS 失败是 TLS 传输问题、不是配额限流"属本机事实，写进文档要标明，避免被当成系统行为。

## Why This Matters

- **可审性决定结论是否被采信**：审阅者一旦放弃逐条核对，等于你的结论无人验证。
- **单点观测会被复制成"事实"**：本例 `订单发货仓库对应成本来源 = 48 数据行` 这个错，被**我的文档和一次独立并行复核同时写错**（实为 **47 数据行 + 表头**），只有机械自检才抓出来。
- **遗留系统审计的价值不在结论，而在可复用的判断依据**；不写"想错过什么"，下一个 Agent 会把同样的坑再踩一遍。

## When to Apply

- 审计/考古遗留系统、并把结果交给他人（或别的 Agent）评审时。
- 把多年积累的 notebook / GS / 脚本整理成"现状事实源"时。
- 任何"结论数量超出人可逐条核对能力"的交付。

## Examples

**自检输出的样子**（评审者的一条命令即可复算）：

```
$ GSPREAD_SERVICE_ACCOUNT_FILE=<repo>/secrets/gsheets-service-account.json \
    uv run python tongtool_order_cost/scripts/verify_colab_cost_claims.py
  [OK] cell 数 == 227
  [OK] ls_col_order_keep 列数 == 71（实得 71）
  [OK] 绍兴二次加工成本 手填兜底 == 188（实得 188）
  ...
=== 合计 40 项，FAIL 0 ===
```

**被推翻的假设（给独立评审的关键材料）**

| # | 当时的判断 | 推翻它的证据 | 正确结论 |
|---|---|---|---|
| ① | `售价*汇率` 被 1.7.0 特殊规则覆写 | 通途原表 `DY-LAPW-24868` 有 2 行，`售价` 107.26 + 122.69 = 229.95 = Colab 合并行的 `售价` | 通途**按包裹分摊销售额**、Colab 求和**正确**；`售价(人民币)` 是通途自带汇率（财务不用），因此**人民币列不能当判据** |
| ② | "跨 EN 产品 ⇒ 不该合并" | `TT0031131K0063816-Foam`（海绵）+ 多色 `…-Cover`（皮壳）**拼起来是一个成品**；EN 客户码登记历史上允许一码多登记（后加前端校验禁止），且**共享部件只登记在一个产品下** | EN 产品编号只是**分组信号、不是判据**；必须叠加订单侧信号（部件互补 + 产品名主体一致），且"跨产品"不等于不该合并 |
| ③ | 仓映射有 **48 数据行** | 自检脚本数出 47 data rows，`get_all_values()` 共 48 行（含表头） | **47 数据行 + 表头** |
| ④ | 白名单里 `运营部当月是否为新品` 多一个"为" | 实读白名单 `cell 135` 为 `运营部当月是否新品`（**少**"为"），上游 `cell 36/101` 才是"是否为新品" | 方向相反：`reindex(fill_value=0)` 会把白名单那列造出**恒 0 幻影列**，并**丢掉真实列** |

**一条本机事实（写文档时要标明）**：`gc.open(标题)` 会走 **Drive files.list** 解析标题→ID，在本机（境内出口）间歇 `ssl.SSLEOFError: UNEXPECTED_EOF_WHILE_READING`（**不是 429 配额**）；改 `gc.open_by_key(<表格key>)` + 4–6s 退避重试 + 落盘缓存后每次成功。

## Related

- 被审计对象的现状档案：`architecture-patterns/colab-cost-pipeline-current-state.md`、`colab-gsheet-inventory.md`、`en-cost-side-current-state.md`、`colab-cost-pipeline-data-flow.md`
- 被审计出的核心缺陷：`workflow-issues/colab-legacy-cost-two-source-delivery-type.md`
- 自检脚本：`tongtool_order_cost/scripts/verify_colab_cost_claims.py`
- [知识库防腐三件套](knowledge-base-anti-rot.md) —— 文档层面的机械校验（孤儿/索引/链接）
- [扫描类脚本防"静默丢数"](scanner-silent-data-loss-guard.md) —— 脚本层面的机械校验（反转匹配方向）
- [Colab notebook 读写改工具箱](../../../colab_kit/README.md) —— 改这类 notebook 的 guard/verify 纪律
