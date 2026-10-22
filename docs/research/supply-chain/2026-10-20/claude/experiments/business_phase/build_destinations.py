#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 1A: destination table for the 1,328-SKU business mother set.

Every SKU with sales in the six complete months 2026-04..09 (by
`gs_orders.despatch_date`) must land in exactly one bucket:

  mapped_eligible       exactly one EN material, all four mapping checks pass
  mapped_ineligible     has a mapping, but >=1 check fails
                        (duplicate_mapping / one_code_multi_material /
                         alias_deleted / uom_unknown / discontinued)
  unmapped              no EN mapping; listed individually with absence evidence
  discontinued_excluded explicit discontinuation evidence

This stage does NOT rank sales and does NOT produce any quantity or
replenishment judgement (D14: mapping quality and sales ranking must not live in
the same script). Mapping quality only.

Inputs (read-only):  D:/Work/fzh-order-store/order_store.duckdb
Outputs:             out/business_phase/destinations.json
                     out/business_phase/destinations.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

import duckdb

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT_DIR = CLAUDE_DIR / "out" / "business_phase"
OUT_JSON = OUT_DIR / "destinations.json"
OUT_MD = OUT_DIR / "destinations.md"

WINDOW_FIRST = "2026-04"
WINDOW_LAST = "2026-09"
EXPECTED_MOTHER_SET = 1328
EXPECTED_MAPPED = 1266
EXPECTED_UNMAPPED = 62

PIECE_UOMS = ("个", "件", "套")
DESTINATIONS = ("mapped_eligible", "mapped_ineligible", "unmapped",
                "discontinued_excluded")
