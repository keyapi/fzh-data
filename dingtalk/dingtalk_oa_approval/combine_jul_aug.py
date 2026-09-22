# -*- coding: utf-8 -*-
"""综合：我们 API 已下 + DRM 桶已有。排除 YTQ PDF、ZKY 审批中 csv。不写 NAS 同步盘。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from audit_vs_drm import (
    AUG,
    JUL,
    DATA,
    MANIFEST,
    SKIP_NAMES,
    classify_suffix,
    index_drm,
    load_manifest,
    orig_name_from_cache,
    norm_person,
)
from person_folders import mentions
from parse import keep_approval, keep_attachment, safe_filename

COMBINED = DATA / "combined_jul_aug"
REPORT = DATA / "reports"
USEFUL = {"txt_csv", "excel", "pdf"}


def skip_for_now(originator: str, status: str, name: str) -> str:
    p = originator or ""
    n = name or ""
    suf = Path(n).suffix.lower()
    if mentions("YTQ", p) and suf == ".pdf":
        return "skip_ytq_pdf"
    if mentions("ZKY", p) and status in {"RUNNING", "审批中"}:
        return "skip_zky_running"
    return ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    recs = load_manifest()
    by_name = {}
    for rec in recs:
        rec["keep"] = keep_approval(rec.get("status") or "", rec.get("result") or "")
        for att in rec.get("attachments") or []:
            fn = (att.get("fileName") or orig_name_from_cache(att.get("path") or "")).upper()
            by_name.setdefault(fn, []).append(rec)

    if COMBINED.exists():
        shutil.rmtree(COMBINED)
    COMBINED.mkdir(parents=True, exist_ok=True)

    copied_drm = copied_us = skipped = 0
    rows = []
    have = set()

    for bucket, files in ((JUL, index_drm(JUL)), (AUG, index_drm(AUG))):
        for f in files:
            if f["name"].lower() in SKIP_NAMES:
                continue
            if str(f["name"]).startswith("合并Amazon"):
                continue
            if f["kind"] not in USEFUL:
                continue
            dest_dir = COMBINED / bucket / safe_filename(f["person"])
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / safe_filename(f["name"])
            shutil.copy2(f["abs"], dest)
            copied_drm += 1
            have.add((bucket, f["person_n"], f["name_u"]))
            rows.append({"来源": "DRM桶", "桶": bucket, "人": f["person"], "文件": f["name"], "bytes": f["size"]})

    for rec in recs:
        if not rec.get("keep"):
            continue
        bucket = rec.get("submit_bucket") or ""
        if bucket not in {JUL, AUG}:
            continue
        person = rec.get("originator") or "unknown"
        person_n = norm_person(person)
        st = rec.get("status") or rec.get("status_cn") or ""
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or orig_name_from_cache(att.get("path") or "")
            why = skip_for_now(person, st, name)
            if why:
                skipped += 1
                rows.append({"来源": why, "桶": bucket, "人": person, "文件": name})
                continue
            key = (bucket, person_n, name.upper())
            alt = (bucket, person, name.upper())
            if key in have or (bucket, person, name.upper()) in have:
                continue
            # 已有同人名文件夹则跟 DRM
            dest_person = person
            parent = COMBINED / bucket
            if parent.exists():
                for d in parent.iterdir():
                    if d.is_dir() and norm_person(d.name) == person_n:
                        dest_person = d.name
                        break
            src = DATA / str(att.get("path") or "")
            if not src.is_file():
                continue
            dest_dir = COMBINED / bucket / safe_filename(dest_person)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / safe_filename(name)
            if dest.exists():
                dest = dest_dir / f"{att.get('fileId') or 'id'}__{safe_filename(name)}"
            shutil.copy2(src, dest)
            copied_us += 1
            have.add(key)
            rows.append({"来源": "钉钉API", "桶": bucket, "人": dest_person, "文件": dest.name, "bytes": dest.stat().st_size})

    import pandas as pd

    REPORT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    xlsx = REPORT / "combined_jul_aug清单.xlsx"
    df.to_excel(xlsx, index=False)
    print(f"DRM拷入 {copied_drm} ；API补入 {copied_us} ；按约定跳过 {skipped}")
    print(f"合计文件 {sum(1 for p in COMBINED.rglob('*') if p.is_file())} → {COMBINED}")
    print(f"清单 {xlsx}")
    print("来源", df["来源"].value_counts().to_dict() if not df.empty else {})


if __name__ == "__main__":
    main()
