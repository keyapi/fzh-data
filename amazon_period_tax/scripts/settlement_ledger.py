# -*- coding: utf-8 -*-
"""结算台账 CLI：扫描账期桶，报告跨桶重复结算（只读，不删不改）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "amazon_period_tax"
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for p in (_REPO, _PKG, _DING):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from settlement_ledger import find_duplicates, format_report, scan_buckets  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="跨账期桶重复结算清单（只报告）")
    ap.add_argument("--root", default="", help="账期资料根目录（默认 LOCAL_NAS_PERIOD_ROOT）")
    ap.add_argument("--json-out", default="", help="可选：把明细写到本地 json（不写 NAS/Google）")
    ap.add_argument("--fail-on-dup", action="store_true", help="发现重复时非 0 退出")
    args = ap.parse_args()

    if args.root:
        root = Path(args.root)
    else:
        from paths import local_nas_period  # noqa: E402

        root = local_nas_period()
    if not root.is_dir():
        raise SystemExit(f"根目录不存在: {root}")

    records = scan_buckets(root)
    duplicates = find_duplicates(records)
    for line in format_report(records, duplicates):
        print(line)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"records": records, "duplicates": duplicates}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("json:", out)
    if args.fail_on_dup and duplicates:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