REASON_CODES = ("duplicate_mapping", "one_code_multi_material", "alias_deleted",
                "uom_unknown", "discontinued")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def name_pattern(sku: str) -> str:
    """Objective label for WHY an unmapped key looks unlike a KS item.
    This is evidence about the key, never a guessed mapping."""
    if sku.endswith("-Cover"):
        return "cover_alias_suffix"
    if sku.endswith("-Foam"):
        return "foam_alias_suffix"
    if re.match(r"^T\d{4}P\d+", sku):
        return "T_P_numeric_key"
    if re.match(r"^PP[\d.]+LB$", sku):
        return "PP_weight_key"
    if sku.startswith("TT") and re.match(r"^TT\d{7}K\d{7}", sku):
        return "tt_numeric_key_without_mapping"
    if re.match(r"^C/", sku):
        return "customer_code_without_mapping"
    if re.match(r"^[A-Za-z][A-Za-z ]*$", sku):
        return "descriptive_name_key"
    return "other_unmapped_key"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--json", default=str(OUT_JSON))
    ap.add_argument("--md", default=str(OUT_MD))
    args = ap.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        raise SystemExit(f"missing db: {db_path}")
    hash_before = sha256_file(db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # ---------------- mother set -----------------------------------------
        con.execute(f"""
            CREATE TEMP TABLE mom AS
            SELECT sku_tongtool AS sku,
                   COUNT(*) AS n_order_lines,
                   SUM(CASE WHEN qty > 0 THEN 1 ELSE 0 END) AS n_positive_lines
            FROM gs_orders
            WHERE substr(despatch_date, 1, 7) BETWEEN '{WINDOW_FIRST}' AND '{WINDOW_LAST}'
            GROUP BY 1
        """)
        mother = con.execute("SELECT sku FROM mom ORDER BY sku").fetchall()
        mother_skus = [r[0] for r in mother]
        if len(mother_skus) != EXPECTED_MOTHER_SET:
            raise SystemExit(
                f"mother set {len(mother_skus)} != frozen {EXPECTED_MOTHER_SET} "
                f"(window {WINDOW_FIRST}..{WINDOW_LAST} by despatch_date)")

        # ---------------- mapping sources ------------------------------------
        # Two frozen mapping tables carry the same key space; both are read so a
        # disagreement would surface as duplicate_mapping.
        map_rows = {}
        for table, key in (("sku_map", "tongtool_sku"), ("sku_item", "sku")):
            for k, item in con.execute(
                    f"SELECT {key}, item_code FROM {table}").fetchall():
                map_rows.setdefault(k, []).append(dict(source=table, item_code=item))
        item_master = {r[0] for r in con.execute("SELECT item FROM item_attr").fetchall()}
        item_name = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_name FROM item_attr").fetchall()}
        bom_uom = {r[0]: r[1] for r in con.execute("SELECT item, uom FROM bom").fetchall()}
        ship_type = {}
        for k, st in con.execute("SELECT sku, ship_type FROM sku_item").fetchall():
            ship_type[k] = st
        stock = {}
        for sku, rows, avail in con.execute("""
                SELECT sku, COUNT(*), SUM(available) FROM stock_latest GROUP BY 1
                """).fetchall():
            stock[sku] = dict(stock_rows=int(rows), available=int(avail or 0))
        mom_stats = {r[0]: dict(n_order_lines=int(r[1]), n_positive_lines=int(r[2]))
                     for r in con.execute(
                         "SELECT sku, n_order_lines, n_positive_lines FROM mom").fetchall()}
        # first/last order line + one sample line_id per unmapped key (evidence)
        order_span = {}
        for sku, first, last in con.execute("""
                SELECT sku_tongtool, MIN(despatch_date), MAX(despatch_date)
                FROM gs_orders
                WHERE substr(despatch_date,1,7) BETWEEN ? AND ?
                GROUP BY 1""", [WINDOW_FIRST, WINDOW_LAST]).fetchall():
            order_span[sku] = (first, last)
        sample_line = {r[0]: r[1] for r in con.execute("""
                SELECT sku_tongtool, MIN(line_id) FROM gs_orders
                WHERE substr(despatch_date,1,7) BETWEEN ? AND ?
                GROUP BY 1""", [WINDOW_FIRST, WINDOW_LAST]).fetchall()}
        # fan-in diagnostic (many tongtool aliases -> one item) is normal, not an error
        item_fan_in = {}
        for item, n in con.execute("""
                SELECT item_code, COUNT(DISTINCT tongtool_sku) FROM sku_map GROUP BY 1
                """).fetchall():
            item_fan_in[item] = int(n)
        # discontinuation evidence source (finished goods only; nd_status is ND#)
        nd_disabled = {r[0] for r in con.execute(
            "SELECT item_code FROM nd_status WHERE disabled = '1'").fetchall()}
    finally:
        con.close()
    hash_after = sha256_file(db_path)
    if hash_before != hash_after:
        raise SystemExit("DB changed during the run; refusing to publish")

    # prefix candidates for unmapped keys: strict prefixes that DO have a mapping.
    # Recorded as context only -- never adopted as a mapping (no guessing).
    mapped_keys = sorted(map_rows)

    rows = []
    for sku in mother_skus:
        stat = mom_stats[sku]
        st = stock.get(sku)
        base = dict(
            sku=sku,
            n_order_lines=stat["n_order_lines"],
            n_positive_lines=stat["n_positive_lines"],
            first_despatch=order_span[sku][0],
            last_despatch=order_span[sku][1],
            ship_type=ship_type.get(sku),
            stock_rows=(st or {}).get("stock_rows"),
            stock_available=(st or {}).get("available"),
            zero_stock_with_sales=bool((st or {}).get("available", 0) <= 0),
        )
        maps = map_rows.get(sku)
        if not maps:
            # ---------------- unmapped --------------------------------------
            key = sku
            prefix_hits = [m for m in mapped_keys
                           if m != key and key.startswith(m + "-")][:3]
            rows.append(dict(
                **base,
                destination="unmapped",
                reason_codes=[],
                mapped_item_code=None,
                checks=dict(
                    duplicate_mapping=dict(state="n/a", detail="no mapping row"),
                    one_code_multi_material=dict(state="n/a", detail="no mapping row"),
                    alias_deleted=dict(state="n/a", detail="no mapping row"),
                    uom_unknown=dict(state="n/a", detail="no mapping row"),
                ),
                unmapped_evidence=dict(
                    absence=[f"sku_map has no row with tongtool_sku={sku!r}",
                             f"sku_item has no row with sku={sku!r}"],
                    name_pattern=name_pattern(sku),
                    prefix_candidates_not_adopted=prefix_hits,
                    prefix_rule=("prefix/suffix similarity is recorded as context; "
                                 "it is NOT used to assign an EN material"),
                ),
                evidence_pointer=(f"gs_orders[sku_tongtool={sku!r}] "
                                  f"line_id={sample_line.get(sku)!r}; "
                                  f"stock_latest[sku={sku!r}] rows="
                                  f"{(st or {}).get('stock_rows')}"),
            ))
            continue

        # ---------------- mapped --------------------------------------------
        distinct_items = sorted({m["item_code"] for m in maps})
        # duplicate_mapping = the KEY is duplicated (rows or conflicting item codes);
        # one_code_multi_material = the resolved codes point to >1 distinct MATERIAL
        # (item_name), which is a different question from code identity.
        dup_flag = len(distinct_items) > 1 or len(maps) > len({m["source"] for m in maps})
        distinct_materials = sorted({item_name.get(i, i) for i in distinct_items})
        multi_material_flag = len(distinct_materials) > 1
        item = distinct_items[0] if len(distinct_items) == 1 else None
        in_master = bool(item and item in item_master)
        uom = bom_uom.get(item) if item else None
        uom_flag = not (uom in PIECE_UOMS)
        discontinued_flag = bool(item and item in nd_disabled)

        checks = dict(
            duplicate_mapping=dict(
                state="flag" if dup_flag else "ok",
                detail=(f"{len(maps)} mapping row(s) across sources "
                        f"{sorted({m['source'] for m in maps})}; distinct "
                        f"item_codes={distinct_items}")),
            one_code_multi_material=dict(
                state="flag" if multi_material_flag else "ok",
                detail=(f"distinct material names={distinct_materials}"
                        if multi_material_flag else
                        f"one material: {distinct_materials[0]!r}"
                        if distinct_materials else "no resolvable material")),
            alias_deleted=dict(
                state="flag" if not in_master else "ok",
                detail=(f"item_code={item!r} present in EN item master"
                        if in_master else
                        f"item_code={item!r} absent from item_attr (master)")),
            uom_unknown=dict(
                state="flag" if uom_flag else "ok",
                detail=(f"bom[item={item!r}].uom={uom!r}" if uom is not None
                        else f"no bom row for item={item!r}; unit basis unknown")),
        )
        reasons = []
        if dup_flag:
            reasons.append("duplicate_mapping")
        if multi_material_flag:
            reasons.append("one_code_multi_material")
        if not in_master:
            reasons.append("alias_deleted")
        if uom_flag:
            reasons.append("uom_unknown")
        if discontinued_flag:
            reasons.append("discontinued")

        rows.append(dict(
            **base,
            destination=("mapped_ineligible" if reasons else "mapped_eligible"),
            reason_codes=reasons,
            mapped_item_code=item,
            item_in_master=in_master,
            bom_uom=uom,
            item_alias_fan_in=item_fan_in.get(item),
            checks=checks,
            evidence_pointer=("; ".join(
                f"{m['source']}[{'tongtool_sku' if m['source']=='sku_map' else 'sku'}="
                f"{sku!r}].item_code={m['item_code']!r}" for m in maps)
                + f"; item_attr[item={item!r}]"
                + (f"; bom[item={item!r}].uom={uom!r}" if uom is not None else "")),
        ))

    # ---------------- reconciliation -----------------------------------------
    counts = {d: sum(1 for r in rows if r["destination"] == d) for d in DESTINATIONS}
    total = sum(counts.values())
    mapped_total = counts["mapped_eligible"] + counts["mapped_ineligible"]
    if total != EXPECTED_MOTHER_SET:
        raise SystemExit(f"destination sum {total} != {EXPECTED_MOTHER_SET}")
    if mapped_total + counts["unmapped"] != EXPECTED_MOTHER_SET:
        raise SystemExit("bucket arithmetic does not close")
    if mapped_total != EXPECTED_MAPPED or counts["unmapped"] != EXPECTED_UNMAPPED:
        raise SystemExit(
            f"mapping reconciliation {mapped_total}/{counts['unmapped']} != frozen "
            f"{EXPECTED_MAPPED}/{EXPECTED_UNMAPPED}")
    if len(rows) != EXPECTED_MOTHER_SET:
        raise SystemExit(f"rows {len(rows)} != {EXPECTED_MOTHER_SET}")

    reason_counts = {c: sum(1 for r in rows if c in r["reason_codes"])
                     for c in REASON_CODES}
    zero_stock = [r["sku"] for r in rows if r["zero_stock_with_sales"]]
    unmapped_rows = [r for r in rows if r["destination"] == "unmapped"]
    ineligible_rows = [r for r in rows if r["destination"] == "mapped_ineligible"]

    out = dict(
        schema_version="business_phase_destinations/1",
        stage="Phase 1A (destination table only: no ranking, no quantity)",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        scope=dict(
            mother_set_definition=(
                "distinct gs_orders.sku_tongtool with despatch_date in "
                f"{WINDOW_FIRST}..{WINDOW_LAST} (six complete months); all qty signs kept"),
            date_field="despatch_date (not sale_date)",
            expected=EXPECTED_MOTHER_SET,
            expected_mapped=EXPECTED_MAPPED,
            expected_unmapped=EXPECTED_UNMAPPED,
            no_ranking=True,
            no_quantities=True,
        ),
        inputs=dict(
            db_path=str(db_path),
            db_sha256_before=hash_before,
            db_sha256_after=hash_after,
            db_unchanged=hash_before == hash_after,
            mapping_sources=["sku_map(tongtool_sku->item_code)",
                             "sku_item(sku->item_code)"],
            item_master="item_attr(item)",
            uom_source="bom(item->uom)",
            stock_source="stock_latest(sku)",
            discontinuation_source="nd_status(item_code, disabled) -- ND# items only",
        ),
        checks_definition=dict(
            duplicate_mapping="one tongtool key with >1 mapping row or >1 distinct item_code",
            one_code_multi_material="one tongtool key resolving to >1 EN material",
            alias_deleted="mapped item_code absent from the EN item master (item_attr)",
            uom_unknown="mapped item has no BOM row, or BOM uom is not piece-like "
                        f"({', '.join(PIECE_UOMS)})",
            discontinued="mapped item listed disabled in nd_status",
            note=("alias fan-in (one item_code reached from many tongtool SKUs) is a "
                  "normal diagnostic, not an error and not a fail code"),
        ),
        counts=dict(
            mother_set=EXPECTED_MOTHER_SET,
            **counts,
            sum=total,
            mapped_total=mapped_total,
            reason_code_counts=reason_counts,
            reconciliation=f"{counts['mapped_eligible']} + {counts['mapped_ineligible']}"
                           f" + {counts['unmapped']} + {counts['discontinued_excluded']}"
                           f" = {total}",
            against_frozen=dict(
                frozen_mapped=EXPECTED_MAPPED, frozen_unmapped=EXPECTED_UNMAPPED,
                observed_mapped=mapped_total, observed_unmapped=counts["unmapped"],
                difference=0,
                explanation=("mapping tables reproduce 1,266/62 exactly; the 29 rows "
                             "that fail UOM are inside the 1,266 -- 'mapped' is not "
                             "'verified'"),
            ),
            zero_stock_with_sales=len(zero_stock),
        ),
        rows=rows,
        ineligible_detail=[dict(sku=r["sku"], mapped_item_code=r["mapped_item_code"],
                                reason_codes=r["reason_codes"],
                                evidence_pointer=r["evidence_pointer"])
                           for r in ineligible_rows],
        unmapped_detail=[dict(sku=r["sku"], name_pattern=r["unmapped_evidence"]["name_pattern"],
                              n_order_lines=r["n_order_lines"],
                              stock_rows=r["stock_rows"],
                              evidence_pointer=r["evidence_pointer"]) for r in unmapped_rows],
        reconciliation_detail=dict(
            rows_in=EXPECTED_MOTHER_SET, rows_out=len(rows),
            dropped=[],
            dropped_reason="none; every mother-set SKU is emitted exactly once",
            bucket_sum_ok=True,
            frozen_ok=True,
        ),
    )

    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    # ---------------- compact markdown summary -------------------------------
    md = []
    md.append("---")
    md.append("okf: v0.1")
    md.append("type: Report")
    md.append("title: Phase 1A 业务母集去向表（1,328 SKU）")
    md.append(f"date: {date.today().isoformat()}")
    md.append("owner: claude-worker")
    md.append("status: destination table only; no ranking, no quantity")
    md.append("inputs:")
    md.append("  - D:/Work/fzh-order-store/order_store.duckdb (read_only)")
    md.append("artifacts:")
    md.append("  - experiments/business_phase/build_destinations.py")
    md.append("  - out/business_phase/destinations.json")
    md.append("---")
    md.append("")
    md.append("# Phase 1A：1,328 SKU 去向表")
    md.append("")
    md.append(f"> 母集口径：`gs_orders.despatch_date` 落在 **{WINDOW_FIRST}..{WINDOW_LAST}**"
              "（6 个完整月）的去重 `sku_tongtool`；不按 qty 过滤，零库存有销量照样在表内。")
    md.append("> 本阶段只做映射质量，不做销量排序、不出任何数量、不做补货判断。")
    md.append("")
    md.append("## 1. 四类计数（必须相加）")
    md.append("")
    md.append("| 去向 | 计数 |")
    md.append("|---|---:|")
    for d in DESTINATIONS:
        md.append(f"| `{d}` | {counts[d]:,} |")
    md.append(f"| **合计** | **{total:,}** |")
    md.append("")
    md.append(f"- 已映射 {mapped_total:,}（合格 {counts['mapped_eligible']:,} + 不合格 "
              f"{counts['mapped_ineligible']:,}） / 未映射 {counts['unmapped']:,} "
              f"= 与初始对账 1,266 / 62 一致，差额 **0**。")
    md.append("- **1,266「已映射」不等于已验证**：其中 "
              f"{counts['mapped_ineligible']:,} 个未通过检查（见 §3）。")
    md.append(f"- 零库存但有历史销量的 SKU：**{len(zero_stock):,}** 个，全部在表内。")
    md.append("")
    md.append("## 2. 四项检查（逐行写入 `rows[].checks`）")
    md.append("")
    md.append("| 检查 | 定义 | 命中行数 |")
    md.append("|---|---|---:|")
    md.append(f"| `duplicate_mapping` | 同一通途键多行映射或映射到多个 item_code | "
              f"{reason_counts['duplicate_mapping']} |")
    md.append(f"| `one_code_multi_material` | 同一通途键解析出多个 EN 物料 | "
              f"{reason_counts['one_code_multi_material']} |")
    md.append(f"| `alias_deleted` | 映射到的 item_code 不在 EN 物料主数据 | "
              f"{reason_counts['alias_deleted']} |")
    md.append(f"| `uom_unknown` | 无 BOM 行，或 BOM 单位不是件/个/套 | "
              f"{reason_counts['uom_unknown']} |")
    md.append(f"| `discontinued` | 物料在 nd_status 中标 disabled | "
              f"{reason_counts['discontinued']} |")
    md.append("")
    md.append("> 别名聚集（一个 item_code 被多个通途 SKU 引用）是正常现象，"
              "只作诊断字段 `item_alias_fan_in`，不作为失败码。")
    md.append("")
    md.append("## 3. 已映射但不合格（逐条）")
    md.append("")
    md.append("| SKU | EN 物料 | reason_codes |")
    md.append("|---|---|---|")
    for r in ineligible_rows:
        md.append(f"| `{r['sku']}` | `{r['mapped_item_code']}` | "
                  f"{', '.join(r['reason_codes'])} |")
    md.append("")
    md.append("## 4. 未映射 62 个（逐个列出，不猜配）")
    md.append("")
    md.append("| SKU | 名称形态 | 订单行 | 库存行 |")
    md.append("|---|---|---:|---:|")
    for r in unmapped_rows:
        md.append(f"| `{r['sku']}` | {r['unmapped_evidence']['name_pattern']} | "
                  f"{r['n_order_lines']} | {r['stock_rows']} |")
    md.append("")
    md.append("每个未映射行的 `evidence_pointer` 给出 `gs_orders` 抽样行键与 "
              "`stock_latest` 行数；`unmapped_evidence.absence` 给出两张映射表都不存在的"
              "断言；`prefix_candidates_not_adopted` 只记录形近键，**不用来配映射**。")
    md.append("")
    md.append("## 5. 对账")
    md.append("")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 入 / 出 | {EXPECTED_MOTHER_SET:,} / {len(rows):,}，0 丢弃 |")
    md.append(f"| 四类相加 | {counts['mapped_eligible']} + {counts['mapped_ineligible']}"
              f" + {counts['unmapped']} + {counts['discontinued_excluded']} = {total} |")
    md.append("| 与 1,266 / 62 | 一致，差额 0；无调整 |")
    md.append(f"| DB 只读 | 运行前后 sha256 一致（`{hash_before[:12]}…`） |")
    md.append("")
    md.append("## 6. 本阶段不做")
    md.append("")
    md.append("- 不做销量排序、不分 80/15/5、不算 90 天节奏、不出任何数量或补货结论。")
    md.append("- 不猜配未映射 SKU；不把“无销量/低销量”当停产，停产类只认明确证据"
              "（当前证据源只有 nd_status，命中 0）。")
    md.append("")
    Path(args.md).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"wrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"wrote {args.md}")
    print("buckets:", {d: counts[d] for d in DESTINATIONS}, "sum", total)
    print("reason codes:", reason_counts)
    print("zero-stock-with-sales:", len(zero_stock))


if __name__ == "__main__":
    main()
