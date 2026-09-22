# -*- coding: utf-8 -*-
"""钉钉标题 vs DRM 人名文件夹去重：同一原名只留 DRM 惯用文件夹。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from nas_admin import ROOT, nas_admin
from nas_finance_buckets import walk_files
from person_folders import DINGTALK_TO_FOLDER
from paths import OA_REPORTS

JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
REPORT = OA_REPORTS
ALIAS_DROP = dict(DINGTALK_TO_FOLDER)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    nas = nas_admin()
    log = []
    for b in (JUL, AUG):
        files = walk_files(nas, f"{ROOT}/{b}", depth=2)
        by = {}
        for f in files:
            by.setdefault((f.get("person"), (f.get("name") or "").upper()), []).append(f)
        for alias, canonical in ALIAS_DROP.items():
            for f in files:
                if f.get("person") != alias:
                    continue
                key = (canonical, (f.get("name") or "").upper())
                if key in by:
                    nas._fl.delete_blocking_function(f["path"])
                    log.append({"桶": b, "删除": f["path"], "保留": by[key][0]["path"], "原因": f"{alias}与{canonical}同名"})
                    print("DEL", f["path"])
            # 别名文件夹里剩下的（8 月新补、7 月没有对应 DRM 名）→ 挪到惯用名
            files = walk_files(nas, f"{ROOT}/{b}", depth=2)
            dest_dir = f"{ROOT}/{b}/{canonical}"
            people = [x.get("name") for x in nas.get_file_list(f"{ROOT}/{b}", limit=500) if x.get("is_dir")]
            if canonical not in people:
                nas.create_folder(f"{ROOT}/{b}", canonical)
            for f in files:
                if f.get("person") != alias:
                    continue
                nas._fl.start_copy_move(path=f["path"], dest_folder_path=dest_dir, remove_src=True, overwrite=False)
                log.append({"桶": b, "移动": f["path"], "到": dest_dir, "原因": f"{alias}→{canonical}"})
                print("MOVE", f["path"], "->", dest_dir)
    REPORT.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(log).to_excel(REPORT / "NAS_人名文件夹去重.xlsx", index=False)
    (REPORT / "NAS_人名文件夹去重.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print("n", len(log))


if __name__ == "__main__":
    main()
