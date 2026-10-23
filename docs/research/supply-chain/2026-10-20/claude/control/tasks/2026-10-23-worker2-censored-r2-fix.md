---
okf: v0.1
type: Task
title: 打工仔2｜M01 损失方向返修 + 301 五条整改（合并，不重复派活）
date: 2026-10-23
owner: claude-worker-2
status: dispatched
replaces: none
supersedes_report: 2026-10-23-censored-compare.md（e1b9b5d7）
---

# 任务：删失实验返修（R2）—— M01 为唯一已证实训练错误

## 输入（固定版本，直接用 git show / 直接读文件）

- 本仓库 `e1b9b5d7`：`experiments/pb_stockout/censored_compare.py`、`out/pb_stockout/censored_compare.{json,md}`、`control/reviews/2026-10-23-censored-compare.md`
- 你上一轮的产物（本任务继承，不要重写）：`experiments/pb_stockout/audit_pb_censored.py`、`out/pb_stockout/stockout_intervals_decomposed.csv`、`out/pb_stockout/censored_audit.json`、`control/reviews/2026-10-23-pb-censored-audit.md`
- **Codex #301 独立复审（FAIL，五条 major + 一条 minor）**：
  `C:/Users/zhang/.codex/worktrees/supply-chain-independent-research/Cursor/docs/research/supply-chain-review/2026-10-23-censor-review.md`
  —— 先完整读它，再动手。
- 外部名单证据：`D:/Work/fzh-order-store/pb_forecast_cohort.json`（28 名单 / 2024-25 促销证据）。

## 必须做的（按 301 的 M01–M05 / N01）

### M01 · 删失损失方向反了 —— 唯一已证实的训练错误，必须修

**事实（301 用固定版本纯函数复现）**：`censored_compare.py:105-122` 在 `pred < y_log` 时把受限月权重**置零**；
`y` 是真实销量的**下限**（true_demand ≥ y），所以：

| 情形 | 正确做法 | 现实现 |
|---|---|---|
| `pred < y` | **预测必然低于真实需求 → 必须惩罚**（单侧损失） | 零权重 ❌ |
| `pred ≥ y` | 不确定区 → 不惩罚 | 有惩罚 ❌ |

301 的极小反例：`y=[0,0,10]`，第三行受限 → raw 拟合 `3.333333`，censored 拟合 `0`。方向必须反过来。

**要求**：
1. 实现正确的单侧下限目标（如 `max(0, y - pred)²`，或 Tobit 下删失负对数似然），并说明选了哪种、为什么。
2. 加**回归测试**：固定输入 `y=[0,0,10]` → 断言 censored 拟合 **≥** raw 拟合且**远离 0**；再构造一个"预测已高于下限"的单元，断言不产生额外惩罚。
3. 重跑对照，**明确废止** e1b9b5d7 里"0.527→0.518 方法有效性"的解释。新报告写"取代 2026-10-23-censored-compare.md 第 X 节"。

### M02 · 信号簇跨度 ≠ 连续断货下界

- 字段改名 `signal_cluster_span_days`；上界叫「假设性扩展窗口」，**不叫下界/上界**。
- 实际信号点**独立保留**；连续时长 / 恢复日期一律 `unknown`，除非有逐日或区间连续证据。
- **不得**把假设边界直接转成已证的删失标签（`censored_compare.py:78-82` 现在把整个跨度重叠月标成受限，必须改）。

### M03 · 预测/发运比是中性的描述性统计

- 已改名 `forecast_above_shipment_ratio`；再补：零分母（6 个 `actual=0` 单元）**单列**，不并进比值分母。
- 全文不得出现"缺货暴露 / 积压 / 更好"这类业务排序措辞。

### M04 · 事后选样 / 标签可知时间

- 每个切点**冻结**：当时可知的事件与来源时间、当时可用的训练标签、当时入选的名单。
- 目标期分组**另列**为事后分析用途；补一个负例：**追加未来证据不改变历史可用训练标签与预测**。
- 做不到 point-in-time 就明写「回顾性同批 SKU 实验」，**不得**当作部署回测证据。

### M05 · 26 / 27 / 28 集合差异闭合

- 出**逐 SKU 集合差异表**，四类分开：未纳入 / 无窗口标签 / 无销量 / 映射歧义。
- 已知：27→26 排除 `CEN803NLinen-Black-138`（PB 销量 46、全期事件 7、**WX 窗口内事件 0**）。**不得**静默当作"无受限需求"。
- 外部 28 名单：你上一轮已给"多 3 个 CENC/Linen、缺 4 个 Coffee（零销售）"；本轮把 cohort.json 的规则与来源引用一并写进表，并标明 **28 个 PB 数字码本地无证据**。
- 回测与业务结论**限定到冻结集合**。

### N01 · 计数与 horizon 文案

- 受限月：JSON 实际是 **24 个两月 + 2 个一月**（SageGreen-100、LTGrey-97 仅 July），不是"每 SKU 两个"。
- 单元数：全预测单元 **208**；比值可评 **202** + 零分母 **6**。
- 逐切点有效 horizon **3/3/2**（最后切点 July 起点的 Oct 目标被截），不得统一写 horizon 3。

## 硬约束

- DB `read_only=True`；不访问生产、不扩样、不下单。
- **不 commit、不 push** —— 工头是唯一提交者。
- 不新增第三方依赖。
- 只改 `experiments/pb_stockout/`、`out/pb_stockout/`、`control/reviews/2026-10-23-*`。
- 顺手把两个一次性探针脚本 `_probe_schema.py`、`_probe_map.py` 删掉；删不掉就明说，工头提交时排除。
- `uv run python scripts/check_secrets.py` 零输出（**不要**跑 `update_index.py`，工头做）。

## 验收

- 终端输出 `DONE PB-FIX2`。
- 报告 `control/reviews/2026-10-23-censored-r2-fix.md`：M01–M05/N01 **逐条**给「修复前 → 修复后 + 证据（文件:行 / 数字）」，并用 301 的反例 `y=[0,0,10]` 演示方向已纠正。
- 新对照数字 + SKU 整簇 bootstrap CI；若差异仍在噪声内，**明写仍不支持"删失更好"**。
- 入 N 出 M 对账；未评分/未纳入单列并给原因。
