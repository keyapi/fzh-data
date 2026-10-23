#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC10 入批准备（只读，不改母集、不出量）。

对 SC10 差集里 271 个「有库存无近期销售」候选做入批前置评审：
  (1) 9 个有库存但无映射的 SKU：映射缺口 + 建议处理
  (2) UOM 评审：uom_basis 全 unknown 下，可用的**单位证据来源清单**
  (3) 库存评审：逐 SKU 的仓 + 观测日 + 四态（可直接用/需仓映射/需单位/不可用）
  (4) 409 个 -Cover 共享皮壳料单列（为什么不进本批）
  (5) 入批检查表（四项打勾 + 责任角色）

禁止把 271 并入任何可执行数量；本脚本不产出任何数量合计。

输出（本地）：
  out/sc10/sc10_prep_candidates.csv   271 行（四项评审）
  out/sc10/sc10_prep_unmapped9.csv    9 行（映射缺口）
  out/sc10/sc10_prep_cover409.csv     409 行（Cover 单列）
  out/sc10/sc10_prep.json             聚合 + 证据来源清单 + 检查表模板
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

CLAUDE = Path(__file__).resolve().parents[2]
OUT = CLAUDE / "out" / "sc10"
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
ROWS = OUT / "sc10_catalog_rows.csv"


