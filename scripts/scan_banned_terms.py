# -*- coding: utf-8 -*-
"""扫描工作簿与报告是否出现裸 East / Central（B v6 r5 验收项）。"""
from __future__ import annotations

import re
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
PAT = re.compile(r"(?<![A-Za-z])(?:East|Central)(?![A-Za-z])")


def scan_xlsx(path: str) -> tuple[int, list]:
    hits = []
    for sh in pd.ExcelFile(path).sheet_names:
        d = pd.read_excel(path, sheet_name=sh)
        for c in d.columns:
            n = int(d[c].astype(str).str.contains(PAT, na=False).sum())
            if n:
                hits.append((sh, str(c), n))
    return sum(h[2] for h in hits), hits


def main() -> int:
    xlsx = sys.argv[1]
    md = sys.argv[2] if len(sys.argv) > 2 else None
    total, hits = scan_xlsx(xlsx)
    print(f"工作簿命中: {total}")
    for h in hits:
        print(f"  {h}")
    if md:
        text = open(md, encoding="utf-8").read()
        print(f"报告 md 命中: {len(PAT.findall(text))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
