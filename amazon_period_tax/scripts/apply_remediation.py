# -*- coding: utf-8 -*-
"""把 corrections.v1.json 应用到定稿原件，生成 corrected 副本（不覆盖原件）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "amazon_period_tax"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from remediation import apply_corrections, load_corrections  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrections", required=True)
    ap.add_argument("--period", required=True, help="YYYYMM")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    corrections = load_corrections(Path(args.corrections))
    result = apply_corrections(
        src=Path(args.src),
        corrections=corrections,
        period=args.period,
        out=Path(args.out),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
