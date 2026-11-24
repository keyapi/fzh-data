# -*- coding: utf-8 -*-
"""从最新订单 parquet 重算需求表与预测（只读，不下单）。

给想自己复现需求/预测的人一条命令：

    uv run python -m supply_copilot.rebuild --orders <orders_unified.parquet> --out <目录>

流程
1. ``build_demand``：订单行 → ``demand_line_disposition.parquet`` + ``sku_coverage.parquet``
   （列与 ``self_fulfilled_demand.forecast`` 的口径对齐）。
2. ``run_forecast``：调用 ``self_fulfilled_demand.forecast.run``，产物落
   ``<out>/forecast/<run_id>``；**不更新 CURRENT**，不碰线上预测。
3. ``rebuild``：上面两步 + ``rebuild_manifest.json``（输入哈希/行数/排除原因/run_id/耗时）。

边界
- 只读本地 parquet；不联网、不写 EN、不做供应净额、不下单。
- 未知不猜：SKU 未映射写 ``unmapped:<sku>``，UOM 缺失写 ``unknown``，仓名未知保留并在
  coverage 里记阻断原因。
- 每个输入行都有去向：进 disposition，或被排除并在统计里按原因计数（入 = 出 + 排除）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

# 与 forecast.DISPOSITION_COLUMNS 对齐；另带 uom 作为证据列（forecast 会忽略）
CORE_COLUMNS = [
    "tongtool_sku",
    "demand_date",
    "quantity",
    "in_main_series",
    "fulfillment_scope",
    "canonical_warehouse",
    "canonical_sku",
    "mapping_status",
]
DISPOSITION_COLUMNS = CORE_COLUMNS + ["uom"]

# 预测引擎校验写死 L90（forecast.validate_frames），标准套件必须包含它
STANDARD_LEADS = (60, 90, 120, 180)

EXCLUSION_ORDER = ("no_sku", "no_date", "fba", "third_party")


def _sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load_alias_config(value: str | Path | dict) -> dict:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _date_str(series: pd.Series) -> pd.Series:
    """任意日期/时间列 → ``YYYY-MM-DD`` 字符串；无法解析写 NaN。"""
    dt = pd.to_datetime(series, errors="coerce")
    out = dt.dt.strftime("%Y-%m-%d")
    return out.where(dt.notna(), None)


def _uom_status(stock_uom: Any, item_found: bool) -> str:
    """与 ``self_fulfilled_demand.canonical._uom_status`` 同一口径。"""
    from self_fulfilled_demand.canonical import PIECE_UOMS

    if not item_found:
        return "missing"
    # EN 不维护 UOM（项目既定）：缺失/空按“个”，不因 UOM 阻断；明确非“个”的才另处理。
    if stock_uom is None or (isinstance(stock_uom, float) and pd.isna(stock_uom)):
        return "known_piece"
    value = str(stock_uom).strip()
    if not value:
        return "known_piece"
    return "known_piece" if value in PIECE_UOMS else "not_piece"


def _block_reasons(
    mapping_status: str,
    uom_status: str,
    warehouse_status: str,
    warehouse_merge_status: str,
    quantity: float,
) -> list[str]:
    reasons: list[str] = []
    if mapping_status == "ambiguous":
        reasons.append("sku_mapping_ambiguous")
    elif mapping_status == "unmapped":
        reasons.append("sku_mapping_missing")
    if uom_status == "missing":
        reasons.append("uom_missing")
    elif uom_status == "not_piece":
        reasons.append("uom_not_piece")
    if warehouse_status == "unknown":
        reasons.append("warehouse_identity_unknown")
    if warehouse_merge_status == "not_merged_no_evidence":
        reasons.append("subwarehouse_identity_unproven")
    if pd.isna(quantity) or float(quantity) <= 0:
        reasons.append("quantity_invalid")
    return reasons


def _build_coverage(disp: pd.DataFrame, input_rows: int, input_qty: float) -> pd.DataFrame:
    """按通途 SKU 汇总覆盖与净额阻断原因；列对齐 forecast 所需。

    forecast.assemble 需要：``tongtool_sku``、``ready_rows``、``blocked_rows``、
    ``block_reasons``、``canonical_sku``、``mapping_status``、``uom``、``uom_status``。
    """
    rows: list[dict[str, Any]] = []
    for sku, grp in disp.groupby("tongtool_sku", dropna=False):
        allowed = grp["netting_allowed"]
        ready = grp[allowed]
        blocked = grp[~allowed]
        uom_status = str(grp["uom_status"].iloc[0])
        uom = str(grp["uom"].iloc[0]) if uom_status == "known_piece" else None
        item_codes = grp["item_codes"].iloc[0]
        rows.append(
            {
                "tongtool_sku": sku,
                "demand_rows": int(len(grp)),
                "demand_qty": float(pd.to_numeric(grp["quantity"], errors="coerce").sum()),
                "mapping_status": grp["mapping_status"].iloc[0],
                "item_codes": None if item_codes is None or pd.isna(item_codes) else str(item_codes),
                "canonical_sku": grp["canonical_sku"].iloc[0],
                "uom_status": uom_status,
                "uom": uom,
                "canonical_warehouses": int(grp["canonical_warehouse"].nunique(dropna=False)),
                "ready_rows": int(len(ready)),
                "ready_qty": float(pd.to_numeric(ready["quantity"], errors="coerce").sum()),
                "blocked_rows": int(len(blocked)),
                "blocked_qty": float(pd.to_numeric(blocked["quantity"], errors="coerce").sum()),
                "block_reasons": ",".join(sorted(set(blocked["block_reason"].astype(str)))),
            }
        )
    out = pd.DataFrame(rows)
    total = pd.DataFrame(
        [
            {
                "tongtool_sku": "__TOTAL__",
                "demand_rows": int(input_rows),
                "demand_qty": float(input_qty),
                "mapping_status": None,
                "item_codes": None,
                "canonical_sku": None,
                "uom_status": None,
                "uom": None,
                "canonical_warehouses": None,
                "ready_rows": int(disp["netting_allowed"].sum()),
                "ready_qty": float(
                    pd.to_numeric(disp.loc[disp["netting_allowed"], "quantity"], errors="coerce").sum()
                ),
                "blocked_rows": int((~disp["netting_allowed"]).sum()),
                "blocked_qty": float(
                    pd.to_numeric(disp.loc[~disp["netting_allowed"], "quantity"], errors="coerce").sum()
                ),
                "block_reasons": ",".join(
                    sorted(set(disp.loc[~disp["netting_allowed"], "block_reason"].astype(str)))
                ),
            }
        ]
    )
    return pd.concat([out, total], ignore_index=True)


def build_demand(
    orders_path: str | Path,
    *,
    sku_map_path: str | Path,
    warehouse_aliases: str | Path | dict,
    uom_cache_path: str | Path,
    out_dir: str | Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    """订单行 → 需求去向表 + SKU 覆盖表；返回统计（入/出/排除/映射率/日期范围）。

    排除规则（互斥、按优先级计数，保证 入 = 出 + 排除）：
    无 SKU → 无日期 → FBA 仓（仓名含 FBA / 解析为 fba）→ 第三方仓（别名表 third_party）。
    未知仓不排除（未证非自发货），保留并把 ``warehouse_identity_unknown`` 写进阻断原因。
    """
    from self_fulfilled_demand.canonical import (
        load_sku_map,
        load_uom_cache,
        resolve_warehouse,
    )

    orders_path = Path(orders_path)
    orders = pd.read_parquet(orders_path)
    required = {"sku_tongtool", "sale_date", "qty"}
    missing = required - set(orders.columns)
    if missing:
        raise ValueError(f"订单 parquet 缺列: {sorted(missing)}")

    source_rows = int(len(orders))

    # as_of：只保留截止日（含）之前的订单，便于复现已过时点的需求
    as_of_filtered_rows = 0
    if as_of:
        raw_dates = pd.to_datetime(orders["sale_date"], errors="coerce")
        cutoff = pd.Timestamp(as_of)
        keep_asof = raw_dates.isna() | (raw_dates <= cutoff)
        as_of_filtered_rows = int((~keep_asof).sum())
        orders = orders[keep_asof]
    orders = orders.reset_index(drop=True)
    sale_dates = pd.to_datetime(orders["sale_date"], errors="coerce")

    input_rows = int(len(orders))
    input_qty = float(pd.to_numeric(orders["qty"], errors="coerce").fillna(0).sum())
    input_date_min = sale_dates.min()
    input_date_max = sale_dates.max()

    sku = orders["sku_tongtool"].astype("string").str.strip()
    sku = sku.where(sku.notna() & sku.ne(""), None)
    demand_date = _date_str(orders["sale_date"])
    qty = pd.to_numeric(orders["qty"], errors="coerce")
    warehouse_raw = (
        orders["warehouse"]
        if "warehouse" in orders.columns
        else pd.Series([None] * len(orders))
    )

    # 仓名解析一次（缓存），用于 FBA/第三方排除与 canonical_warehouse
    alias_cfg = _load_alias_config(warehouse_aliases)
    wh_cache: dict[Any, dict] = {}

    def resolve_wh(name: Any) -> dict:
        key = None if name is None or (isinstance(name, float) and pd.isna(name)) else str(name)
        if key not in wh_cache:
            wh_cache[key] = resolve_warehouse(key, alias_cfg)
        return wh_cache[key]

    wh_resolved = [resolve_wh(w) for w in warehouse_raw]
    wh_status = pd.Series([r["warehouse_status"] for r in wh_resolved], index=orders.index)

    # 互斥排除：优先级 no_sku → no_date → fba → third_party
    no_sku = sku.isna()
    no_date = demand_date.isna()
    is_fba = wh_status.eq("fba")
    is_tp = wh_status.eq("third_party")
    keep = ~no_sku & ~no_date & ~is_fba & ~is_tp

    excluded = {
        "no_sku": int(no_sku.sum()),
        "no_date": int((~no_sku & no_date).sum()),
        "fba": int((~no_sku & ~no_date & is_fba).sum()),
        "third_party": int((~no_sku & ~no_date & ~is_fba & is_tp).sum()),
    }
    output_rows = int(keep.sum())
    if input_rows != output_rows + sum(excluded.values()):  # 防御：守恒断言
        raise AssertionError("需求统计不守恒：入 ≠ 出 + 排除")

    # SKU 映射
    sku_map = load_sku_map(sku_map_path)
    map_index = sku_map.set_index("tongtool_sku")
    item_codes_map = map_index["item_codes"].to_dict()
    mapping_status_map = map_index["mapping_status"].to_dict()

    kept = orders[keep].copy()
    kept_sku = sku[keep]
    kept_wh = [wh_resolved[i] for i in kept.index]

    mapping_status: list[str] = []
    canonical_sku: list[str] = []
    item_code: list[str | None] = []
    item_codes_text: list[str | None] = []
    for s in kept_sku:
        codes = item_codes_map.get(s)
        status = mapping_status_map.get(s, "unmapped")
        if status == "mapped" and isinstance(codes, tuple) and len(codes) == 1:
            mapping_status.append("mapped")
            canonical_sku.append(codes[0])
            item_code.append(codes[0])
            item_codes_text.append(codes[0])
        elif status == "ambiguous" and isinstance(codes, tuple) and len(codes) > 1:
            mapping_status.append("ambiguous")
            canonical_sku.append(f"ambiguous:{s}")
            item_code.append(None)
            item_codes_text.append("|".join(codes))
        else:
            mapping_status.append("unmapped")
            canonical_sku.append(f"unmapped:{s}")
            item_code.append(None)
            item_codes_text.append(None)

    # UOM：按 canonical item_code 查缓存；缺失/未映射 → unknown
    uom_cache = load_uom_cache(uom_cache_path)
    if len(uom_cache):
        uom_lookup = (
            uom_cache[["item_code", "stock_uom"]]
            .drop_duplicates(subset=["item_code"], keep="last")
            .set_index("item_code")["stock_uom"]
            .to_dict()
        )
    else:
        uom_lookup = {}

    uom_values: list[str] = []
    uom_statuses: list[str] = []
    for code, status in zip(item_code, mapping_status):
        found = code is not None and status == "mapped"
        raw_uom = uom_lookup.get(code) if found else None
        st = _uom_status(raw_uom, found)
        uom_statuses.append(st)
        uom_values.append(str(raw_uom).strip() if st == "known_piece" and raw_uom else "个")

    kept_qty = qty[keep].reset_index(drop=True)
    block_reason = [
        ";".join(
            _block_reasons(
                mstat,
                ustat,
                wh["warehouse_status"],
                wh["warehouse_merge_status"],
                q,
            )
        )
        for mstat, ustat, wh, q in zip(mapping_status, uom_statuses, kept_wh, kept_qty)
    ]

    disp = pd.DataFrame(
        {
            "tongtool_sku": kept_sku.astype(str).reset_index(drop=True),
            "demand_date": demand_date[keep].reset_index(drop=True),
            "quantity": kept_qty,
            "in_main_series": True,
            "fulfillment_scope": "self_fulfilled_candidate",
            "canonical_warehouse": [wh["canonical_warehouse"] for wh in kept_wh],
            "canonical_sku": canonical_sku,
            "mapping_status": mapping_status,
            "uom": uom_values,
            # 以下为证据列（不属于 forecast 必需 8 列）
            "uom_status": uom_statuses,
            "item_codes": item_codes_text,
            "warehouse_status": [wh["warehouse_status"] for wh in kept_wh],
            "warehouse_merge_status": [wh["warehouse_merge_status"] for wh in kept_wh],
            "block_reason": block_reason,
            "netting_allowed": [r == "" for r in block_reason],
        }
    )

    coverage = _build_coverage(disp, input_rows=len(disp), input_qty=float(
        pd.to_numeric(disp["quantity"], errors="coerce").fillna(0).sum()
    ))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    disp_path = out / "demand_line_disposition.parquet"
    cov_path = out / "sku_coverage.parquet"
    disp.to_parquet(disp_path, index=False, compression="zstd")
    coverage.to_parquet(cov_path, index=False, compression="zstd")

    mapped_rows = int((disp["mapping_status"] == "mapped").sum())
    out_dates = disp["demand_date"]
    return {
        "source_rows": source_rows,
        "as_of": as_of,
        "as_of_filtered_rows": as_of_filtered_rows,
        "input_rows": input_rows,
        "input_qty": input_qty,
        "input_date_min": None if pd.isna(input_date_min) else str(input_date_min.date()),
        "input_date_max": None if pd.isna(input_date_max) else str(input_date_max.date()),
        "output_rows": output_rows,
        "output_date_min": None if out_dates.empty or pd.isna(out_dates.min()) else str(out_dates.min()),
        "output_date_max": None if out_dates.empty or pd.isna(out_dates.max()) else str(out_dates.max()),
        "excluded_rows": int(sum(excluded.values())),
        "excluded": excluded,
        "mapping": {
            "mapped_rows": mapped_rows,
            "ambiguous_rows": int((disp["mapping_status"] == "ambiguous").sum()),
            "unmapped_rows": int((disp["mapping_status"] == "unmapped").sum()),
            "mapping_rate": round(mapped_rows / output_rows, 4) if output_rows else 0.0,
        },
        "unique_skus": int(disp["tongtool_sku"].nunique()),
        "demand_units": float(pd.to_numeric(disp["quantity"], errors="coerce").fillna(0).sum()),
        "paths": {"disposition": str(disp_path), "coverage": str(cov_path)},
    }


def run_forecast(
    out_dir: str | Path,
    *,
    decision_date: str | date,
    lead_days: int = 90,
    no_statsforecast: bool = False,
    model_policy: str = "autoets",
    model_map_path: str | None = None,
) -> dict[str, Any]:
    """在 ``<out>/demand_line_disposition.parquet`` 上跑一次预测。

    产物落 ``<out>/forecast/<run_id>``，**不更新 CURRENT**。``lead_days`` 会并入
    标准窗口（60/90/120/180，引擎校验固定看 L90）；``no_statsforecast`` 时强制
    MA3/naive 回退（离线/对照）。
    """
    from self_fulfilled_demand import forecast

    out = Path(out_dir)
    disposition = out / "demand_line_disposition.parquet"
    coverage = out / "sku_coverage.parquet"
    if not disposition.exists():
        raise FileNotFoundError(f"缺少需求表，请先 build_demand：{disposition}")
    if not coverage.exists():
        raise FileNotFoundError(f"缺少 SKU 覆盖表，请先 build_demand：{coverage}")

    dd = decision_date if isinstance(decision_date, date) else date.fromisoformat(str(decision_date))
    leads = tuple(sorted(set(STANDARD_LEADS) | {int(lead_days)}))
    cfg = forecast.ForecastConfig(decision_date=dd, leads=leads,
                                  model_policy=model_policy,
                                  model_map_path=model_map_path)
    backend = None if no_statsforecast else forecast.load_backend()
    run_dir = forecast.run(
        disposition_path=disposition,
        coverage_path=coverage,
        out_root=out / "forecast",
        cfg=cfg,
        backend=backend,
        update_current=False,
    )
    return {
        "run_id": Path(run_dir).name,
        "run_dir": str(run_dir),
        "decision_date": dd.isoformat(),
        "leads": list(leads),
        "no_statsforecast": bool(no_statsforecast),
    }


def rebuild(
    orders_path: str | Path,
    out_dir: str | Path,
    *,
    sku_map_path: str | Path,
    warehouse_aliases: str | Path | dict,
    uom_cache_path: str | Path,
    as_of: str | None = None,
    decision_date: str | date | None = None,
    lead_days: int = 90,
    no_statsforecast: bool = False,
    model_policy: str = "autoets",
    model_map_path: str | None = None,
) -> dict[str, Any]:
    """build_demand + run_forecast + ``rebuild_manifest.json``；返回 manifest。"""
    t0 = time.perf_counter()
    stats = build_demand(
        orders_path,
        sku_map_path=sku_map_path,
        warehouse_aliases=warehouse_aliases,
        uom_cache_path=uom_cache_path,
        out_dir=out_dir,
        as_of=as_of,
    )
    if decision_date is None:
        # 默认用数据截止日；若为空则拒绝，避免拿错时点预测
        decision_date = stats["output_date_max"]
    if not decision_date:
        raise ValueError("无法确定决策日：需求表没有有效日期，请显式传 decision_date")

    forecast_info = run_forecast(
        out_dir,
        decision_date=decision_date,
        lead_days=lead_days,
        no_statsforecast=no_statsforecast,
        model_policy=model_policy,
        model_map_path=model_map_path,
    )

    manifest = {
        "schema": "demand-rebuild-v1",
        "generated_at": _now_iso(),
        "orders": {
            "path": str(orders_path),
            "sha256": _sha256(orders_path),
            "rows": stats["source_rows"],
        },
        "as_of": as_of,
        "cutoff_date": stats["output_date_max"],
        "counts": {
            "source_rows": stats["source_rows"],
            "as_of_filtered_rows": stats["as_of_filtered_rows"],
            "input_rows": stats["input_rows"],
            "output_rows": stats["output_rows"],
            "excluded_rows": stats["excluded_rows"],
            "unique_skus": stats["unique_skus"],
            "demand_units": stats["demand_units"],
        },
        "excluded": stats["excluded"],
        "mapping": stats["mapping"],
        "date_range": {
            "input": [stats["input_date_min"], stats["input_date_max"]],
            "output": [stats["output_date_min"], stats["output_date_max"]],
        },
        "forecast": forecast_info,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
    manifest_path = Path(out_dir) / "rebuild_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从最新订单 parquet 重算需求表 + 预测（只读）")
    ap.add_argument("--orders", required=True, help="orders_unified parquet 路径")
    ap.add_argument("--out", required=True, help="输出目录（不要放仓库里）")
    ap.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    ap.add_argument(
        "--uom-cache",
        default="D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet",
    )
    ap.add_argument(
        "--warehouse-aliases",
        default=str(Path(__file__).resolve().parent.parent / "self_fulfilled_demand" / "warehouse_aliases.json"),
    )
    ap.add_argument("--as-of", default=None, help="只保留该日期（含）之前的订单，YYYY-MM-DD")
    ap.add_argument("--decision-date", default=None, help="预测决策日；默认用数据截止日")
    ap.add_argument("--lead-days", type=int, default=90)
    ap.add_argument("--no-statsforecast", action="store_true", help="强制 MA3/naive（离线/对照）")
    ap.add_argument("--build-only", action="store_true", help="只建需求表，不跑预测")
    args = ap.parse_args(argv)

    if args.build_only:
        stats = build_demand(
            args.orders,
            sku_map_path=args.sku_map,
            warehouse_aliases=args.warehouse_aliases,
            uom_cache_path=args.uom_cache,
            out_dir=args.out,
            as_of=args.as_of,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    manifest = rebuild(
        args.orders,
        args.out,
        sku_map_path=args.sku_map,
        warehouse_aliases=args.warehouse_aliases,
        uom_cache_path=args.uom_cache,
        as_of=args.as_of,
        decision_date=args.decision_date,
        lead_days=args.lead_days,
        no_statsforecast=args.no_statsforecast,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
