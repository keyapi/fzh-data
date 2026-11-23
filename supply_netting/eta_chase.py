# -*- coding: utf-8 -*-
"""在途 SO 的催证清单（eta_chase）：正缺口键 × 在途 SO 行 → 缺哪张证据、找谁要。

只读生成，不改任何净额/决策包数字。清单的用途是**催证**，不是可抵扣量：
在途没有运单状态与 ETA，就无法进入任何时点覆盖，缺口也不能因此减少。

输入
- ``horizon_windows_keys.csv``：90 / 150 天窗口的逐键缺口（``qty_current`` 为正即正缺口）
- ``so-conditional-supply-2026-10-27-v2/so_supply_tranches.csv``：W1 阶段余额（取 in-transit 行）
- ``w1_supply_facts_v2/supply_facts_raw.jsonl``：逐行 Shipment / Tracking Number / DN / dispatch 证据
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]

OWNER_SHIPMENT = "物流/头程：补 Shipment 与运单号"
OWNER_ETA = "物流/头程：补运单状态与 ETA"
OWNER_RECEIPT = "海外仓：到仓后补收货与上架证明"
OWNER_DEDUP = "采购/通途：核与 PO 是否同批"
OWNER_MASTER = "运营/主数据：补快照与批次归属"


def load_line_evidence(w1_path: str | Path) -> dict[tuple[str, str], dict]:
    """逐 SO 行收集 Shipment / Tracking / DN / dispatch 证据。"""
    evidence: dict[tuple[str, str], dict] = {}

    def bucket(so, line):
        return evidence.setdefault((str(so), str(line)),
                                   dict(shipments=set(), trackings=set(), dns=set(),
                                        dispatch_dates=set()))

    for raw in Path(w1_path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = json.loads(raw).get("payload") or {}
        for link in payload.get("links") or []:
            item = bucket(link.get("so"), link.get("so_line_id"))
            doctype = link.get("target_doctype")
            if doctype == "Shipment":
                item["shipments"].add(str(link.get("target_name")))
            elif doctype == "Tracking Number":
                item["trackings"].add(str(link.get("target_name")))
            elif doctype == "Delivery Note":
                item["dns"].add(str(link.get("target_name")))
        for milestone in payload.get("milestones") or []:
            if milestone.get("node") != "dispatch":
                continue
            item = bucket(milestone.get("so"), milestone.get("so_line_id"))
            actual = milestone.get("actual_at")
            if actual:
                item["dispatch_dates"].add(str(actual)[:10])
            if str(milestone.get("source_record") or "").startswith("Shi"):
                item["shipments"].add(str(milestone.get("source_record")))
    return evidence


def _sorted(values) -> str:
    return ";".join(sorted(str(v) for v in values))


def build_chase_list(keys_csv: str | Path, tranches_csv: str | Path,
                     w1_path: str | Path) -> tuple[pd.DataFrame, dict]:
    keys = pd.read_csv(keys_csv)
    tranches = pd.read_csv(tranches_csv, encoding="utf-8-sig")
    evidence = load_line_evidence(w1_path)

    def window_gaps(days: int, column: str) -> pd.DataFrame:
        subset = keys[(keys["window_days"] == days) & (keys["qty_current"] > 0)][KEY + ["qty_current"]]
        return subset.rename(columns={"qty_current": column})

    gap90 = window_gaps(90, "gap90")
    gap150 = window_gaps(150, "gap150")

    transit = tranches[(tranches["stage"] == "shipped_in_transit")
                       & tranches["branch_warehouse"].notna()].copy()
    transit = transit.rename(columns={"branch_warehouse": "canonical_warehouse",
                                     "uom": "canonical_uom"})
    transit["qty"] = pd.to_numeric(transit["qty"], errors="coerce")

    # 90 与 150 天正缺口键的**并集**：只在 150 天出缺口的键也要催（标 P2）
    merged = (transit.merge(gap90, on=KEY, how="left")
              .merge(gap150, on=KEY, how="left"))
    merged["gap90"] = pd.to_numeric(merged["gap90"], errors="coerce")
    merged["gap150"] = pd.to_numeric(merged["gap150"], errors="coerce")
    merged = merged[(merged["gap90"].fillna(0) > 0) | (merged["gap150"].fillna(0) > 0)].copy()
    merged["gap90"] = merged["gap90"].fillna(0.0)
    merged["gap150"] = merged["gap150"].fillna(0.0)

    # 同一键上全部在途量（用于判断「即使全部到齐能覆盖多少」）
    per_key_transit = merged.groupby(KEY)["qty"].sum().rename("key_transit_total").reset_index()
    merged = merged.merge(per_key_transit, on=KEY, how="left")

    rows = []
    for record in merged.itertuples(index=False):
        line_evidence = evidence.get((str(record.so), str(record.so_line_id)), {})
        shipments = line_evidence.get("shipments") or set()
        trackings = line_evidence.get("trackings") or set()
        dispatch = line_evidence.get("dispatch_dates") or set()
        dns_on_line = line_evidence.get("dns") or set()

        multi_dn = len(dns_on_line) > 1
        has_dn = bool(record.source_record and str(record.source_record).startswith("DN"))
        has_shipment = bool(shipments)
        has_tracking = bool(trackings)
        eta_value = getattr(record, "eta_earliest", None)
        has_eta = (
            eta_value is not None
            and not (isinstance(eta_value, float) and pd.isna(eta_value))
            and str(eta_value) not in ("", "nan")
        )
        included_known = str(getattr(record, "included_in_stock", "unknown")) == "true"
        dedup_proven = "po_in_transit_unproven" not in str(getattr(record, "dedup_status", ""))

        missing = []
        if not has_dn:
            missing.append("DN 未定位")
        elif multi_dn:
            missing.append("DN 数量分配未证（该行有多张 DN）")
        if not has_shipment:
            missing.append("运单（Shipment）")
        if has_shipment and not has_eta:
            missing.append("运单状态与 ETA")
        missing.append("收货与上架证明（未到仓）")
        if not included_known:
            missing.append("是否已入库存快照")
        if not dedup_proven:
            missing.append("是否与通途 PO 同批")

        owners = []
        if not has_shipment:
            owners.append(OWNER_SHIPMENT)
        elif not has_eta:
            owners.append(OWNER_ETA)
        owners.append(OWNER_RECEIPT)
        if not dedup_proven:
            owners.append(OWNER_DEDUP)
        if not included_known:
            owners.append(OWNER_MASTER)

        gap90_value = float(record.gap90 or 0.0)
        gap150_value = float(record.gap150 or 0.0)
        tier = "P1（90 天内缺口）" if gap90_value > 0 else "P2（仅 150 天内缺口）"
        coverage = (float(record.key_transit_total) / gap150_value) if gap150_value else None

        status_parts = ["在途"]
        if dispatch:
            status_parts.append(f"DN 过账 {_sorted(dispatch)}")
        if shipments:
            status_parts.append(f"Shipment {_sorted(shipments)}")
        else:
            status_parts.append("无 Shipment 记录")
        if trackings:
            status_parts.append(f"Tracking {_sorted(trackings)}")

        rows.append({
            "优先级": tier,
            "SKU": record.canonical_sku,
            "仓库": record.canonical_warehouse,
            "单位": record.canonical_uom,
            "缺口90": gap90_value,
            "缺口150": gap150_value,
            "在途量": None if pd.isna(record.qty) else float(record.qty),
            "该键在途合计": float(record.key_transit_total),
            "在途/缺口150": None if coverage is None else round(coverage, 4),
            "SO": record.so,
            "SO 行": record.so_line_id,
            "DN": str(record.source_record or ""),
            "Shipment": _sorted(shipments),
            "Tracking Number": _sorted(trackings),
            "有Shipment": "是" if has_shipment else "否",
            "有Tracking": "是" if has_tracking else "否",
            "有ETA": "是" if has_eta else "否",
            "当前状态": "；".join(status_parts),
            "缺失字段": "；".join(missing),
            "建单日（dispatch actual）": _sorted(dispatch),
            "建议责任角色": "；".join(owners),
            "W1 去重状态": str(getattr(record, "dedup_status", "")),
            "QTY 证据": str(getattr(record, "qty_evidence", "")),
            "是否可抵扣": "否（在途无 ETA，需先取证）",
        })

    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=[
            "优先级", "SKU", "仓库", "单位", "缺口90", "缺口150", "在途量", "该键在途合计",
            "在途/缺口150", "SO", "SO 行", "DN", "Shipment", "Tracking Number", "有Shipment",
            "有Tracking", "有ETA", "当前状态", "缺失字段", "建单日（dispatch actual）",
            "建议责任角色", "W1 去重状态", "QTY 证据", "是否可抵扣"])
        return frame, _summarize(frame, gap90, gap150)
    tier_order = {"P1（90 天内缺口）": 0, "P2（仅 150 天内缺口）": 1}
    frame["_tier"] = frame["优先级"].map(tier_order)
    frame = frame.sort_values(["_tier", "缺口90", "在途量"],
                              ascending=[True, False, False]).drop(columns="_tier")

    summary = _summarize(frame, gap90, gap150)
    return frame, summary


def _summarize(frame: pd.DataFrame, gap90: pd.DataFrame, gap150: pd.DataFrame) -> dict:
    def qty_by_uom(subset):
        values = pd.to_numeric(subset["在途量"], errors="coerce")
        return {str(u): round(float(v), 3) for u, v in
                subset.assign(q=values).groupby("单位")["q"].sum().items()}

    has_ship = frame["有Shipment"] == "是"
    has_eta = frame["有ETA"] == "是"
    local_key = ["SKU", "仓库", "单位"]
    return {
        "gap90_keys": int(len(gap90)),
        "gap150_keys": int(len(gap150)),
        "gap90_keys_with_transit": int(
            frame[frame["缺口90"] > 0][local_key].drop_duplicates().shape[0]),
        "gap150_keys_with_transit": int(frame[local_key].drop_duplicates().shape[0]),
        "chase_rows": int(len(frame)),
        "chase_qty_by_uom": qty_by_uom(frame),
        "chase_rows_p1": int((frame["缺口90"] > 0).sum()),
        "dn_rows": int((frame["DN"].fillna("") != "").sum()),
        "dn_without_shipment_rows": int(((frame["DN"].fillna("") != "") & ~has_ship).sum()),
        "shipment_without_eta_rows": int((has_ship & ~has_eta).sum()),
        "no_shipment_rows": int((~has_ship).sum()),
        "no_any_waybill_rows": int((~has_ship & (frame["Tracking Number"].fillna("") == "")).sum()),
        "qty_dn_without_shipment_by_uom": qty_by_uom(frame[(frame["DN"].fillna("") != "") & ~has_ship]),
        "qty_no_shipment_by_uom": qty_by_uom(frame[~has_ship]),
        "note": "催证清单：在途未取到运单状态与 ETA 前，不能抵扣任何窗口缺口",
    }


def write_readme(path: Path, summary: dict, generated_at: str) -> None:
    text = f"""# 在途 SO 催证清单（eta-chase）

