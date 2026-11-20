# -*- coding: utf-8 -*-
"""把 aflow/钉钉导出按「账期日期」自然月切开。发起时间窗 ≠ 账期月。

钉钉后台只能按发起时间导出；要「只保留 7 月账期」必须先宽窗导出，再按账期月过滤。
可选 --exclude-keys 做迟交跨月剔除（每行一个 审批编号|账期日期|销售账户|销售额）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ding_xlsx import enrich, exclude_keys, id_text, read_dingtalk_xlsx_records
from export_lineage import build_export_lineage, empty_enriched_frame
from export_period_excels import drop_helper, write_xlsx
from parse import keep_approval


def load_exclude_keys(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    keys = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keys.add(line)
    return keys


def _cell_text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def filter_period_rows(
    df, period: str, keys: set[str] | None = None
) -> tuple[object, dict[str, int]]:
    """账期月 + 审批状态（完成/审批中且非拒绝）+ 迟交唯一键 三重过滤。

    返回 (保留行, 计数)。计数用于核对 N 进 M 出：period 是账期月命中的行数，
    excluded_status 是其中被审批状态剔掉的，excluded_late 是被迟交登记剔掉的。
    """
    period_rows = df[df["账期月"] == period].copy()
    n_period = len(period_rows)
    keep_mask = period_rows.apply(
        lambda r: keep_approval(_cell_text(r.get("审批状态")), _cell_text(r.get("审批结果"))),
        axis=1,
    )
    kept = period_rows[keep_mask].copy()
    excluded_status = n_period - len(kept)
    excluded_late = 0
    if keys:
        before = len(kept)
        kept = exclude_keys(kept, keys)
        excluded_late = before - len(kept)
    counts = {
        "period": n_period,
        "excluded_status": excluded_status,
        "excluded_late": excluded_late,
        "kept": len(kept),
    }
    return kept, counts


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True, help="aflow / 钉钉导出 xlsx")
    ap.add_argument("--period", required=True, help="账期月 YYYY-MM，例如 2026-07")
    ap.add_argument("--out", required=True, help="过滤后 xlsx")
    ap.add_argument(
        "--exclude-keys",
        default="",
        help="可选：迟交登记唯一键，每行一条，命中则从本月定稿去掉",
    )
    args = ap.parse_args()
    src = Path(args.src)
    raw, read_report = read_dingtalk_xlsx_records(src)
    if raw.empty and not read_report.get("rows_failed"):
        raise SystemExit(f"读不到含「账期日期」的行: {src}")
    en = enrich(raw) if not raw.empty else empty_enriched_frame()
    keys = load_exclude_keys(Path(args.exclude_keys)) if args.exclude_keys else set()
    lineage = build_export_lineage(en, args.period, keys, read_report)
    print(lineage.summary())
    blockers = lineage.blockers()
    if blockers:
        for b in blockers:
            print(f"BLOCKING: {b}")
        raise SystemExit(2)  # 有阻断项：不产出正式定稿，也不静默出半截表
    kept = lineage.partitions["kept"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if "审批编号" in kept.columns:
        kept["审批编号"] = kept["审批编号"].map(id_text)
    write_xlsx(out, {"核算行": drop_helper(kept)})
    print(lineage.summary() + f" wrote={out}")


if __name__ == "__main__":
    main()
