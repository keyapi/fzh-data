#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C package: join A's routing evidence and B's verified linkage into one
human-decision pack over the existing 1,328-SKU recommendation set (OFFLINE).

Reads only local artifacts (no production access, no writes outside its output):

  out/business_phase/decision_v2.csv        base rows (SKU x warehouse, 2,309)
  out/business_phase/usability_audit.csv    allocation ratio, evidence gaps, owner
  out/business_phase/wo_dn_coverage.csv     WO material found / open WO qty / ETA
  experiments/business_phase/forecast_eval/routing.csv   A: type, method, features
  out/auto_order/linkage_audit_v2.csv        B: explicit SO linkage, DN net, anomalies
  order_store.duckdb                        sku_item map (read-only)

Design rules baked into the output:

1. Three demand views stay in separate columns:
     terminal forecast (monthly rate / P50 L90), internal SO (a replenishment /
     production instruction, never terminal demand), external SO (contract).
   Internal SO is never added to terminal demand and never deducted from it.
2. Known and unknown supply are separate columns. `在途` / `PO未结` have no
   dates and `在产 WO` is missing for most rows: they are marked `_无日期` /
   `未证` and never silently folded into an on-hand number.
3. Horizons L15 / L30 / L60 are three separate columns and are never summed.
4. A WO without a date is shown as three conditional scenarios
   (不假设 / 假设L30可到 / 假设L60可到), each labelled 未证.
5. The quantity recommendation is a *conditional* quantity: null when the row
   is out of scope or on-hand is unknown. MOQ/pack rounding is NOT applied
   (those fields are missing), so the number is not a purchase order.
6. A/B numbers are read, never recomputed or altered.

Decision status rule (documented, not inferred):
    范围外   : row status C (UOM / mapping unproven)
    可决策   : status B, on-hand known, and the L30 gap (on-hand + in-transit +
               open PO) is <= 0 -> "no action needed, facts complete"
    待补证   : everything else (a positive gap depends on unproven supply)

Outputs: out/business_phase/final_bundle.csv, out/business_phase/final_bundle.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
BP = CLAUDE_DIR / "out" / "business_phase"
A_ROUTING = CLAUDE_DIR / "experiments" / "business_phase" / "forecast_eval" / "routing.csv"
B_LINKAGE = CLAUDE_DIR / "out" / "auto_order" / "linkage_audit_v2.csv"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")


def num(x):
    if x in (None, "", "None"):
        return None
    try:
        return float(x)
    except Exception:
        return None


