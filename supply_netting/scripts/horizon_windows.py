# -*- coding: utf-8 -*-
"""从已完成的净额 run 切出 30/60/90/120/150/180 天多窗口表（不重跑、不改包）。

口径
- 窗口按**真实桶边界**取：选「桶结束时间 ≥ as_of + N 天」的第一个桶；
  实际覆盖天数可能比 N 多最多 7 天，用 ``bucket_end`` / ``actual_days`` 标明，绝不插值。
- 每个窗口都是**从 as_of 起的累计**；窗口之间不相加（30 天行不是 60 天行的子集可加项）。
- 所有数量按 UOM 分组；多 UOM 时不输出无单位总量。
- 180 天窗口标 ``usage=scenario_only``：只作产能/春节排期情景，不是采购量。

用法
```bash
uv run python -m supply_netting.scripts.horizon_windows \
  --run D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-26-r6 \
  --demand D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_netting.parquet \
  --out D:/Work/fzh-order-store/en-demand-v1/supply-netting/horizon-windows-2026-10-29
```
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

TARGETS = (30, 60, 90, 120, 150, 180)
SCENARIO_ONLY = {180}
KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def _parse(value) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def load_run(run_dir: str | Path) -> tuple[pd.DataFrame, list[dict], datetime, dict]:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
    netting = pd.read_parquet(run_dir / "supply_netting.parquet")
    netting = netting[netting["scenario"] == "expected"].copy()
    for column in ("period_demand", "receipts", "unserved", "gap", "opening",
                   "conditional_receipts"):
        if column in netting.columns:
            netting[column] = pd.to_numeric(netting[column], errors="coerce")
    as_of = _parse(manifest["as_of"])
    buckets = [dict(bucket_id=b["bucket_id"], start=_parse(b["start"]), end=_parse(b["end"]))
               for b in manifest["buckets"]]
    return netting, buckets, as_of, manifest


def buffers_from_history(history: pd.DataFrame) -> pd.DataFrame:
    """与决策包一致的参考缓冲：z95 × 日需求 σ × √14，按 UOM 分组计算 ABC 无关。

    这里只需要 σ，不需要 ABC 分档；UOM 只作为分组键，不跨组求和。
    """
    if history.empty:
        return pd.DataFrame(columns=KEY + ["buffer_reference"])
    hist = history.copy()
    hist["demand_date"] = pd.to_datetime(hist["demand_date"])
    cutoff = hist["demand_date"].max() - pd.Timedelta(days=90)
    hist = hist[hist["demand_date"] >= cutoff]
    return hist.groupby(KEY)["quantity"].std().reset_index(name="sigma_daily")


def _z95() -> float:
    # 标准正态 95% 分位（与 pack._z 同一近似函数）
    from ..pack import _z
    return _z(0.95)


def build_windows(netting: pd.DataFrame, buckets: list[dict], as_of: datetime,
                  history: pd.DataFrame, targets=TARGETS) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not len(netting):
        return pd.DataFrame(), pd.DataFrame()
    ordered = sorted(buckets, key=lambda b: b["end"])
    order = {b["bucket_id"]: idx for idx, b in enumerate(ordered)}
    netting = netting.assign(_order=netting["bucket_id"].map(order))

    sigma = buffers_from_history(history)
    if len(sigma):
        sigma["buffer_reference"] = sigma["sigma_daily"] * _z95() * math.sqrt(14)
        sigma = sigma[KEY + ["buffer_reference"]]
    opening = (netting.sort_values("_order").groupby(KEY, as_index=False)
               .agg(opening=("opening", "first")))

    summary_rows, key_rows = [], []
    for target in targets:
        cutoff = as_of + timedelta(days=target)
        chosen = next((b for b in ordered if b["end"] >= cutoff), ordered[-1])
        window_ids = {b["bucket_id"] for b in ordered if b["end"] <= chosen["end"]}
        part = netting[netting["bucket_id"].isin(window_ids)]
        demand = part.groupby(KEY, as_index=False).agg(demand=("period_demand", "sum"),
                                                       receipts=("receipts", "sum"),
                                                       max_gap=("gap", "max"))
        last = (part.sort_values("_order").groupby(KEY, as_index=False)
                .agg(unserved=("unserved", "last")))
        frame = demand.merge(last, on=KEY, how="left").merge(opening, on=KEY, how="left")
        frame = frame.merge(sigma, on=KEY, how="left")
        frame["buffer_reference"] = pd.to_numeric(frame.get("buffer_reference"),
                                                  errors="coerce").fillna(0.0)
        frame["qty_current"] = frame["unserved"].clip(lower=0).map(
            lambda v: float(math.ceil(v)) if pd.notna(v) else 0.0)
        target_stock = (pd.to_numeric(frame["demand"], errors="coerce").fillna(0.0)
                        + frame["buffer_reference"])
        frame["qty_higher"] = (target_stock - pd.to_numeric(frame["opening"], errors="coerce")
                               .fillna(0.0) - pd.to_numeric(frame["receipts"], errors="coerce")
                               .fillna(0.0)).clip(lower=0).map(
            lambda v: float(math.ceil(v)) if pd.notna(v) else 0.0)
        frame["qty_higher"] = frame[["qty_current", "qty_higher"]].max(axis=1)
        frame["window_days"] = target

        for uom, group in frame.groupby("canonical_uom", sort=True):
            summary_rows.append(dict(
                window_days=target, uom=uom,
                bucket_id=chosen["bucket_id"],
                bucket_end=chosen["end"].isoformat(),
                actual_days=round((chosen["end"] - as_of).total_seconds() / 86400, 3),
                buckets_count=len(window_ids),
                forecast_demand=round(float(group["demand"].sum()), 6),
                cum_unserved=round(float(group["unserved"].clip(lower=0).sum()), 6),
                gap_keys=int((group["max_gap"].fillna(0) > 0).sum()),
                suggestion_keys=int((group["qty_current"] > 0).sum()),
                qty_current=float(group["qty_current"].sum()),
                qty_higher=float(group["qty_higher"].sum()),
                usage=("scenario_only" if target in SCENARIO_ONLY else "review_candidate"),
                note=("180 天只作产能/春节排期情景，不作采购量" if target in SCENARIO_ONLY
                      else "累计窗口，按真实桶边界；窗口之间不可相加"),
            ))
        for row in frame.itertuples(index=False):
            key_rows.append(dict(window_days=target, bucket_end=chosen["end"].isoformat(),
                                 canonical_sku=row.canonical_sku,
                                 canonical_warehouse=row.canonical_warehouse,
                                 canonical_uom=row.canonical_uom,
                                 forecast_demand=round(float(row.demand or 0), 6),
                                 cum_unserved=round(float(max(0.0, row.unserved or 0)), 6),
                                 qty_current=float(row.qty_current),
                                 qty_higher=float(row.qty_higher),
                                 gap=bool((row.max_gap or 0) > 0)))
    return pd.DataFrame(summary_rows), pd.DataFrame(key_rows)


def write_outputs(summary: pd.DataFrame, keys: pd.DataFrame, doc: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "horizon_windows.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    keys_path = out_dir / "horizon_windows_keys.csv"
    keys.to_csv(keys_path, index=False, encoding="utf-8-sig")
    doc["outputs"] = dict(summary=str(summary_path), keys=str(keys_path))
    (out_dir / "horizon_windows_manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "README.md").write_text(_readme(summary, doc), encoding="utf-8")
    return doc["outputs"]


def _readme(summary: pd.DataFrame, doc: dict) -> str:
    lines = [
        "# 多窗口切片（30/60/90/120/150/180 天）",
        "",
        f"- 来源 run：`{doc['run_dir']}`（run_id `{doc['run_id']}`，as_of `{doc['as_of']}`）",
        f"- 预测：`{doc['forecast_run_id']}`，lead {doc['forecast_lead_days']} 天；"
        f"promoted={doc['forecast_promoted']}",
        "- 窗口按**真实桶边界**取：桶结束 ≥ as_of+N 天的第一个桶；"
        "`actual_days` 可能比 `window_days` 多最多 7 天。",
        "- **每个窗口都是从 as_of 起的累计，窗口之间不能相加**；"
        "`30 天` 不是 `60 天` 的可加子项。",
        "- 数量按 UOM 分开；本表 UOM 组："
        + ", ".join(f"`{u}`（{len(g)} 个窗口）" for u, g in summary.groupby("uom")),
        "- **180 天标 `usage=scenario_only`**：只作产能/春节排期情景，不是采购量；"
        "越远越不准（预测区间未标定、仓分配是假设、窗口按天均摊）。",
        "- 已证到货为 0（在途/PO 无 ETA），`cum_unserved` 是「需求 vs 期初」的模型化缺口。",
        "",
        "## 字段",
        "",
        "| 列 | 含义 |",
        "|---|---|",
        "| window_days | 目标窗口（30/60/…/180） |",
        "| uom | 计量单位；跨 UOM 不相加 |",
        "| bucket_id / bucket_end | 实际采用的最后一个桶及其结束时刻 |",
        "| actual_days | 从 as_of 到 bucket_end 的真实天数 |",
        "| buckets_count | 累计包含的桶数 |",
        "| forecast_demand | 窗口内预测需求合计（个/套） |",
        "| cum_unserved | 窗口末累计未满足 |",
        "| gap_keys | 窗口内曾出现缺口的键数 |",
        "| suggestion_keys | 窗口末仍有缺口的键数（建议量 > 0） |",
        "| qty_current | 覆盖模型化缺口所需数量（逐键向上取整后求和） |",
        "| qty_higher | 缺口 + 14 天参考缓冲（非覆盖率承诺） |",
        "| usage | `review_candidate` / `scenario_only` |",
        "",
        "## 汇总",
        "",
        _markdown_table(summary),
        "",
    ]
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "（无数据）"
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="净额 run 的多窗口切片（不重跑）")
    parser.add_argument("--run", required=True)
    parser.add_argument("--demand", required=True, help="demand_netting.parquet（算 σ 参考缓冲）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    netting, buckets, as_of, manifest = load_run(args.run)
    demand = pd.read_parquet(args.demand)
    keep = demand["in_default_series"].fillna(False).astype(bool)
    history = demand.loc[keep, KEY + ["demand_date", "quantity_default"]].rename(
        columns={"quantity_default": "quantity"})
    summary, keys = build_windows(netting, buckets, as_of, history)
    doc = dict(
        schema_version="horizon-windows/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        run_dir=str(Path(args.run)), run_id=manifest.get("run_id"), as_of=manifest.get("as_of"),
        forecast_run_id=(manifest.get("forecast") or {}).get("run_id"),
        forecast_lead_days=(manifest.get("forecast") or {}).get("lead_days"),
        forecast_promoted=(manifest.get("forecast") or {}).get("forecast_promoted"),
        rule="每窗口 = as_of 到「结束 ≥ as_of+N 天的第一个桶」；累计；不插值；窗口间不可相加",
        scenario_only_windows=sorted(SCENARIO_ONLY),
    )
    outputs = write_outputs(summary, keys, doc, Path(args.out))
    print(json.dumps(dict(rows=len(summary), keys=len(keys), outputs=outputs),
                     ensure_ascii=False, indent=1))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
