# -*- coding: utf-8 -*-
"""生成 Colab 用账期定稿：账期月过滤 + 撤销剔除 + 销售账户规范化为表上「渠道账号」。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from channel_canonical import canonical_account  # noqa: E402
from ding_xlsx import enrich, id_text, read_dingtalk_xlsx_records  # noqa: E402
from export_lineage import build_export_lineage, empty_enriched_frame  # noqa: E402
from export_period_excels import drop_helper, write_xlsx  # noqa: E402


def normalize_accounts(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    n = 0
    for idx, row in out.iterrows():
        if str(row.get("选择平台", "")).strip() != "亚马逊":
            continue
        src_col = str(row.get("销售账户来源列") or "").strip()
        raw = str(row.get("销售账户_展开") or "").strip()
        if not raw and src_col and src_col in out.columns:
            raw = str(row.get(src_col) or "").strip()
        canon = canonical_account(raw)
        if not canon or canon == raw:
            continue
        if src_col and src_col in out.columns:
            out.at[idx, src_col] = canon
            n += 1
        out.at[idx, "销售账户_展开"] = canon
    return out, n


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="colab")
    ap.add_argument(
        "--exclude-keys",
        default="",
        help="迟交登记唯一键文件，命中行从本月定稿剔除（与 filter_export_by_period 相同）",
    )
    args = ap.parse_args()

    raw, read_report = read_dingtalk_xlsx_records(Path(args.src))
    if raw.empty and not read_report.get("rows_failed"):
        raise SystemExit(f"读不到含「账期日期」的行: {args.src}")
    en = enrich(raw) if not raw.empty else empty_enriched_frame()
    keys = set()
    if args.exclude_keys:
        from filter_export_by_period import load_exclude_keys  # noqa: E402

        keys = load_exclude_keys(Path(args.exclude_keys))
    lineage = build_export_lineage(en, args.period, keys, read_report)
    print(lineage.summary())
    blockers = lineage.blockers()
    if blockers:
        for b in blockers:
            print(f"BLOCKING: {b}")
        raise SystemExit(2)  # 有阻断项：不产出正式定稿
    kept = lineage.partitions["kept"].copy()
    kept, n_norm = normalize_accounts(kept)
    out = Path(args.out)
    write_xlsx(out, {"核算行": drop_helper(kept)})
    amz = kept[kept["选择平台"] == "亚马逊"]
    print(
        f"wrote {out} rows={len(kept)} amz={len(amz)} "
        f"excluded_late={lineage.counts['excluded_late']} "
        f"account_normalized={n_norm} dup={len(lineage.duplicate_keys)}"
    )


if __name__ == "__main__":
    main()
