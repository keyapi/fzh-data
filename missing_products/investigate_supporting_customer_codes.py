# -*- coding: utf-8 -*-
"""Read-only audit of customer codes registered on PK# and HM1510 items."""

from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SSH_KEY = Path(r"D:\Work\Aliyun\ssh\aliyun_fzh_erpnext_20240726.pem")
SSH_HOST = "frappe@47.116.128.218"

SQL = r'''
    select i.name as item_code, i.item_name, i.item_group, c.ref_code
    from tabItem i
    join `tabItem Customer Detail` c on c.parent = i.name
    where (i.name like 'PK#%%' or i.name like 'HM1510%%')
      and ifnull(c.ref_code, '') != ''
    order by i.name, c.ref_code;
'''


def summarize(rows: list[dict]) -> dict:
    by_type = Counter("PK#" if row["item_code"].startswith("PK#") else "HM1510" for row in rows)
    item_ref_pairs = {(row["item_code"], row["ref_code"]) for row in rows}
    ref_to_items: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        ref_to_items[row["ref_code"]].add(row["item_code"])
    duplicates = {ref: sorted(items) for ref, items in ref_to_items.items() if len(items) > 1}
    return {
        "row_count": len(rows),
        "unique_item_customer_pairs": len(item_ref_pairs),
        "unique_customer_codes": len(ref_to_items),
        "by_item_type": dict(by_type),
        "duplicate_customer_codes": duplicates,
    }


def main() -> None:
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-i", str(SSH_KEY), SSH_HOST,
        "cd ~/frappe-bench && bench --site erpnext.vilavi.cn mariadb --batch --raw",
    ]
    completed = subprocess.run(
        command, input=SQL, text=True, encoding="utf-8",
        capture_output=True, timeout=180, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Remote audit failed ({completed.returncode}): {completed.stderr[-2000:]}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        rows = []
    else:
        headers = lines[0].split("\t")
        rows = [dict(zip(headers, line.split("\t"))) for line in lines[1:]]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summarize(rows),
        "rows": rows,
    }
    out = HERE / "out" / f"PK_HM1510客户物料号只读调查_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), **result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