生成时间：{generated_at}

## 这是什么

**催证清单，不是可抵扣量。** 清单列出「90/150 天有缺口的键」上所有在途 SO 行，标出每行缺哪张证据、
该找谁补。在运单状态与 ETA 拿到之前，这些在途量**不计入任何时点覆盖**，缺口也不会因此减少。

## 数字（按 UOM 分列，不跨单位相加）

| 项 | 值 |
|---|---|
| 90 天正缺口键 | {summary['gap90_keys']} |
| 150 天正缺口键 | {summary['gap150_keys']} |
| 其中有在途的键（150 天口径） | {summary['gap150_keys_with_transit']} |
| 催证行数 | {summary['chase_rows']}（P1：{summary['chase_rows_p1']}） |
| 关联在途量 | {json.dumps(summary['chase_qty_by_uom'], ensure_ascii=False)} |
| 有 DN 无 Shipment | {summary['dn_without_shipment_rows']} 行，{json.dumps(summary['qty_dn_without_shipment_by_uom'], ensure_ascii=False)} |
| 有 Shipment 无 ETA | {summary['shipment_without_eta_rows']} 行 |
| 无任何运单 | {summary['no_any_waybill_rows']} 行，{json.dumps(summary['qty_no_shipment_by_uom'], ensure_ascii=False)} |

