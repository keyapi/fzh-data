#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quantity pilot R2: time-basis correction + three diagnostic evidence chains (OFFLINE).

Why R2: the pilot's on-hand came from the 2026-10-22 snapshot. That snapshot cannot
support a need date of 2026-10-01, and must not be used to offset October demand.

Rule implemented (per SKU x month bucket):
  * a bucket is COMPUTABLE only when the stock observation date is on or before the
    bucket's need date; otherwise the bucket's stock status is `unknown_asof` and its
    net demand is "不可算" (neither 0 nor a gap);
  * for computable buckets, net demand accumulates from the FIRST computable bucket
    (October demand is never silently carried into November/December);
  * the residual assumption (shipments between the snapshot and the next bucket start
    are unobserved) is stated on every computable row.

Also: the three diagnostic SKUs mandated by Codex2 are reproduced as-is (no
substitution), each with a one-page evidence chain, plus a minimal evidence request
list with responsible roles.

Read-only; no order quantity; row-level output stays local.
Outputs:
  control/reviews/2026-10-23-quantity-pilot-r2.md   (aggregates + three chains)
  out/business_phase/quantity_pilot_r2_periods.csv  (local, row level)
  out/business_phase/quantity_pilot_r2.json         (local, machine summary)
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
REVIEW = Path(__file__).resolve().parents[2] / "control" / "reviews" / \
    "2026-10-23-quantity-pilot-r2.md"
MONTHS = ["2026-10", "2026-11", "2026-12"]
OBS_DATE = date(2026, 10, 22)          # max(stock_history.snapshot_date)
EXAMPLES = [
    ("① 最大缺口（12 月净需求最大）", "PTC/Linen-Natural-100-681-wow", 42.0),
    ("② 中位（正值升序取中位）", "TT0000910K0011672", 4.0),
    ("③ 零缺口（零缺口里月需求最大）", "TT0001325K0010512", 0.0),
]


