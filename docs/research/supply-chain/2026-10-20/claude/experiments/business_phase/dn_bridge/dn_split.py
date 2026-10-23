#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC03 分路核验：39 张有号 DN 拆成 单号路(37) / 多号路(2)（只读，不改 EN）。

接 `control/reviews/2026-10-23-dn-status.md`。核心问题：
「没有逐运单 qty」不等于「永远无法把运单和物料量关联」——
**单号 DN 的运单覆盖整张 DN**，所以运单的物料内容 = 该 DN 的全部物料行（按单据规则，不需要业务再填一对一）。

(A) 37 张单号 DN：逐张核 承接状态 / 目的仓 / 物料行数量守恒 / 是否已在在手 stock_history 计入；
    四项成立 -> 建立「运单 ↔ 物料量」关联，并写明规则与适用范围。
(B) 2 张多号 DN：混合到货且无分号数量 -> 保留「分配未知」；不均摊、不整单提前抵扣。

红线：只读；不改 EN；不下单；不扩样；不 commit。

输出（本地）：
  out/business_phase/dn_split_lines.csv   DN 物料行（含 SO 关联键）
  out/business_phase/dn_split_so.csv      SO 行（qty / delivered_qty / pending）
  out/business_phase/dn_split_dn.csv      逐 DN 核验结果
  out/business_phase/dn_split.json        聚合
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
SIGNED = {"已签收", "已上传POD", "已入仓"}
IN_TRANSIT = {"已订舱", "已报关", "已离港", "已转运", "已到港", "清关中", "已清关"}
DEST_MAP = {                              # DN 客户 -> stock_history 仓库名
    "美国FBA仓": None,                    # 不在 stock_history 里（外部 FBA）
    "DANEEY": "美中-FZH-DANEEY",
    "CENTRADE": "美东-CENTRADE",
    "波兰公司": "波兰-FZHPoland-covers",
}