def r2(x):
    return None if x is None else round(x, 2)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    base = read_csv(BP / "decision_v2.csv")
    replen = {(r["SKU"], r["仓"]): r for r in read_csv(BP / "replenishment_v2.csv")}
    use = {(r["SKU"], r["仓"]): r for r in read_csv(BP / "usability_audit.csv")}
    wo = {(r["SKU"], r["仓"]): r for r in read_csv(BP / "wo_dn_coverage.csv")}
    a_rows = {r["sku_hash"]: r for r in read_csv(A_ROUTING)}
    a_hashes = set(a_rows)
    b_rows = read_csv(B_LINKAGE)

    # ---- B: aggregate explicit linkage by EN item ---------------------
    b_item = defaultdict(lambda: dict(lines=0, internal=0.0, external=0.0,
                                      dn_net=0.0, over=0, dup=0, shared=0,
                                      linked=0))
    for r in b_rows:
        it = r.get("item")
        if not it:
            continue
        agg = b_item[it]
        agg["lines"] += 1
        q = num(r.get("demand")) or 0.0
        if r.get("internal") == "True":
            agg["internal"] += q
        else:
            agg["external"] += q
        agg["dn_net"] += num(r.get("dn_net")) or 0.0
        agg["over"] += 1 if ((num(r.get("dn_net")) or 0) > q + 0.005 and q > 0) else 0
        agg["dup"] += 1 if int(r.get("dn_rows") or 0) > 1 else 0
        agg["shared"] += 1 if r.get("line_link") == "so_level_only" else 0
        agg["linked"] += 1 if r.get("line_link") else 0

    con = duckdb.connect(args.db, read_only=True)
    try:
        item2skus = defaultdict(set)
        for sku, item in con.execute("SELECT sku, item_code FROM sku_item").fetchall():
            item2skus[item].add(sku)
    finally:
        con.close()

    decision_skus = {r["SKU"] for r in base}
    sku2items = defaultdict(set)
    for it, skus in item2skus.items():
        for s_ in skus:
            sku2items[s_].add(it)
    # only items that map to exactly one decision SKU can be attributed
    b_by_sku, b_ambiguous_items = {}, 0
    for item, agg in b_item.items():
        skus = item2skus.get(item, set()) & decision_skus
        if len(skus) == 1:
            b_by_sku[next(iter(skus))] = agg
        elif len(skus) > 1:
            b_ambiguous_items += 1

    # ---- per row -------------------------------------------------------
    out_rows = []
    for r in base:
        sku, wh = r["SKU"], r["仓"]
        u = use.get((sku, wh), {})
        w = wo.get((sku, wh), {})
        h = hashlib.sha256(sku.encode()).hexdigest()[:12]
        a = a_rows.get(h, {})
        in_a = h in a_hashes

        status = r.get("状态", "")
        rate = num(r.get("月需求率"))
        on_hand = num(r.get("可用"))
        transit = num(r.get("在途"))
        po_open = num(r.get("PO未结"))
        wo_qty = num(w.get("WO剩余量_不计供给"))
        existing_l90 = num(r.get("建议下限L90"))

        ratio = num(u.get("需求摊派比例")) or 0.0
        bagg = b_by_sku.get(sku)
        b_state = "absent"
        b_internal = b_external = b_dn = None
        b_flags = ""
        if bagg:
            b_state = "linked"
            b_internal = round(bagg["internal"] * ratio, 2) if ratio else 0.0
            b_external = round(bagg["external"] * ratio, 2) if ratio else 0.0
            b_dn = round(bagg["dn_net"] * ratio, 2) if ratio else 0.0
            flags = []
            if bagg["over"]:
                flags.append(f"历史超交付 {bagg['over']} 行")
            if bagg["dup"]:
                flags.append(f"多张 DN {bagg['dup']} 行")
            if bagg["shared"]:
                flags.append(f"仅 SO 级关联 {bagg['shared']} 行")
            b_flags = "；".join(flags)
        else:
            multi = [it for it in sku2items.get(sku, ())
                     if len(item2skus.get(it, set()) & decision_skus) > 1]
            if multi:
                b_state = "ambiguous"

        # horizons: three separate projections, never summed
        dem15 = None if rate is None else round(rate * 0.5, 2)
        dem30 = None if rate is None else round(rate, 2)
        dem60 = None if rate is None else round(rate * 2, 2)

        supply_l30_base = None
        if on_hand is not None:
            supply_l30_base = on_hand + (transit or 0.0) + (po_open or 0.0)
        gap15 = None if (on_hand is None or dem15 is None) else max(0.0, dem15 - on_hand)
        gap30 = None if (supply_l30_base is None or dem30 is None) else max(0.0, dem30 - supply_l30_base)
        gap60 = None if (supply_l30_base is None or dem60 is None) else max(0.0, dem60 - supply_l30_base)

        # WO scenarios — each labelled 未证, never collapsed
        if wo_qty is None:
            wo_no, wo_l30, wo_l60 = None, None, None
            wo_note = "未取得（在产 WO 不在快照）"
        else:
            wo_no = r2(gap30)
            wo_l30 = r2(max(0.0, (gap30 or 0.0) - wo_qty))
            wo_l60 = r2(max(0.0, (gap60 or 0.0) - wo_qty))
            wo_note = "数量有、日期未证"

        rec_l30 = None if gap30 is None else r2(max(0.0, gap30))
        rec_l60 = None if gap60 is None else r2(max(0.0, gap60))

        # decision status (documented rule)
        if status == "C":
            dec = "范围外"
        elif on_hand is None:
            dec = "待补证"
        elif gap30 is not None and gap30 <= 0:
            dec = "可决策"          # no action needed on known facts
        else:
            dec = "待补证"

        blockers = []
        if status == "C":
            blockers.append("UOM/映射未证")
        if on_hand is None:
            blockers.append("同仓库存未取得")
        if (transit or po_open) and gap30 is not None and gap30 > 0:
            blockers.append("在途/PO 无到货日期")
        if wo_qty is None and gap30 is not None and gap30 > 0:
            blockers.append("在产 WO 数量与日期均未证")
        if b_state != "linked":
            blockers.append("无显式 SO 关联（重复无法排除）" if b_state == "absent"
                            else "物料对应多 SKU，SO 关联无法归属")
        miss = (u.get("缺失类别") or "").strip()
        if miss:
            blockers.append(f"既有缺口：{miss}")

        out_rows.append(dict(
            SKU=sku, 仓=wh, 原状态=status, 决策状态=dec,
            终端需求_月率=rate, 终端需求_P50L90=num(r.get("需求P50(冲减前)")),
            内部SO_历史需求=b_internal, 外部SO_历史需求=b_external,
            B证据状态=b_state, B重复风险=b_flags or "",
            B_DN净交付_历史=b_dn,
            在手=on_hand, 在途_无日期=transit, PO未结_无日期=po_open,
            WO_未证=wo_qty, WO说明=wo_note,
            需求_L15=dem15, 需求_L30=dem30, 需求_L60=dem60,
            缺口_L15_保守=r2(gap15), 缺口_L30_含在途PO=r2(gap30),
            缺口_L60_含在途PO=r2(gap60),
            WO情景_不假设_L30=wo_no, WO情景_假设L30可到_L30=wo_l30,
            WO情景_假设L60可到_L60=wo_l60,
            建议量_L30_条件=rec_l30, 建议量_L60_条件=rec_l60,
            既有建议L90=existing_l90,
            A分型=(a.get("type") or "未评分(历史不足)") if in_a else "无A记录",
            A选模=a.get("method", ""),
            A证据起点=a.get("evidence_origin", ""),
            预测方法=(replen.get((sku, wh), {}) or {}).get("预测方法(实际使用)", ""),
            责任方=u.get("责任方", ""),
            blockers="；".join(blockers)))

    csv_path = BP / "final_bundle.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        wr.writeheader()
        wr.writerows(out_rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()[:16]

    # ---- one-page note --------------------------------------------------
    n = len(out_rows)
    dec = Counter(r["决策状态"] for r in out_rows)
    st = Counter(r["原状态"] for r in out_rows)
    a_state = Counter(r["A分型"] or "未覆盖" for r in out_rows)
    b_state = Counter(r["B证据状态"] for r in out_rows)
    skus = {r["SKU"] for r in out_rows}
    gap_pos = sum(1 for r in out_rows if (r["缺口_L30_含在途PO"] or 0) > 0)
    wo_known = sum(1 for r in out_rows if r["WO_未证"] is not None)
    on_hand_unknown = sum(1 for r in out_rows if r["在手"] is None)

    L = ["---", "okf: v0.1", "type: Report",
         "title: C 包：A+B 接回 1,328 建议的独立验收包",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 完成；离线复用 A/B；不改 A/B 数字",
         "artifacts:",
         "  - experiments/business_phase/build_final_bundle.py",
         "  - out/business_phase/final_bundle.csv",
         "---", "",
         "# C 包：A+B 接回 1,328 建议的独立验收包", "",
         "> 离线生成：只读既有产物与本地 DuckDB，**无生产访问、无写库**；"
         "A/B 的数字原样引用，不重算、不改动。", "",
         "## 1. 覆盖", "",
         f"- 行数 **{n}**（每 SKU×仓一行），SKU **{len(skus)}**",
         f"- 原状态分布：{dict(st)}",
         f"- 决策状态：**可决策 {dec.get('可决策', 0)} / 待补证 {dec.get('待补证', 0)} / "
         f"范围外 {dec.get('范围外', 0)}**"
         f"（可决策＝在已知事实上确认“无需动作”；需动作但依赖未证供给的一律待补证）",
         f"- A 分型覆盖：{dict(a_state)}（A 覆盖 1,237 / 1,328 SKU）",
         f"- B 关联覆盖：{dict(b_state)}"
         f"（B 的物料→SKU 只有 1:1 才可归属，歧义物料 {b_ambiguous_items} 个不摊派）",
         f"- L30 存在正缺口的行：**{gap_pos}**；在手未知：**{on_hand_unknown}**；"
         f"WO 数量已取得：**{wo_known}**",
         f"- CSV 哈希（sha256 前 16）：`{digest}`", "",
         "## 2. 三视图（分列，不混用）", "",
         "| 视图 | 列 | 口径 |", "|---|---|---|",
         "| 终端销售预测 | `终端需求_月率`、`终端需求_P50L90`、`需求_L15/L30/L60` | "
         "既有 T5 预测（AutoETS/MA3），A 只提供分型与方法证据 |",
         "| 内部 SO 补货/生产指令 | `内部SO_历史需求` | B 的显式关联（2024-11..2026-10 累计），"
         "按既有需求摊派比例分到仓；**不计入终端需求、不从外部扣减** |",
         "| 外部合同履约 | `外部SO_历史需求` | 同上，外部 SO 累计需求 |", "",
         "> 内部 SO 与外部 SO 的数字是**历史累计**，不是未结量（B 没有 SO 未结字段）；"
         "它们只用于判断“是否可能重复下单”，不进入任何缺口公式。", "",
         "## 3. 已知 / 未知供应（分列）", "",
         "| 字段 | 含义 | 是否证 |", "|---|---|---|",
         "| `在手` | 同仓可用库存 | 已证（缺失记 null） |",
         "| `在途_无日期` | 在途数量，**无到货日期** | 数量有、日期未证 |",
         "| `PO未结_无日期` | 未结 PO 数量，**无 ETA** | 数量有、日期未证 |",
         "| `WO_未证` | 在产 WO 剩余量（仅 32 行有材料） | 多数未取得 |",
         "| `B_DN净交付_历史` | B 的 DN 净交付（历史累计） | 已证（仅 1:1 物料可归属） |", "",
         "> `在途` / `PO未结` 为空表示**无该记录**（按 0 参与缺口计算）；`WO_未证` 为空表示"
         "**未取得**（不按 0 计，相关结论一律记未证）。", "",
         "## 4. 时间情景（L15 / L30 / L60 分列，**绝不相加**）", "",
         "- 需求：`需求_L15 = 月率×0.5`、`L30 = 月率`、`L60 = 月率×2`（线性投影，标注为假设）。",
         "- 缺口：`L15` 只算在手；`L30`/`L60` 计入在途与未结 PO（**假设能到**，无日期佐证）。",
         "- WO 三档：`不假设` / `假设L30可到` / `假设L60可到`，三列并列，每档都标未证；"
         "WO 数量缺失时三列都为 null 并写原因，不填 0。", "",
         "## 5. 使用限制", "",
         "1. 建议量是**条件量**：未套 MOQ/包装倍数（字段缺失），不能直接当采购单下。",
         "2. 绝大多数行的在产 WO 不在快照——任何依赖 WO 到货的判断都必须先补证。",
         "3. `在途`/`PO未结` 没有到货日期，L30/L60 的“能到”是假设，不是事实。",
         "4. 内部 SO 是补货/生产指令，不计入终端需求；外部 SO 用历史累计，不代表未结。",
         "5. B 的物料↔SKU 只有 1:1 才归属，多 SKU 物料记 `ambiguous`，不做摊派。",
         "6. 本包不判断库存真实性、不判断到货及时性，也不构成下单指令。", ""]

    (BP / "final_bundle.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"rows={n} skus={len(skus)} decision={dict(dec)} b={dict(b_state)} "
          f"a={dict(a_state)} gap_pos={gap_pos} wo_known={wo_known} sha={digest}")


if __name__ == "__main__":
    main()
