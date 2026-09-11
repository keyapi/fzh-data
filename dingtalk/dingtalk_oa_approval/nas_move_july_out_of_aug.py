# -*- coding: utf-8 -*-
"""把 8 月桶里文件名属于 7 月账期的附件挪到 7 月桶，避免两月重复计算。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from nas_admin import ROOT, nas_admin
from nas_finance_buckets import walk_files
from paths import OA_REPORTS

JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
REPORT = OA_REPORTS

# 跨 7–8 月的文件留在提交窗（8 月桶），不挪
KEEP_IN_AUG = {"TOODDLYDUUS-20260707-202608.24.CSV"}


def is_july_name(name: str) -> bool:
    n = name or ""
    nu = n.upper()
    if nu in KEEP_IN_AUG:
        return False
    if "2026-08" in n or "2026-8-" in n or "2026-8." in n:
        return False
    if "2026-07" in n or "2026-7-" in n or "2026-7." in n:
        return True
    if re.search(r"202607\d{2}", n):
        return True
    if "-7-25" in n or "-7-27" in n:
        return True
    return False


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    nas = nas_admin()
    jul_files = walk_files(nas, f"{ROOT}/{JUL}", depth=2)
    aug_files = walk_files(nas, f"{ROOT}/{AUG}", depth=2)
    jul_people = [x.get("name") for x in nas.get_file_list(f"{ROOT}/{JUL}", limit=500) if x.get("is_dir")]
    log = []
    for h in aug_files:
        n = h.get("name") or ""
        if not is_july_name(n):
            continue
        person = h.get("person") or ""
        dest_dir = f"{ROOT}/{JUL}/{person}"
        already = any(
            (x.get("name") or "").upper() == n.upper() and (x.get("person") or "") == person for x in jul_files
        )
        rec = {"src": h["path"], "name": n, "person": person, "dest_dir": dest_dir}
        if person not in jul_people:
            cr = nas.create_folder(f"{ROOT}/{JUL}", person)
            rec["建7月文件夹"] = cr.get("success")
            jul_people.append(person)
        if already:
            nas._fl.delete_blocking_function(h["path"])
            rec["动作"] = "7月已有_删除8月重复"
        else:
            nas._fl.start_copy_move(path=h["path"], dest_folder_path=dest_dir, remove_src=True, overwrite=False)
            rec["动作"] = "8月→7月移动"
        log.append(rec)
        print(rec["动作"], n, person)

    REPORT.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    df = pd.DataFrame(log)
    xlsx = REPORT / "NAS_8月桶7月账期挪到7月.xlsx"
    df.to_excel(xlsx, index=False)
    (REPORT / "NAS_8月桶7月账期挪到7月.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print("moved", len(log), xlsx)


if __name__ == "__main__":
    main()
