#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quantity pilot: four gates -> per-period net demand -> A/B/reject (OFFLINE).

Implements DECISIONS.md D35 item 3 on the 790 scored SKUs:
  1. four gates, each SKU gets 已证 / 未证 / 无法判定 with the evidence field;
  2. per-period net demand for the SKUs that pass all four gates (monthly
     buckets — the forecast has no finer date; this is a granularity limit,
     not a monthly-average shortcut);
  3. A / B / reject split: A requires a business-approved demand basis (none
     exists in the artifacts, so A = 0), B carries explicit assumptions that
     still need approval, reject names the failed gate and the missing evidence.

Constraints honoured: DB read_only, no production, no order quantity is
produced, MOQ/pack/budget are not mixed into net demand, row-level CSV stays
local, no commit.

Outputs:
  control/reviews/2026-10-23-quantity-pilot.md      (aggregates only)
  out/business_phase/quantity_pilot_rows.csv        (local, row level)
  out/business_phase/quantity_pilot.json            (local, machine summary)
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
BP = CLAUDE_DIR / "out" / "business_phase"
REVIEW = CLAUDE_DIR / "control" / "reviews" / "2026-10-23-quantity-pilot.md"
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
MONTHS = ["2026-10", "2026-11", "2026-12"]


def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def main() -> None:
    dest = {r["sku"]: r for r in json.loads((BP / "destinations.json")
                                            .read_text(encoding="utf-8"))["rows"]}
    rout = list(csv.DictReader((BP / "final_bundle_routing.csv").open(encoding="utf-8-sig")))
    scored = sorted({r["SKU"] for r in rout if r["routing_support"].startswith("曾进入")})
    dec = list(csv.DictReader((BP / "decision_v2.csv").open(encoding="utf-8-sig")))
    usab = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "usability_audit.csv").open(encoding="utf-8-sig"))}
    wo = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "wo_dn_coverage.csv").open(encoding="utf-8-sig"))}
    rows_by_sku = defaultdict(list)
    for r in dec:
        rows_by_sku[r["SKU"]].append(r)

    b = list(csv.DictReader((CLAUDE_DIR / "out" / "auto_order" / "linkage_audit_v2.csv")
                            .open(encoding="utf-8-sig")))
    so_items = {r["item"] for r in b if r.get("item")}

    con = duckdb.connect(str(DB), read_only=True)
    try:
        item2skus = defaultdict(set)
        for sku, item in con.execute("SELECT sku, item_code FROM sku_item").fetchall():
            item2skus[item].add(sku)
        stock_date = con.execute(
            "SELECT max(snapshot_date) FROM stock_history").fetchone()[0]
    finally:
        con.close()

    def gate(sku):
        d = dest.get(sku, {})
        rows = rows_by_sku.get(sku, [])
        item = d.get("mapped_item_code")
        # G1 mapping + UOM
        checks = d.get("checks", {})
        states = {k: checks.get(k, {}).get("state") for k in
                  ("duplicate_mapping", "one_code_multi_material",
                   "alias_deleted", "uom_unknown")}
        if d.get("destination") == "mapped_eligible" and all(v == "ok" for v in states.values()):
            g1 = ("已证", "destinations.checks 四检全 ok + mapped_eligible")
        elif d.get("destination") == "mapped_eligible":
            g1 = ("未证", f"checks 未全 ok: {states}")
        elif not d:
            g1 = ("无法判定", "不在 destinations 母集")
        else:
            g1 = ("未证", f"destination={d.get('destination')}")
        # G2 same-warehouse stock + date
        if not rows:
            g2 = ("无法判定", "无 SKU×仓 行")
        elif len(rows) > 1:
            g2 = ("未证", f"多仓（{len(rows)} 个仓行），非简单单仓 SKU")
        else:
            r = rows[0]
            u = usab.get((r["SKU"], r["仓"]), {})
            if r.get("可用") in ("", "None"):
                g2 = ("未证", "该仓可用库存未取得（B_pending_inventory）")
            elif u.get("可用是否同仓事实") == "yes" and u.get("库存摊派") == "no（逐仓库存行）":
                g2 = ("已证", f"同仓库存行 + 快照日期 {stock_date}")
            else:
                g2 = ("未证", f"同仓事实={u.get('可用是否同仓事实')} 摊派={u.get('库存摊派')}")
        # G3 demand source identifiable
        if not item:
            g3 = ("无法判定", "无映射物料")
        elif len(item2skus.get(item, ())) > 1:
            g3 = ("未证", f"物料对应 {len(item2skus.get(item, ()))} 个 SKU，需求归属不唯一")
        elif item in so_items:
            g3 = ("未证", "窗口内有显式 SO 行；预测与 SO 重叠未处理（冲减说明：不冲减）")
        else:
            g3 = ("已证", "窗口内无该物料 SO 行；需求仅来自预测")
        # G4 supply dedupe + usable time
        w = wo.get((rows[0]["SKU"], rows[0]["仓"]), {}) if rows else {}
        if not rows:
            g4 = ("无法判定", "无 SKU×仓 行")
        else:
            issues = []
            if w.get("覆盖状态") != "no_material_found":
                issues.append("在产 WO 有材料但 ETA 未证（covered_unvalidated）")
            for r in rows:
                po = r.get("PO去重状态")
                if po not in ("none_recorded", "lines_unique"):
                    issues.append(f"PO 去重未过（{po}）")
                if num(r.get("PO未结")) > 0:
                    issues.append("存在未结 PO 且无 ETA")
                if r.get("在途去重状态") != "none_recorded" or num(r.get("在途")) > 0:
                    issues.append(f"在途不可去重/无时间（{r.get('在途去重状态')}）")
            g4 = ("已证", "无 WO 材料、无未结 PO、无在途") if not issues else ("未证", "；".join(sorted(set(issues))))
        return g1, g2, g3, g4

    # ---- gate evaluation + sequential funnel --------------------------
    gate_rows = []
    first_fail = Counter()
    per_gate_fail = Counter()
    per_gate_state = defaultdict(Counter)
    passed = []
    for sku in scored:
        g = gate(sku)
        verdicts = [x[0] for x in g]
        gate_rows.append(dict(sku=sku, G1=g[0][0], G1_evidence=g[0][1],
                              G2=g[1][0], G2_evidence=g[1][1],
                              G3=g[2][0], G3_evidence=g[2][1],
                              G4=g[3][0], G4_evidence=g[3][1]))
        for i, v in enumerate(verdicts, 1):
            per_gate_state[f"G{i}"][v] += 1
            if v != "已证":
                per_gate_fail[f"G{i}"] += 1
        fail = next((i for i, v in enumerate(verdicts, 1) if v != "已证"), None)
        if fail:
            first_fail[f"G{fail}"] += 1
        else:
            passed.append(sku)

    # ---- per-period net demand for passing SKUs ----------------------
    period_rows = []
    for sku in passed:
        r = rows_by_sku[sku][0]
        on_hand = num(r.get("可用"))
        rate = num(r.get("月需求率"))
        cum = 0.0
        for m in MONTHS:
            cum += rate
            net = max(0.0, cum - on_hand)
            period_rows.append(dict(sku=sku, month=m, monthly_demand=round(rate, 3),
                                    cumulative_demand=round(cum, 3),
                                    on_hand=round(on_hand, 3), net_demand=round(net, 3),
                                    formula="max(0, Σ月需求 − 在手)"))
    month_agg = defaultdict(lambda: dict(demand=0.0, net=0.0, n=0))
    for p in period_rows:
        a = month_agg[p["month"]]
        a["demand"] += p["monthly_demand"]
        a["net"] += p["net_demand"]
        a["n"] += 1

    # ---- A/B/reject ----------------------------------------------------
    # A needs a business-approved demand basis; the artifacts contain none.
    A = []
    B = [s for s in passed]
    reject = [r for r in gate_rows if r["sku"] not in set(passed)]

    # ---- write local row-level files ----------------------------------
    with (BP / "quantity_pilot_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gate_rows[0].keys()))
        w.writeheader()
        w.writerows(gate_rows)
    with (BP / "quantity_pilot_periods.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(period_rows[0].keys()) if period_rows else ["sku"])
        w.writeheader()
        w.writerows(period_rows)

    # ---- report (aggregates only) --------------------------------------
    n = len(scored)
    total_net = {m: round(month_agg[m]["net"], 1) for m in MONTHS}
    total_dem = {m: round(month_agg[m]["demand"], 1) for m in MONTHS}
    summary = dict(
        schema_version="quantity_pilot/1",
        scored=n, passed=len(passed), A=len(A), B=len(B), reject=len(reject),
        per_gate_fail=dict(per_gate_fail), first_fail=dict(first_fail),
        months=MONTHS, month_demand=total_dem, month_net=total_net,
        stock_snapshot_date=str(stock_date),
        reconcile=f"{len(A)} + {len(B)} + {len(reject)} = {len(A)+len(B)+len(reject)} == {n}",
        reconcile_ok=(len(A) + len(B) + len(reject) == n),
    )
    (BP / "quantity_pilot.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def pct(a, b):
        return f"{a/b*100:.1f}%" if b else "—"

    L = ["---", "okf: v0.1", "type: Review",
         "title: 数量衔接试点：四门筛选 + 逐时段净需求 + A/B/拒绝",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读离线；不给可下单量；行级数据留本地",
         "---", "",
         "# 数量衔接试点", "",
         "> 依据 D35 第 3 条：**不得把 790 整体视为供需合格**。本报告只给判定与聚合数字，"
         "不产出可下单量；MOQ / 包装倍数 / 预算均不在本表。", "",
         "## 1. 四门判定（790 个已评分 SKU）", "",
         "每门三态：已证 / 未证 / 无法判定。逐 SKU 判定与证据字段见本地 "
         "`out/business_phase/quantity_pilot_rows.csv`。", "",
         "| 门 | 判据 | 已证 | 未证 | 无法判定 |", "|---|---|---:|---:|---:|",
         f"| G1 映射与 UOM | destinations.checks 四检全 ok + mapped_eligible | "
         f"{per_gate_state['G1'].get('已证',0)} | {per_gate_state['G1'].get('未证',0)} | "
         f"{per_gate_state['G1'].get('无法判定',0)} |",
         f"| G2 同仓库存与日期 | 简单单仓 + 同仓库存行 + 快照日期 {stock_date} | "
         f"{per_gate_state['G2'].get('已证',0)} | {per_gate_state['G2'].get('未证',0)} | "
         f"{per_gate_state['G2'].get('无法判定',0)} |",
         f"| G3 需求来源可辨 | 窗口内无该物料 SO 行（否则预测/SO 重叠未处理） | "
         f"{per_gate_state['G3'].get('已证',0)} | {per_gate_state['G3'].get('未证',0)} | "
         f"{per_gate_state['G3'].get('无法判定',0)} |",
         f"| G4 供给可去重与可用时间 | 无 WO 材料、无未结 PO、无在途 | "
         f"{per_gate_state['G4'].get('已证',0)} | {per_gate_state['G4'].get('未证',0)} | "
         f"{per_gate_state['G4'].get('无法判定',0)} |", "",
         "（各门独立计数，同一 SKU 可同时未过多个门，因此四列相加 ≠ 790。）", "",
         "**顺序漏斗（首个未过门，互斥，合计 790）**：", "",
         "| 阶段 | SKU |", "|---|---:|",
         f"| 入 | {n} |",
         f"| 过 G1 | {n - first_fail.get('G1', 0)} |",
         f"| 过 G1–G2 | {n - first_fail.get('G1', 0) - first_fail.get('G2', 0)} |",
         f"| 过 G1–G3 | {n - first_fail.get('G1', 0) - first_fail.get('G2', 0) - first_fail.get('G3', 0)} |",
         f"| 过四门 | {len(passed)} |", "",
         "**拒绝原因分布（首个未过门，互斥）**：" +
         "、".join(f"{k}（{'映射/UOM' if k=='G1' else '同仓库存' if k=='G2' else '需求来源' if k=='G3' else '供给可去重'}）{v}"
                  for k, v in sorted(first_fail.items())), "",
         "## 2. 过门 SKU", "",
         f"- 四门全过 **{len(passed)}** 个（占 {pct(len(passed), n)}）。",
         "- 这些是「简单单仓、映射与 UOM 已证、同仓库存有日期、需求仅来自预测、无可去重供给单」的 SKU。",
         "- 名称清单见本地 `quantity_pilot_rows.csv`（筛 `G1..G4` 全为已证）。", "",
         "## 3. 逐时段净需求（仅过门 SKU）", "",
         "公式：`净需求_m = max(0, Σ_{k≤m} 月需求_k − 在手)`；输入 = `decision_v2.月需求率`（月桶）"
         f"与 `decision_v2.可用`（快照日期 {stock_date}）。", "",
         "| 月份 | 需要日 | 需求合计 | 净需求合计 | 覆盖 SKU | 成立条件 |",
         "|---|---|---:|---:|---:|---|"]
    for m in MONTHS:
        L.append(f"| {m} | {m}-01 | {total_dem[m]} | {total_net[m]} | {month_agg[m]['n']} | "
                 f"在手当日可销、无在途/PO/WO、预测即需求 |")
    L += ["", "> 月度需求每桶相同，是因为 T5 预测给出的是**平月率**（无季节形状），"
          "不是把季度总量摊平的结果。", "",
          "> **粒度边界**：需求来自月度预测，本身没有日期；这里按**月桶**分时段，"
          "不是用月均单点替代日需求（日级需求在本数据源里不存在）。"
          "时间未证的供给（PO/WO/在途）不进本表——G4 已把它们排除。", "",
          "## 4. A / B / 拒绝 三分", "",
          "| 批 | 数 | 定义与假设 |", "|---|---:|---|",
          f"| A（业务已批准需求依据 + 供给完整） | **{len(A)}** | 现有产物中**没有**业务批准记录，"
          f"因此 A 批为空；不把测算当批准 |",
          f"| B（显式假设，**待业务批准**） | **{len(B)}** | 每行假设：需求=预测（无 SO 重叠）、"
          f"在手可销、无在途/PO/WO |",
          f"| 拒绝 | **{len(reject)}** | 逐条写首个未过门与缺什么证据，见 CSV |", "",
          f"**对账**：{len(A)} + {len(B)} + {len(reject)} = {len(A)+len(B)+len(reject)} = 入 {n} "
          f"{'✅' if len(A)+len(B)+len(reject) == n else '❌'}", "",
          "## 5. 能支持什么 / 不能支持什么", "",
          "**能支持**：在这批过门 SKU 上，按月说明「在手能覆盖到哪个月、哪个月开始出现净需求」，"
          "作为需求—供给对话的输入。", "",
          "**不能支持**：① 不能当采购/下单量（MOQ、包装倍数、预算未纳入）；"
          "② 不能外推到未过门的 584 个 SKU；③ 不能证明预测准确（预测是需求依据，不是真值）；"
          "④ 不能替代业务对 B 批假设的批准；⑤ 不含日级需求（数据源无日期）。", "",
          "## 6. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/"
          "business_phase/quantity_pilot.py",
          "```", ""]

    REVIEW.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
