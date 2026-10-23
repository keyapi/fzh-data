#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC03 DN 分路核验 R2（只读，不改 EN）—— 修 301 的 D01 / D02。

D01（证据分层）
  * 只凭「目的仓 + 状态 + 日期」**不能**断言某批货已计入库存。
    旧字段 already_in_stock / not_yet 已删除，改为：
      received_before_snapshot_candidate  —— 仅表示「签收日 ≤ CUTOFF，是个候选」
      stock_inclusion_unknown             —— 其余一律未知（附具体原因）
    `credited_qty` 恒为 null：本轮**不认任何数量入账**。
  * 单据关联（运单 ↔ DN 整单）与数量入账（DN → 库存账面）**分开两列**，不混为一谈。
  * ATA（到港）与 dlvr（签收）分开记录；**只有 dlvr 参与候选判定**，ATA 永不当作签收。
  * 全篇固定 **CUTOFF = 2026-10-20**（stock_history 第一个快照日），不再用 10-22 另立口径。

D02（禁止跨 UOM 合计）
  * 不再有「DN 总件数」这种数：数量以 (item_code, UOM, role) 的**原始向量**输出。
  * 跨 UOM 不相加；只有换算/BOM 证据成立才谈目标 SKU 数量 —— 本批**不成立**（套→个 无依据），
    所以输出里没有任何"目标 SKU 数量"。

输出（本地）：
  out/business_phase/dn_split_dn.csv         逐 DN 核验（含 stock_inclusion / credited_qty=null）
  out/business_phase/dn_split_qty_vectors.csv (item_code × UOM × role 的原始向量)
  out/business_phase/dn_split_lines.csv      DN 物料行
  out/business_phase/dn_split_so.csv         SO 行
  out/business_phase/dn_split.json           聚合（无跨 UOM 总量）
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import dn_bridge as B                      # noqa: E402  (env / auth / get)

OUT = B.OUT
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
SNAPSHOTS = ["2026-10-20", "2026-10-21", "2026-10-22"]
CUTOFF = SNAPSHOTS[0]                     # 唯一 cutoff：签收候选只比这一天
SIGNED = {"已签收", "已上传POD", "已入仓"}
IN_TRANSIT = {"已订舱", "已报关", "已离港", "已转运", "已到港", "清关中", "已清关"}
DEST_MAP = {"美国FBA仓": None, "DANEEY": "美中-FZH-DANEEY",
            "CENTRADE": "美东-CENTRADE", "波兰公司": "波兰-FZHPoland-covers"}


