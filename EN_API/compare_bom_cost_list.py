# -*- coding: utf-8 -*-
"""拉取最新「BOM 成本表」(BOM Cost List V2)，并与之前的一份快照做逐格对比。

用途：确认 2026-09-10 那次「工艺路线→BOM 同步」事故的恢复是否完整
      —— 报表数据若与事故前的快照一致，说明 BOM 侧数据已还原。

用法:
  python compare_bom_cost_list.py                      # 拉最新 vs 数据源/ 里最新的一份旧快照
  python compare_bom_cost_list.py --old 数据源/xxx.json.gz
  python compare_bom_cost_list.py --new-only           # 只拉新快照不做对比

输出:
  数据源/bom_cost_list_v2_<ts>.json.gz    新快照（原始响应）
  out/bom_cost_diff_<ts>.xlsx             差异明细（每个不同单元格一行）
"""
from __future__ import annotations

import argparse
import datetime
import glob
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bom_cost_list_excel import DATA_DIR, OUT_DIR, fetch_report, load_credentials  # noqa: E402

KEY_FIELD = "item_fg"


def rows_as_dict(report: dict) -> list[dict]:
    cols = [c["fieldname"] for c in report["columns"]]
    out = []
    for row in report["result"]:
        if isinstance(row, dict):
            out.append(row)
        else:
            out.append({c: v for c, v in zip(cols, row)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="BOM 成本表快照 + 对比")
    ap.add_argument("--env", default="prod", choices=["prod", "test"])
    ap.add_argument("--old", type=Path, default=None, help="对比用的旧快照 gz")
    ap.add_argument("--new", type=Path, default=None, help="用已有新快照，不联网")
    ap.add_argument("--new-only", action="store_true", help="只拉新快照")
    args = ap.parse_args()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1) 新快照
    if args.new:
        new_path = args.new
        print(f"读已有新快照: {new_path}")
    else:
        key, sec = load_credentials(args.env)
        report = fetch_report(args.env, key, sec)
        new_path = DATA_DIR / f"bom_cost_list_v2_{ts}.json.gz"
        with gzip.open(new_path, "wt", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)
        print(f"新快照: {new_path}  ({new_path.stat().st_size/1024:.0f} KB)")

    with gzip.open(new_path, "rt", encoding="utf-8") as f:
        new_report = json.load(f)
    new_rows = rows_as_dict(new_report)
    new_cols = [c["fieldname"] for c in new_report["columns"]]
    print(f"新表: {len(new_rows)} 行, {len(new_cols)} 列")
    if args.new_only:
        return 0

    # 2) 旧快照
    old_path = args.old
    if not old_path:
        cands = sorted((p for p in glob.glob(str(DATA_DIR / "bom_cost_list_v2_*.json.gz"))
                        if Path(p).resolve() != new_path.resolve()),
                       key=lambda p: Path(p).stat().st_mtime)
        if not cands:
            raise SystemExit("没有可对比的旧快照")
        old_path = Path(cands[-1])
    with gzip.open(old_path, "rt", encoding="utf-8") as f:
        old_report = json.load(f)
    old_rows = rows_as_dict(old_report)
    old_cols = [c["fieldname"] for c in old_report["columns"]]
    print(f"旧表: {old_path.name}  {len(old_rows)} 行, {len(old_cols)} 列  ← 对比基准")

    # 3) 对比
    print("\n── 结构 ──")
    print("  列名完全一致:", old_cols == new_cols)
    if old_cols != new_cols:
        print("   仅旧表有:", [c for c in old_cols if c not in new_cols])
        print("   仅新表有:", [c for c in new_cols if c not in old_cols])

    old_map = {r.get(KEY_FIELD): r for r in old_rows if r.get(KEY_FIELD)}
    new_map = {r.get(KEY_FIELD): r for r in new_rows if r.get(KEY_FIELD)}
    only_old = sorted(set(old_map) - set(new_map))
    only_new = sorted(set(new_map) - set(old_map))
    print(f"\n  行数: 旧 {len(old_map)}  新 {len(new_map)}")
    print(f"  仅旧表存在的 {KEY_FIELD}: {len(only_old)}", only_old[:10])
    print(f"  仅新表存在的 {KEY_FIELD}: {len(only_new)}", only_new[:10])

    common = sorted(set(old_map) & set(new_map))
    shared_cols = [c for c in old_cols if c in new_cols]
    diffs = []
    per_col: dict[str, int] = {}
    rows_with_diff = set()
    for k in common:
        a, b = old_map[k], new_map[k]
        for c in shared_cols:
            va, vb = a.get(c), b.get(c)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                same = abs(float(va) - float(vb)) < 1e-6
            else:
                same = (va or "") == (vb or "")
            if not same:
                diffs.append({KEY_FIELD: k, "column": c, "old": va, "new": vb})
                per_col[c] = per_col.get(c, 0) + 1
                rows_with_diff.add(k)

    print(f"\n── 差异 ──")
    print(f"  有差异的行: {len(rows_with_diff)} / {len(common)}")
    print(f"  不同单元格: {len(diffs)}")
    for c, n in sorted(per_col.items(), key=lambda x: -x[1])[:25]:
        print(f"    {c:34s} {n}")
    for d in diffs[:15]:
        print(f"    e.g. {d[KEY_FIELD]}  {d['column']}: {d['old']!r} -> {d['new']!r}")

    if diffs:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "差异明细"
        ws.append([KEY_FIELD, "column", "old", "new"])
        for d in diffs:
            ws.append([d[KEY_FIELD], d["column"], d["old"], d["new"]])
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_xlsx = OUT_DIR / f"bom_cost_diff_{ts}.xlsx"
        wb.save(out_xlsx)
        print(f"\n差异明细已写出: {out_xlsx}")

    print("\n结论:", "两份数据完全一致 ✅" if not diffs and not only_old and not only_new
          else "存在差异，见上表 ⚠️")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