def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def main() -> None:
    rows = {r["sku"]: r for r in csv.DictReader(
        (BP / "quantity_pilot_rows.csv").open(encoding="utf-8-sig"))}
    passed = [s for s, r in rows.items()
              if all(r.get(g) == "已证" for g in ("G1", "G2", "G3", "G4"))]
    dec = {r["SKU"]: r for r in csv.DictReader(
        (BP / "decision_v2.csv").open(encoding="utf-8-sig"))}
    replen = {r["SKU"]: r for r in csv.DictReader(
        (BP / "replenishment_v2.csv").open(encoding="utf-8-sig"))}

    period_rows = []
    agg = defaultdict(lambda: dict(demand=0.0, net=0.0, n=0, unknown=0))
    for sku in sorted(passed):
        d = dec.get(sku, {})
        rate = num(d.get("月需求率"))
        on_hand = num(d.get("可用"))
        cum = 0.0
        started = False
        for m in MONTHS:
            need = date(int(m[:4]), int(m[5:7]), 1)
            computable = OBS_DATE <= need
            if not computable:
                period_rows.append(dict(
                    sku=sku, month=m, need_date=need.isoformat(),
                    stock_obs_date=OBS_DATE.isoformat(),
                    stock_status="unknown_asof", monthly_demand=round(rate, 3),
                    cumulative_demand="", on_hand="", net_demand="不可算",
                    note="观测日晚于桶起点：该桶库存不可用于抵扣"))
                agg[m]["unknown"] += 1
                continue
            if not started:
                cum = 0.0
                started = True
            cum += rate
            net = max(0.0, cum - on_hand)
            period_rows.append(dict(
                sku=sku, month=m, need_date=need.isoformat(),
                stock_obs_date=OBS_DATE.isoformat(), stock_status="observed_before_need",
                monthly_demand=round(rate, 3), cumulative_demand=round(cum, 3),
                on_hand=round(on_hand, 3), net_demand=round(net, 3),
                note="假设：快照(10-22)与桶起点之间的出库未观测"))
            agg[m]["demand"] += rate
            agg[m]["net"] += net
            agg[m]["n"] += 1

    with (BP / "quantity_pilot_r2_periods.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(period_rows[0].keys()))
        w.writeheader()
        w.writerows(period_rows)

    n_buckets = len(passed) * len(MONTHS)
    n_computable = sum(a["n"] for a in agg.values())
    n_unknown = sum(a["unknown"] for a in agg.values())

    # ---- three diagnostic chains -------------------------------------
    def chain(sku, label):
        d = dec.get(sku, {})
        rep = replen.get(sku, {})
        r = rows.get(sku, {})
        rate = num(d.get("月需求率"))
        on_hand = num(d.get("可用"))
        nov_net = max(0.0, rate - on_hand)
        dec_net = max(0.0, rate * 2 - on_hand)
        return dict(
            label=label, sku=sku, warehouse=d.get("仓", ""),
            demand_source="T5 预测：" + (rep.get("预测方法(实际使用)") or "—"),
            monthly_rate=rate, stock_observed=OBS_DATE.isoformat(),
            on_hand=on_hand, po_open=d.get("PO未结", ""), transit=d.get("在途", ""),
            gates="/".join(r.get(g, "") for g in ("G1", "G2", "G3", "G4")),
            oct_status="unknown_asof（10-22 > 10-01，不可抵扣）",
            nov_net=round(nov_net, 3), dec_net=round(dec_net, 3),
            old_dec_net=next((float(p["net_demand"]) for p in
                              csv.DictReader((BP / "quantity_pilot_periods.csv")
                                             .open(encoding="utf-8-sig"))
                              if p["sku"] == sku and p["month"] == "2026-12"), None))

    chains = [chain(s, lab) for lab, s, _v in EXAMPLES]

    summary = dict(
        schema_version="quantity_pilot_r2/1",
        passed_skus=len(passed), buckets=n_buckets,
        computable=n_computable, unknown=n_unknown,
        reconcile=f"{n_computable} + {n_unknown} = {n_computable + n_unknown} == {n_buckets}",
        reconcile_ok=(n_computable + n_unknown == n_buckets),
        month_agg={m: dict(demand=round(agg[m]["demand"], 1), net=round(agg[m]["net"], 1),
                           n=agg[m]["n"], unknown=agg[m]["unknown"]) for m in MONTHS},
        stock_observation_date=OBS_DATE.isoformat(),
        examples=[{k: v for k, v in c.items()} for c in chains],
        void_numbers={
            "old_oct_net_total": 44.7,
            "old_nov_net_total": 124.3,
            "old_dec_net_total": 212.0,
            "reason": "旧表用 10/22 快照抵扣 10/01 起的需求（含 10 月桶），时间口径不成立",
        })
    (BP / "quantity_pilot_r2.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- report --------------------------------------------------------
    L = ["---", "okf: v0.1", "type: Review",
         "title: 数量试点 R2：时间口径纠正 + 诊断三例证据链",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读离线；数量暂不验收；不给可下单量；行级数据留本地",
         "---", "",
         "# 数量试点 R2", "",
         "> Codex2 裁决：**206 仅为 B 情景候选，A 仍为 0；计算与索证并行，现表数量暂不验收**。", "",
         "## ① 时间口径纠正", "",
         f"- 唯一库存快照观测日 **{OBS_DATE.isoformat()}**（`stock_history.max(snapshot_date)`）。",
         "- 规则：桶的**需要日**早于观测日 → 该桶库存 `unknown_asof`，**净需求不可算**（不是 0，也不是缺口）。",
         "", "| 桶 | 需要日 | 观测日 ≤ 需要日？ | 库存状态 | 净需求 |", "|---|---|---|---|---|",
         "| 2026-10 | 2026-10-01 | 否（10-22 晚 21 天） | `unknown_asof` | **不可算** |",
         "| 2026-11 | 2026-11-01 | 是 | observed_before_need | 可算（含假设） |",
         "| 2026-12 | 2026-12-01 | 是 | observed_before_need | 可算（含假设） |", "",
         "**纠正前 → 纠正后（10 月桶）**：旧表把 10/22 的在手当作 10/01 的期初，"
         "10 月净需求合计 44.7 属于**时间口径错误**；现在 10 月桶一律记「不可算」。", "",
         "**可算桶的残余假设（逐行写在本地 CSV）**：快照 10-22 到桶起点（11-01/12-01）之间的出库未观测，"
         "默认不显著——这是 B 情景假设，需业务批准。", "",
         "## ② 桶级对账（206 × 3 = 618）", "",
         f"- 可算桶 **{n_computable}**（11 月 + 12 月），不可算桶 **{n_unknown}**（10 月）。",
         f"- 对账：{n_computable} + {n_unknown} = {n_computable + n_unknown} = **{n_buckets}**"
         f" {'✅' if n_computable + n_unknown == n_buckets else '❌'}", "",
         "| 月份 | 需求合计 | 净需求合计 | 可算 SKU | 不可算 |", "|---|---:|---:|---:|---:|"]
    for m in MONTHS:
        a = agg[m]
        L.append(f"| {m} | {round(a['demand'],1)} | "
                 f"{round(a['net'],1) if a['n'] else '不可算'} | {a['n']} | {a['unknown']} |")
    L += ["", "> 净需求只在可算桶内累计，**不把 10 月需求带进 11/12 月**；"
          "这与旧表的 3 个月累计口径不同，旧表的 11/12 月数字因此作废。", "",
          "## ③ 诊断三例证据链（Codex2 指定，未换样）", ""]
    for c in chains:
        L += [f"### {c['label']} · `{c['sku']}`", "",
              f"- **需求来源**：{c['demand_source']}；仓 `{c['warehouse']}`。",
              f"- **月份口径**：月需求率 {c['monthly_rate']}（T5 平月率，无日期，月桶即最细粒度）。",
              f"- **在手**：{c['on_hand']}，观测日 **{c['stock_observed']}**；"
              f"未结 PO `{c['po_open'] or '无记录'}`、在途 `{c['transit'] or '0'}`。",
              f"- **四门**：{c['gates']}（G1/G2/G3/G4）。",
              f"- **净需求（纠正后）**：10 月 `{c['oct_status']}`；"
              f"11 月 = max(0, {c['monthly_rate']} − {c['on_hand']}) = **{c['nov_net']}**；"
              f"12 月 = max(0, 2×{c['monthly_rate']} − {c['on_hand']}) = **{c['dec_net']}**。",
              f"- **与旧表对比**：旧表 12 月 {c['old_dec_net']}（含 10 月桶累计）"
              + ("；该口径作废，纠正后为 " + str(c['dec_net']) + "。"
                 if c['old_dec_net'] != c['dec_net']
                 else "；口径作废，但纠正后仍为 " + str(c['dec_net']) + "（数字巧合相同，不可沿用旧依据）。"),
              "- **需要日**：2026-11-01 / 2026-12-01；**成立条件**：10-22 快照可作桶期初、"
              "10-22→桶起点无未观测出库、需求=预测。",
              "- **批次**：**B**（假设：需求=预测、快照即期初、无未观测出库、无在途/PO/WO）。"]
        if c["label"].startswith("③"):
            L += ["- **措辞**：**在当前证据下未观测到缺口**——不是「已证不需补货」。"
                  "要下结论还需：① 单位换算依据（UOM）；② 10-22→11-01 的出库记录；"
                  "③ 该仓可售/占用口径。"]
        L.append("")
    L += ["## ④ 证据索取清单（最小集 + 责任角色）", "",
          "| 角色 | 要什么 | 为什么需要 | 缺了会怎样 |", "|---|---|---|---|",
          "| 运营 | 需求来源/预测政策、内部 SO 语义与冲减规则 | 决定需求桶与是否重复 | 重叠未处理 → 拒报数量 |",
          "| 仓储 | 同仓库存的观测日期、可售与占用口径 | 判断桶期初库存是否可用 | 观测日不明 → 该桶不可算 |",
          "| 主数据 | 单位换算（UOM）依据 | 四检不证明换算 | 单位未证 → 拒报数字 |",
          "| 采购/生产 | 完整未结 PO/WO 行、剩余量、DN/SE 关联、ETA 依据 | 供给能否去重与定时 | ETA 未知 → 仅条件情景 |", "",
          "## ⑤ 现表哪些数字被作废", "",
          "| 数字 | 旧值 | 状态 |", "|---|---:|---|",
          "| 10 月净需求合计 | 44.7 | **作废**（用 10/22 快照抵扣 10/01 起的需求） |",
          "| 11 月净需求合计 | 124.3 | **作废**（含 10 月桶累计） |",
          "| 12 月净需求合计 | 212.0 | **作废**（含 10 月桶累计） |",
          "| 三例的旧 12 月净需求（42 / 4 / 0） | — | 42 与 4 作废；0 需按新口径重述 |",
          "",
          "**仍然有效**：四门判定（790 → 206）、A/B/拒绝三分（0/206/584）与 618 桶的对账骨架；"
          "只有**数量**暂不验收。", "",
          "## 边界", "",
          "- 不给可下单量；MOQ/包装/预算不在本表；需求批准 ≠ 订单批准。",
          "- 行级结果在本地 `out/business_phase/quantity_pilot_r2_periods.csv`，报告只放聚合与三例。", ""]

    REVIEW.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps(dict(passed=len(passed), buckets=n_buckets,
                          computable=n_computable, unknown=n_unknown,
                          reconcile_ok=(n_computable + n_unknown == n_buckets),
                          month_agg={m: dict(net=round(agg[m]['net'],1), n=agg[m]['n'],
                                             unknown=agg[m]['unknown']) for m in MONTHS},
                          chains=[(c['sku'], c['nov_net'], c['dec_net'], c['old_dec_net'])
                                  for c in chains]), ensure_ascii=False))


if __name__ == "__main__":
    main()