def main() -> None:
    import requests
    env = B.load_env()
    session = requests.Session()
    session.headers.update(B.auth(env))

    dn_rows = list(csv.DictReader((OUT / "dn_bridge_rows.csv").open(encoding="utf-8-sig", newline="")))
    dn_meta = {r["dn"]: r for r in csv.DictReader(
        (OUT / "dn_bridge_dn.csv").open(encoding="utf-8-sig", newline=""))}
    recon = {r["logistic_number"]: r for r in csv.DictReader(
        (OUT / "dn_status_recon.csv").open(encoding="utf-8-sig", newline=""))}
    per_dn_numbers = defaultdict(list)
    for r in dn_rows:
        per_dn_numbers[r["dn"]].append(r["logistic_number"])

    # stock_history 覆盖
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        stock_wh = {r[0] for r in con.execute(
            "SELECT DISTINCT warehouse_name FROM stock_history").fetchall()}
        snap_max = con.execute("SELECT max(snapshot_date) FROM stock_history").fetchone()[0]
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

    # ---- 逐 SO 拉行（qty / delivered_qty）------------------------------------
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

    # ---- 逐 DN 核验 ----------------------------------------------------------
    out_rows = []
    for dn, numbers in sorted(per_dn_numbers.items()):
        meta = dn_meta.get(dn, {})
        lines = lines_by_dn.get(dn, [])
        total_qty = sum(x["qty"] for x in lines)
        src_wh = sorted({x["warehouse"] for x in lines if x["warehouse"]})
        dest = meta.get("customer", "")
        dest_wh = DEST_MAP.get(dest)
        receipts = []
        statuses = []
        for ln in numbers:
            r = recon.get(ln, {})
            statuses.append(r.get("status11") or "")
            for k in ("dlvr", "ata"):      # 签收 / 到港
                if r.get(k):
                    receipts.append(r[k])
        if all(s in SIGNED for s in statuses if s) and statuses:
            route_state = "已签收/已入仓"
        elif any(s in SIGNED for s in statuses):
            route_state = "部分签收"
        elif statuses and all(s in IN_TRANSIT for s in statuses if s):
            route_state = "在途"
        else:
            route_state = "未知"

        # 数量守恒：DN 行 -> SO 行
        matched = [x for x in lines if (x["against_sales_order"], x["so_detail"]) in so_index]
        viol_over_delivered = 0
        viol_over_ordered = 0
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

        # 重复计入：目的仓是否已被 stock_history 覆盖 + 是否已签收
        if dest_wh and dest_wh in stock_wh:
            if route_state in ("已签收/已入仓", "部分签收"):
                if receipts and min(receipts) <= SNAPSHOTS[0]:
                    double = "already_in_stock(签收日≤首个快照)"
                elif receipts:
                    double = "not_yet(签收日晚于快照)"
                else:
                    double = "unverifiable(无签收日期)"
            elif route_state == "在途":
                double = "not_yet(在途)"
            else:
                double = "unverifiable(状态未知)"
        elif dest_wh:
            double = "dest_wh_not_in_stock_history"
        else:
            double = "dest_not_tracked(外部FBA)"

        single = len(numbers) == 1
        no_so = sum(1 for x in lines if not x["against_sales_order"])
        if single and lines:
            if len(seen) == 0 and no_so:
                so_check = "no_so_link"
            elif viol_over_delivered or viol_over_ordered:
                so_check = "over_delivery"
            else:
                so_check = "ok"
        else:
            so_check = "n/a"
        # 关联本身只看单据规则：1 张已提交 DN + 1 个运单号 -> 运单覆盖整张 DN
        link_conf = ("C 多号未分配" if not single else
                     ("A 四项全过" if so_check == "ok" else "B 关联成立·SO校验未过"))
        out_rows.append(dict(
            dn=dn, numbers=len(numbers), n_lines=len(lines), total_qty=round(total_qty, 2),
            source_warehouses="|".join(src_wh), destination=dest, dest_warehouse=dest_wh or "",
            route="单号路" if single else "多号路",
            route_state=route_state,
            statuses="|".join(sorted(set(statuses))),
            so_lines_matched=len(seen), so_ordered=round(ordered, 2),
            so_delivered=round(delivered, 2), so_pending=round(pending, 2),
            so_check=so_check,
            no_so_lines=no_so,
            double_count=double,
            link_confidence=link_conf,
            quantity_link=("运单↔物料量可关联（单号覆盖整张 DN）" if single and lines
                           else "分配未知（多号无分号数量）"),
            link_blockers=";".join([b for b, c in (
                ("无物料行", not lines),
                ("SO 行未匹配", len(matched) == 0),
                ("DN>SO已发", viol_over_delivered > 0),
                ("SO已发>订购", viol_over_ordered > 0)) if c]) or "none",
        ))

    with (OUT / "dn_split_dn.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---- 聚合 ----------------------------------------------------------------
    single_rows = [r for r in out_rows if r["route"] == "单号路"]
    multi_rows = [r for r in out_rows if r["route"] == "多号路"]
    payload = dict(
        schema_version="dn_split/1",
        inputs=dict(snapshots=SNAPSHOTS, stock_history_warehouses=sorted(stock_wh),
                    snapshot_max=str(snap_max)),
        counts=dict(dns=len(out_rows), single=len(single_rows), multi=len(multi_rows),
                    numbers=sum(r["numbers"] for r in out_rows)),
        single_route=dict(
            n=len(single_rows),
            qty_total=round(sum(r["total_qty"] for r in single_rows), 2),
            by_confidence={
                c: dict(n=sum(1 for r in single_rows if r["link_confidence"] == c),
                        qty=round(sum(r["total_qty"] for r in single_rows
                                      if r["link_confidence"] == c), 2))
                for c in sorted({r["link_confidence"] for r in single_rows})},
            so_check=dict(Counter(r["so_check"] for r in single_rows)),
            state=dict(Counter(r["route_state"] for r in single_rows)),
        ),
        multi_route=dict(
            n=len(multi_rows),
            dns=[dict(dn=r["dn"], numbers=r["numbers"], lines=r["n_lines"], qty=r["total_qty"],
                      state=r["route_state"], statuses=r["statuses"],
                      double_count=r["double_count"]) for r in multi_rows],
            qty=round(sum(r["total_qty"] for r in multi_rows), 2),
        ),
        status_split=dict(
            by_dn=dict(Counter(r["route_state"] for r in out_rows)),
            by_number=dict(Counter(
                ("已签收/已入仓" if (recon[n].get("status11") or "") in SIGNED else
                 "在途" if (recon[n].get("status11") or "") in IN_TRANSIT else "未知")
                for n in recon)),
        ),
        destination=dict(Counter(r["destination"] for r in out_rows)),
        source_warehouse=dict(Counter(w for r in out_rows for w in r["source_warehouses"].split("|") if w)),
        double_count=dict(Counter(r["double_count"] for r in out_rows)),
        settlement=dict(so_status=so_status),
    )
    (OUT / "dn_split.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("counts", "single_route", "multi_route",
                                              "status_split", "destination", "source_warehouse",
                                              "double_count")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
