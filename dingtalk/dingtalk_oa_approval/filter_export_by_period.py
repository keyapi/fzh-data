# -*- coding: utf-8 -*-
"""把 aflow/钉钉导出按「账期日期」自然月切开。发起时间窗 ≠ 账期月。

钉钉后台只能按发起时间导出；要「只保留 7 月账期」必须先宽窗导出，再按账期月过滤。
可选 --exclude-keys 做迟交跨月剔除（每行一个 审批编号|账期日期|销售账户|销售额）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ding_xlsx import enrich, exclude_keys, id_text, read_dingtalk_xlsx
from export_period_excels import drop_helper, write_xlsx


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
    df = read_dingtalk_xlsx(src)
    if df.empty:
        raise SystemExit(f"读不到含「账期日期」的行: {src}")
    n_in = len(df)
    en = enrich(df)
    kept = en[en["账期月"] == args.period].copy()
    n_period = len(kept)
    excluded = 0
    if args.exclude_keys:
        keys = load_exclude_keys(Path(args.exclude_keys))
        before = len(kept)
        kept = exclude_keys(kept, keys)
        excluded = before - len(kept)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if "审批编号" in kept.columns:
        kept["审批编号"] = kept["审批编号"].map(id_text)
    write_xlsx(out, {"核算行": drop_helper(kept)})
    print(
        f"in={n_in} period={args.period} kept={n_period} "
        f"excluded_late={excluded} wrote={out} rows={len(kept)}"
    )


if __name__ == "__main__":
    main()
