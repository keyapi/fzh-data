# -*- coding: utf-8 -*-
"""把 API 补入的 21 个文件按账期月上传到 NAS；若 8 月桶已有同名/同茎解压件则删除，避免 7/8 月重复核算。

不改 D:\\NAS与我共享\\。默认执行（用户已确认补入）。--dry-run 只出计划。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit_vs_drm import AUG, DATA, JUL, load_manifest, orig_name_from_cache, norm_person
from combine_jul_aug import skip_for_now
from nas_admin import ROOT, nas_admin
from parse import keep_approval, keep_attachment, period_month_bucket, safe_filename, filename_period_month
from person_folders import nas_person_folder

REPORT = DATA / "reports"
KEEP_IN_AUG = {"TOODDLYDUUS-20260707-202608.24.CSV"}


def dest_bucket(rec: dict, filename: str) -> str:
    """钉钉「账期日期」单月优先；跨月才看文件名。9 月账期不进 7/8 桶。

    木已成舟：6 月提交窗（至 2026-07-03）已经核算过的单，不再改归 7/8 月桶。
    """
    created = str(rec.get("createTime") or "")[:10]
    if created and created <= "2026-07-03":
        return ""
    n = filename or ""
    if n.upper() in KEEP_IN_AUG:
        return AUG
    months = [m for m in (rec.get("period_months") or []) if m]
    jul_aug_sep = [m for m in months if m in {"2026-07", "2026-08", "2026-09"}]
    if jul_aug_sep == ["2026-07"]:
        return JUL
    if jul_aug_sep == ["2026-08"]:
        return AUG
    if jul_aug_sep == ["2026-09"]:
        return ""
    fm = filename_period_month(n)
    if fm == "2026-09":
        return ""
    if fm == "2026-07":
        return JUL
    if fm == "2026-08":
        return AUG
    if "2026-08" in months:
        return AUG
    if "2026-07" in months:
        return JUL
    return ""


def stem_key(name: str) -> str:
    p = Path(name)
    stem = p.stem
    if stem.lower().endswith(".xlsx"):
        stem = Path(stem).stem
    return stem.upper().replace(" ", "").replace("_", "-")


def nas_people(nas, bucket: str) -> list[str]:
    return [x["name"] for x in nas.get_file_list(f"{ROOT}/{bucket}", limit=500) if x.get("is_dir")]


def resolve_person(people: list[str], originator: str) -> str:
    want = nas_person_folder(norm_person(originator))
    for p in people:
        if p == want or nas_person_folder(norm_person(p)) == want:
            return want
    return want


def list_person_files(nas, bucket: str, person: str) -> list[dict]:
    return [x for x in nas.get_file_list(f"{ROOT}/{bucket}/{person}", limit=1000) if not x.get("is_dir")]


def collect_jobs() -> list[dict]:
    recs = load_manifest()
    from audit_vs_drm import index_drm

    jul_keys = {(norm_person(f["person"]), f["name"].upper()) for f in index_drm(JUL)}
    aug_keys = {(norm_person(f["person"]), f["name"].upper()) for f in index_drm(AUG)}
    import pandas as pd

    combo_path = REPORT / "combined_jul_aug清单.xlsx"
    whitelist = set()
    if combo_path.is_file():
        cdf = pd.read_excel(combo_path)
        for _, r in cdf[cdf["来源"] == "钉钉API"].iterrows():
            whitelist.add((norm_person(str(r["人"])), str(r["文件"]).upper()))

    jobs = []
    seen = set()
    for rec in recs:
        if not keep_approval(rec.get("status") or "", rec.get("result") or ""):
            continue
        submit = rec.get("submit_bucket") or ""
        if submit not in {JUL, AUG}:
            continue
        person = rec.get("originator") or "unknown"
        st = rec.get("status") or ""
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or orig_name_from_cache(att.get("path") or "")
            if skip_for_now(person, st, name):
                continue
            src = DATA / str(att.get("path") or "")
            if not src.is_file():
                continue
            bucket = dest_bucket(rec, name)
            key = (norm_person(person), name.upper())
            if whitelist and key not in whitelist:
                continue
            in_jul = key in jul_keys
            in_aug = key in aug_keys
            already_dest = (bucket == JUL and in_jul) or (bucket == AUG and in_aug)
            jobs.append(
                {
                    "审批编号": rec.get("businessId"),
                    "processInstanceId": rec.get("processInstanceId"),
                    "发起人": person,
                    "发起时间": rec.get("createTime"),
                    "账期月": ",".join(rec.get("period_months") or []),
                    "提交桶": submit,
                    "核算桶": bucket,
                    "原始文件名": name,
                    "fileId": att.get("fileId"),
                    "本地缓存": str(src),
                    "bytes": src.stat().st_size,
                    "本地7月已有": in_jul,
                    "本地8月已有": in_aug,
                    "跳过上传_已在核算桶": already_dest,
                }
            )
            seen.add((norm_person(person), name.upper()))
    return jobs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    jobs = collect_jobs()
    nas = nas_admin()
    if not nas.available or not nas._fl:
        raise SystemExit("NAS 未连接")
    jul_people = nas_people(nas, JUL)
    aug_people = nas_people(nas, AUG)
    log_rows = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for job in jobs:
        person = job["发起人"]
        name = job["原始文件名"]
        bucket = job["核算桶"]
        people = jul_people if bucket == JUL else aug_people
        dest_person = resolve_person(people, person)
        dest_dir = f"{ROOT}/{bucket}/{dest_person}"
        dest_file = f"{dest_dir}/{name}"
        dest_files = list_person_files(nas, bucket, dest_person) if dest_person in people else []
        dest_names = {x.get("name") for x in dest_files}
        dest_stems = {stem_key(x.get("name") or "") for x in dest_files}

        aug_person = resolve_person(aug_people, person)
        aug_files = list_person_files(nas, AUG, aug_person) if aug_person in aug_people else []
        aug_hits = [
            x
            for x in aug_files
            if (x.get("name") or "").upper() == name.upper() or stem_key(x.get("name") or "") == stem_key(name)
        ]

        action = []
        skip_upload = bool(job.get("跳过上传_已在核算桶"))
        if name in dest_names or stem_key(name) in dest_stems:
            skip_upload = True
            action.append("核算桶已有同名或同茎文件_跳过上传")
        if bucket == AUG and aug_hits and (name in dest_names or stem_key(name) in dest_stems):
            action.append("8月桶已有解压件_不再传zip以免重复")

        rec = {
            **job,
            "时间": ts,
            "NAS人名文件夹": dest_person,
            "NAS目标目录": dest_dir,
            "NAS目标文件": dest_file,
            "8月桶命中": ";".join(x.get("path") or x.get("name") for x in aug_hits),
            "dry_run": args.dry_run,
        }

        if not skip_upload and not args.dry_run:
            nas.create_folder(f"{ROOT}/{bucket}", dest_person)
            with tempfile.TemporaryDirectory() as td:
                local = Path(td) / safe_filename(name)
                shutil.copy2(job["本地缓存"], local)
                up = nas._fl.upload_file(
                    dest_path=dest_dir,
                    file_path=str(local),
                    create_parents=True,
                    overwrite=False,
                    progress_bar=False,
                )
            rec["上传结果"] = str(up)[:400]
            action.append("已上传")
            if bucket == JUL and dest_person not in jul_people:
                jul_people.append(dest_person)
            if bucket == AUG and dest_person not in aug_people:
                aug_people.append(dest_person)
        elif skip_upload:
            rec["上传结果"] = "skipped_exists"
        else:
            rec["上传结果"] = "dry_run"
            action.append("计划上传")

        removed = []
        # 核算进 7 月：8 月桶同名/同茎必须删，避免 7 月算一遍 8 月又算一遍
        if bucket == JUL:
            for hit in aug_hits:
                hp = hit.get("path")
                if not hp:
                    continue
                if args.dry_run:
                    removed.append(hp + " (dry-run)")
                    action.append("计划从8月桶删除")
                else:
                    nas._fl.delete_blocking_function(hp)
                    removed.append(hp)
                    action.append("已从8月桶删除")
        rec["从8月桶移除"] = ";".join(removed)
        rec["动作"] = " | ".join(action)
        log_rows.append(rec)
        print(rec["动作"], dest_person, name, "->", bucket, "aug_hits", rec["8月桶命中"])

    import pandas as pd

    df = pd.DataFrame(log_rows)
    REPORT.mkdir(parents=True, exist_ok=True)
    xlsx = REPORT / "NAS补入21_操作记录.xlsx"
    md = REPORT / "NAS补入21_操作记录.md"
    js = REPORT / "NAS补入21_操作记录.json"
    df.to_excel(xlsx, index=False)
    js.write_text(json.dumps(log_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# NAS 补入 21 操作记录",
        f"- 时间 {ts}",
        f"- dry-run={args.dry_run}",
        f"- 财务根 `{ROOT}`",
        f"- 口径：按账期月进 7/8 月桶 `{JUL}` / `{AUG}` / 人名 / 原名；7 月件若 8 月桶有同名或同茎（zip/csv）则从 8 月删除。",
        f"- 行数 {len(df)}",
        "",
        df.to_string(index=False),
        "",
        f"Excel: `{xlsx}`",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", xlsx)
    print(md.read_text(encoding="utf-8")[:2500])


if __name__ == "__main__":
    main()