## 字段说明

- **优先级**：P1 = 该键 90 天内就有缺口（先催）；P2 = 只有 150 天内缺口。
- **在途/缺口150**：该键上全部在途量 ÷ 150 天缺口；>1 只说明「若全部到齐且日期可证」可能覆盖，
  **不代表已经覆盖**。
- **缺失字段**：DN 数量分配 / 运单（Shipment）/ 运单状态与 ETA / 收货与上架 / 是否已入快照 / 是否与通途 PO 同批。
- **建议责任角色**：物流头程补 Shipment 与 ETA；海外仓到仓后补收货上架；采购核 PO 同批；运营补快照归属。
- **是否可抵扣**：本清单全部为「否（在途无 ETA，需先取证）」。

## 边界

- 只读生成：不改 r6 / h180 净额与决策包，不写生产，不下单；
- 在途无 ETA 时按 unknown 处理，不写 0、不按 0 抵扣；
- 数量按 UOM 分开，不跨单位合计。
"""
    path.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="在途 SO 催证清单")
    parser.add_argument("--keys", required=True)
    parser.add_argument("--tranches", required=True)
    parser.add_argument("--w1", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    frame, summary = build_chase_list(args.keys, args.tranches, args.w1)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "eta_chase_list.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    (out_dir / "eta_chase_summary.json").write_text(
        json.dumps(dict(generated_at=generated_at, **summary), ensure_ascii=False, indent=1),
        encoding="utf-8")
    write_readme(out_dir / "README.md", summary, generated_at)
    print(json.dumps(dict(rows=len(frame), **{k: summary[k] for k in
                                              ("gap90_keys", "gap150_keys", "chase_qty_by_uom",
                                               "dn_without_shipment_rows", "shipment_without_eta_rows",
                                               "no_any_waybill_rows")}), ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