def main() -> None:
    R = list(csv.DictReader(ROWS.open(encoding="utf-8-sig", newline="")))
    cands = [r for r in R if r["enter_next_mother"] == "yes"]
    blocked = [r for r in R if r["enter_next_mother"].startswith("blocked")]
    covers = [r for r in R if r["cover_like"] == "yes"]

    con = duckdb.connect(str(DB), read_only=True)
    def q(sql, p=None):
        return con.execute(sql, p or []).fetchall()
    hist_wh = sorted({r[0] for r in q("SELECT DISTINCT warehouse_name FROM stock_history")})
    snap_dates = [str(r[0]) for r in q("SELECT DISTINCT snapshot_date FROM stock_history ORDER BY 1")]
    bom_uom = defaultdict(set)
    for it, u in q("SELECT item, uom FROM bom"):
        bom_uom[it].add(u)
    item_attr = {r[0] for r in q("SELECT DISTINCT item FROM item_attr")}
    item_name = {r[0]: r[1] for r in q("SELECT item, item_name FROM item_attr")}
    dis = {r[0] for r in q(
        "SELECT item_code FROM nd_status WHERE CAST(disabled AS VARCHAR) IN ('1','True','true')")}
    con.close()

    # 逐候选：库存仓 + 快照日
    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute(
        "SELECT sku, warehouse, sum(available) FROM stock_latest WHERE available>0 GROUP BY 1,2"
    ).fetchall()
    con.close()
    by_sku = defaultdict(list)
    for s, w, a in rows:
        by_sku[s].append((w, float(a or 0)))
    hist = defaultdict(set)
    con = duckdb.connect(str(DB), read_only=True)
    for s, d in con.execute("SELECT DISTINCT goods_sku, snapshot_date FROM stock_history").fetchall():
        hist[s].add(str(d))
    con.close()

    def review(r):
        sku = r["sku"]
        ics = [x for x in r["item_codes"].split("|") if x]
        whs = by_sku.get(sku, [])
        uoms = set()
        for ic in ics:
            uoms |= bom_uom.get(ic, set())
        m_ok = len(ics) == 1 and ics[0] not in dis and ics[0] in item_attr
        u_ok = bool(uoms) and uoms <= {"个", "件"}
        w_ok = bool(whs) and all(w in hist_wh for w, _ in whs)
        if not whs:
            stock_state = "不可用"
        elif not w_ok:
            stock_state = "需仓映射"
        elif not u_ok:
            stock_state = "需单位"
        else:
            stock_state = "可直接用（条件）"
        return dict(
            sku=sku,
            item_code="|".join(ics),
            stock_available=r["stock_available"],
            warehouses="|".join(f"{w}:{a:.1f}" for w, a in sorted(whs)),
            n_warehouses=len(whs),
            snapshot_dates="|".join(sorted(hist.get(sku, ()))),
            check_mapping=("pass" if m_ok else "FAIL"),
            check_uom=("pass:" + "|".join(sorted(uoms)) if u_ok else
                       ("FAIL(无BOM单位)" if not uoms else "FAIL(需换算:" + "|".join(sorted(uoms)) + ")")),
            check_stock=stock_state,
            # ④ 证据：本地只有 10-20/21/22 三个快照，快照之间没有出入库记录 ->
            # 既不能证明"无未观测出库"，也不该默认通过。
            check_evidence="待补(快照间出入库无记录)",
            final_verdict="待补",
            owner_mapping="主数据" if not m_ok else "",
            owner_uom="主数据/仓储" if not u_ok else "",
            owner_stock="仓储" if stock_state != "可直接用（条件）" else "",
            batch="Cover-单列" if r["cover_like"] == "yes" else "非Cover",
        )

    prep = [review(r) for r in cands]
    with (OUT / "sc10_prep_candidates.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prep[0].keys()))
        w.writeheader()
        w.writerows(prep)

    # ---- (1) 9 个无映射 ------------------------------------------------------
    un_rows = []
    for r in blocked:
        sku = r["sku"]
        whs = by_sku.get(sku, [])
        style = ("纯数字码" if sku.replace("-", "").isdigit() else
                 "含 TEST 字样" if "TEST" in sku.upper() else
                 "通途码形态(TT/TTParts)" if sku.upper().startswith(("TT", "TTPARTS")) else
                 "名称带 -out/-pl 等后缀" if any(x in sku.lower() for x in ("-out", "-pl", "-del")) else
                 "普通命名")
        un_rows.append(dict(
            sku=sku, stock_available=r["stock_available"],
            warehouses="|".join(f"{w}:{a:.1f}" for w, a in sorted(whs)),
            snapshot_dates="|".join(sorted(hist.get(sku, ()))),
            in_item_attr="no", in_sku_item="no",
            gap_type=style,
            suggested_action={
                "纯数字码": "确认是否外部平台码（ASIN/货代号）；若是，需先在主数据建立该码→item_code 的映射",
                "含 TEST 字样": "**建议剔除**（测试数据）；需业务书面确认后再从库存口径移除",
                "通途码形态(TT/TTParts)": "查通途商品档案是否存在同码；存在则补 sku_item 一行",
                "名称带 -out/-pl 等后缀": "确认是否已下架/备用码；下架则单列，不补映射",
                "普通命名": "主数据补 item_code 后重评",
            }.get(style, "主数据补 item_code 后重评"),
            owner="主数据（TEST-1 需业务确认）",
        ))
    with (OUT / "sc10_prep_unmapped9.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(un_rows[0].keys()))
        w.writeheader()
        w.writerows(un_rows)

    # ---- (4) 409 Cover -------------------------------------------------------
    cover_rows = [dict(sku=r["sku"], stock_available=r["stock_available"],
                       category=r["category"], item_codes=r["item_codes"],
                       in_candidate_pool=("yes" if r["enter_next_mother"] == "yes" else "no"),
                       reason="共享皮壳料：库存跨成品共享（代理料），归属与单位未证；"
                              "按 product 分配会重复计，故单列、不进本批")
                  for r in covers]
    with (OUT / "sc10_prep_cover409.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cover_rows[0].keys()))
        w.writeheader()
        w.writerows(cover_rows)

    non_cover = [p for p in prep if p["batch"] == "非Cover"]
    cover_in_pool = [p for p in prep if p["batch"] == "Cover-单列"]

    payload = dict(
        schema_version="sc10_prep/1",
        inputs=dict(sc10_rows=str(ROWS), stock_snapshot_dates=snap_dates,
                    stock_history_warehouses=hist_wh),
        candidates=dict(total=len(prep), non_cover=len(non_cover), cover=len(cover_in_pool)),
        stock_review=dict(Counter(p["check_stock"] for p in prep)),
        stock_review_non_cover=dict(Counter(p["check_stock"] for p in non_cover)),
        mapping=dict(Counter(p["check_mapping"] for p in prep)),
        uom=dict(Counter(p["check_uom"] for p in prep)),
        warehouse_dist=dict(Counter(w for p in prep for w in p["warehouses"].split("|")
                                    for w in [w.rsplit(":", 1)[0]] if w)),
        unmapped9=[dict(sku=u["sku"], stock=u["stock_available"], gap=u["gap_type"],
                        action=u["suggested_action"]) for u in un_rows],
        cover=dict(total=len(covers), with_stock=sum(1 for r in covers if float(r["stock_available"]) > 0),
                   in_candidate_pool=len(cover_in_pool),
                   why_not="共享皮壳料：库存跨成品共享；归属/单位未证；按 SKU 分配会重复计"),
        uom_evidence_sources=[
            dict(source="bom.uom", reachable="本地可得，5,575 行 BOM 头（个/米/件/套）",
                 strength="弱：BOM 基准单位 ≠ 库存单位", provider="主数据"),
            dict(source="EN Delivery Note Item.uom", reachable="本地 dn_split_lines.csv（4,279 行）",
                 strength="中：实际发货单位，可按 item 统计众数", provider="仓储/运营"),
            dict(source="EN Item.stock_uom", reachable="**本地无**，需生产只读查询",
                 strength="强：ERP 库存单位主数据", provider="主数据（ERP 管理员）"),
            dict(source="EN Stock Ledger Entry.uom / 盘点单", reachable="**本地无**，需生产只读查询",
                 strength="强：账面出入库单位", provider="仓储"),
            dict(source="通途商品档案（goods 单位字段）", reachable="**本地无**（tongtool_stock 无单位列）",
                 strength="中：通途侧下单/库存单位", provider="采购/仓管"),
            dict(source="item_attr.qty_per_outer / min_pack / moq", reachable="本地可得",
                 strength="弱：只给装箱关系，不给单位", provider="主数据"),
            dict(source="合同/报价单单位", reachable="**本地无**", strength="中：业务契约单位", provider="运营/采购"),
        ],
        checklist_template=[
            dict(check="① 映射", question="有唯一 item_code 且未停用、且在 item_attr 中？",
                 pass_rule="是", owner="主数据", fail_action="补映射或单列"),
            dict(check="② UOM", question="库存单位有证据（stock_uom 或 DN 单位众数）且为件类？",
                 pass_rule="是", owner="主数据/仓储", fail_action="需换算或拒入批"),
            dict(check="③ 库存", question="仓在快照口径内、有观测日、可用>0？",
                 pass_rule="是", owner="仓储", fail_action="补仓映射/等下次快照"),
            dict(check="④ 证据", question="上述三项 + 快照日前后无未观测出库？",
                 pass_rule="是", owner="仓储/运营", fail_action="标未证，不得入批"),
        ],
        evidence_check=dict(
            rule="④ 证据：需证明快照日前后无未观测出库；本地只有 3 个快照、无台账 -> 一律「待补」",
            verdicts=dict(Counter(p["final_verdict"] for p in prep)),
            note="没有任何一个候选能直接进批"),
        boundaries=[
            "271 个候选**未并入**任何可执行数量；本文件不含任何数量合计。",
            "stock_history.uom_basis 全 unknown：即便「可直接用」也只表示仓/快照/物料单位齐备。",
            "32 个 -Cover 候选单列，不进本批。",
            "9 个无映射的 SKU 必须先补映射，TEST-1 建议剔除（需业务确认）。",
        ],
    )
    (OUT / "sc10_prep.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("candidates", "stock_review", "stock_review_non_cover",
                                              "mapping", "uom", "warehouse_dist", "cover")},
                     ensure_ascii=False, indent=1))
    print(json.dumps(payload["unmapped9"], ensure_ascii=False, indent=1)[:1500])


if __name__ == "__main__":
    main()