def load_roles():
    """role：mapped_sku（直接映射到通途码）/ component_via_bom（BOM 可推导）/ unmapped。
    与 map_evidence.py 同一判据，独立计算以免循环依赖。"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        mapped = {r[0] for r in con.execute("SELECT DISTINCT item_code FROM sku_item").fetchall()}
        parents = defaultdict(set)
        for node, root in con.execute("SELECT node, root FROM bom_exploded").fetchall():
            parents[node].add(root)
    finally:
        con.close()

    def role(code):
        if code in mapped:
            return "mapped_sku"
        ps = parents.get(code)
        if ps and any(r in mapped for r in ps):
            return "component_via_bom"
        return "unmapped"
    return role


def main() -> None:
    import requests
    env = B.load_env()
    session = requests.Session()
    session.headers.update(B.auth(env))
    role_of = load_roles()

    dn_rows = list(csv.DictReader((OUT / "dn_bridge_rows.csv").open(encoding="utf-8-sig", newline="")))
    dn_meta = {r["dn"]: r for r in csv.DictReader(
        (OUT / "dn_bridge_dn.csv").open(encoding="utf-8-sig", newline=""))}
    recon = {r["logistic_number"]: r for r in csv.DictReader(
        (OUT / "dn_status_recon.csv").open(encoding="utf-8-sig", newline=""))}
    per_dn_numbers = defaultdict(list)
    for r in dn_rows:
        per_dn_numbers[r["dn"]].append(r["logistic_number"])

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        stock_wh = {r[0] for r in con.execute(
            "SELECT DISTINCT warehouse_name FROM stock_history").fetchall()}
    finally:
        con.close()

    # ---- 逐 DN 拉物料行 ------------------------------------------------------
    line_rows, so_names = [], set()
    for dn in sorted(per_dn_numbers):
        code, body = B.get(session, f"/api/resource/Delivery Note/{dn}")
        if code != 200:
            continue
        d = body.get("data") or {}
        for it in d.get("items") or []:
            line_rows.append(dict(
                dn=dn, item_code=it.get("item_code"), qty=float(it.get("qty") or 0),
                warehouse=it.get("warehouse") or "", uom=it.get("uom") or "",
                against_sales_order=it.get("against_sales_order") or "",
                so_detail=it.get("so_detail") or ""))
            if it.get("against_sales_order"):
                so_names.add(it["against_sales_order"])
        time.sleep(B.SLEEP)

    so_rows, so_status = [], {}
    for so in sorted(so_names):
        code, body = B.get(session, f"/api/resource/Sales Order/{so}")
        if code != 200:
            continue
        d = body.get("data") or {}
        so_status[so] = d.get("status")
        for it in d.get("items") or []:
            so_rows.append(dict(so=so, so_item=it.get("name"), item_code=it.get("item_code"),
                                qty=float(it.get("qty") or 0),
                                delivered_qty=float(it.get("delivered_qty") or 0)))
        time.sleep(B.SLEEP)

    for name, rows in (("dn_split_lines.csv", line_rows), ("dn_split_so.csv", so_rows)):
        with (OUT / name).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    so_index = {(r["so"], r["so_item"]): r for r in so_rows}
    lines_by_dn = defaultdict(list)
    for r in line_rows:
        lines_by_dn[r["dn"]].append(r)

    # ---- 逐 DN 核验（D01：单据级 vs 数量级分开）------------------------------
    out_rows, vector_rows = [], []
    for dn, numbers in sorted(per_dn_numbers.items()):
        meta = dn_meta.get(dn, {})
        lines = lines_by_dn.get(dn, [])
        dest = meta.get("customer", "")
        dest_wh = DEST_MAP.get(dest)

        # ATA 与签收日**分开**存；只有 dlvr 参与候选
        statuses, dlvr_dates, ata_dates = [], [], []
        for ln in numbers:
            r = recon.get(ln, {})
            statuses.append(r.get("status11") or "")
            if r.get("dlvr"):
                dlvr_dates.append(r["dlvr"])
            if r.get("ata"):
                ata_dates.append(r["ata"])

        if statuses and all(s in SIGNED for s in statuses if s):
            route_state = "已签收/已入仓"
        elif any(s in SIGNED for s in statuses):
            route_state = "部分签收"
        elif statuses and all(s in IN_TRANSIT for s in statuses if s):
            route_state = "在途"
        else:
            route_state = "未知"

        # 数量守恒：DN 行 -> SO 行（只判单据，不涉库存）
        matched = [x for x in lines if (x["against_sales_order"], x["so_detail"]) in so_index]
        viol_over_delivered = viol_over_ordered = 0
        ordered = delivered = pending = 0.0
        seen = set()
        for x in matched:
            k = (x["against_sales_order"], x["so_detail"])
            if k in seen:
                continue
            seen.add(k)
            so_it = so_index[k]
            dn_qty = sum(y["qty"] for y in lines
                         if y["against_sales_order"] == k[0] and y["so_detail"] == k[1])
            ordered += so_it["qty"]
            delivered += so_it["delivered_qty"]
            pending += max(0.0, so_it["qty"] - so_it["delivered_qty"])
            if dn_qty > so_it["delivered_qty"] + 1e-6:
                viol_over_delivered += 1
            if so_it["delivered_qty"] > so_it["qty"] + 1e-6:
                viol_over_ordered += 1

        # D01：只给「候选」，不给「已入账」； credited_qty 恒为 null
        signed_state = route_state in ("已签收/已入仓", "部分签收")
        if not dest_wh:
            stock_inclusion, unknown_reason = "stock_inclusion_unknown", "dest_not_tracked"
        elif dest_wh not in stock_wh:
            stock_inclusion, unknown_reason = "stock_inclusion_unknown", "dest_not_in_stock_history"
        elif not signed_state:
            stock_inclusion, unknown_reason = "stock_inclusion_unknown", (
                "in_transit" if route_state == "在途" else "status_unknown")
        elif not dlvr_dates:
            stock_inclusion, unknown_reason = "stock_inclusion_unknown", "no_receipt_date"
        elif min(dlvr_dates) <= CUTOFF:
            stock_inclusion, unknown_reason = "received_before_snapshot_candidate", "candidate_only"
        else:
            stock_inclusion, unknown_reason = "stock_inclusion_unknown", "receipt_after_cutoff"

        single = len(numbers) == 1
        no_so = sum(1 for x in lines if not x["against_sales_order"])
        so_check = ("n/a" if not (single and lines) else
                    "no_so_link" if len(seen) == 0 and no_so else
                    "over_delivery" if (viol_over_delivered or viol_over_ordered) else "ok")
        link_conf = ("C 多号未分配" if not single else
                     ("A 四项全过" if so_check == "ok" else "B 关联成立·SO校验未过"))

        # D02：数量按 (item_code, UOM, role) 输出向量；不求和
        vec = defaultdict(float)
        for x in lines:
            r_ = role_of(x["item_code"])
            vec[(x["item_code"], x["uom"], r_)] += x["qty"]
            vector_rows.append(dict(dn=dn, item_code=x["item_code"], uom=x["uom"], role=r_,
                                    qty=round(x["qty"], 4),
                                    source_line_warehouse=x["warehouse"]))
        qty_by_uom = defaultdict(float)
        for x in lines:
            qty_by_uom[x["uom"]] += x["qty"]

        out_rows.append(dict(
            dn=dn, numbers=len(numbers), n_lines=len(lines),
            dest=dest, dest_warehouse=dest_wh or "",
            route="单号路" if single else "多号路",
            route_state=route_state,
            statuses="|".join(sorted(set(statuses))),
            dlvr_dates="|".join(sorted(set(dlvr_dates))),
            ata_dates="|".join(sorted(set(ata_dates))),
            # 单据级
            doc_link=("运单↔DN 整单（单号）" if single and lines else "分配未知（多号）"),
            so_lines_matched=len(seen), so_ordered=round(ordered, 2),
            so_delivered=round(delivered, 2), so_pending=round(pending, 2),
            so_check=so_check, no_so_lines=no_so, link_confidence=link_conf,
            # 数量级：明确分层
            stock_inclusion=stock_inclusion,
            stock_inclusion_reason=unknown_reason,
            credited_qty="",                      # null：本轮不认任何数量入账
            qty_by_uom="|".join(f"{u}:{round(v, 2)}" for u, v in sorted(qty_by_uom.items())),
        ))

    with (OUT / "dn_split_dn.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # D02：向量表（同 dn/item/uom/role 合并行）
    agg_vec = defaultdict(float)
    for r in vector_rows:
        agg_vec[(r["dn"], r["item_code"], r["uom"], r["role"])] += r["qty"]
    vector_out = [dict(dn=k[0], item_code=k[1], uom=k[2], role=k[3], qty=round(v, 4))
                  for k, v in sorted(agg_vec.items())]
    with (OUT / "dn_split_qty_vectors.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(vector_out[0].keys()))
        w.writeheader()
        w.writerows(vector_out)

    # ---- 聚合：只给分 UOM / 分 role 的向量，不给跨 UOM 总量 -------------------
    single_rows = [r for r in out_rows if r["route"] == "单号路"]
    multi_rows = [r for r in out_rows if r["route"] == "多号路"]
    by_uom, by_role_uom = defaultdict(float), defaultdict(float)
    for r in vector_out:
        by_uom[r["uom"]] += r["qty"]
        by_role_uom[(r["role"], r["uom"])] += r["qty"]

    payload = dict(
        schema_version="dn_split/2",
        cutoff=CUTOFF,
        cutoff_note=("唯一 cutoff = stock_history 第一个快照日；"
                     "签收日 ≤ CUTOFF 只产生「候选」，不产生「已入账」"),
        counts=dict(dns=len(out_rows), single=len(single_rows), multi=len(multi_rows),
                    numbers=sum(r["numbers"] for r in out_rows)),
        linkage=dict(
            single_route=dict(
                n=len(single_rows),
                by_confidence={c: dict(n=sum(1 for r in single_rows if r["link_confidence"] == c))
                               for c in sorted({r["link_confidence"] for r in single_rows})},
                so_check=dict(Counter(r["so_check"] for r in single_rows)),
                state=dict(Counter(r["route_state"] for r in single_rows)),
            ),
            multi_route=dict(n=len(multi_rows),
                             dns=[dict(dn=r["dn"], numbers=r["numbers"], lines=r["n_lines"],
                                       state=r["route_state"], statuses=r["statuses"])
                                  for r in multi_rows]),
        ),
        stock_inclusion=dict(
            states=dict(Counter(r["stock_inclusion"] for r in out_rows)),
            reasons=dict(Counter(r["stock_inclusion_reason"] for r in out_rows)),
            credited_qty="null（全部 39 张；本轮不做数量入账）",
            note=("received_before_snapshot_candidate 仅表示「签收日 ≤ CUTOFF，值得去账面核」，"
                  "不等于该批货已在库存中；其余一律 stock_inclusion_unknown"),
        ),
        quantities=dict(
            rule="按 (item_code, UOM, role) 输出原始向量；跨 UOM 不合计",
            by_uom={u: round(v, 2) for u, v in sorted(by_uom.items())},
            by_role_uom={f"{r}|{u}": round(v, 2) for (r, u), v in sorted(by_role_uom.items())},
            target_sku_qty="not computed：套→个 无换算依据（KZKP1010 无 BOM 头、库存 uom_basis=unknown）",
            n_vector_rows=len(vector_out),
        ),
        status_split=dict(by_dn=dict(Counter(r["route_state"] for r in out_rows)),
                          by_number=dict(Counter(
                              ("已签收/已入仓" if (recon[n].get("status11") or "") in SIGNED else
                               "在途" if (recon[n].get("status11") or "") in IN_TRANSIT else "未知")
                              for n in recon))),
        destination=dict(Counter(r["dest"] for r in out_rows)),
    )
    (OUT / "dn_split.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("cutoff", "counts", "linkage",
                                              "stock_inclusion", "quantities", "status_split")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
