# -*- coding: utf-8 -*-
"""把浏览器 aflow 下到本地的附件，按账期月补进财务 NAS。

默认 dry-run。真上传必须 --apply 且 --confirm-scope。不写本地 NAS 同步盘。
aflow 落盘：<DINGTALK_OA_WORK>/dingtalk_oa_approval_data/aflow_attachments/<数据id>/<原名>
数据id = processInstanceId，用 OA manifest 找发起人/账期月；对不上的行进报告，不静默丢弃。
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

from audit_vs_drm import AUG, DATA, JUL, load_manifest
from nas_admin import ROOT, nas_admin
from nas_upload_api21 import dest_bucket, list_person_files, nas_people, resolve_person, stem_key
from parse import keep_attachment, safe_filename
from paths import OA_WORK

USEFUL_SUFFIX = {".txt", ".csv", ".xlsx", ".xls", ".pdf", ".zip"}


def default_aflow_root() -> Path:
    return OA_WORK / "dingtalk_oa_approval_data" / "aflow_attachments"


def manifest_by_instance() -> dict[str, dict]:
    out = {}
    for rec in load_manifest():
        iid = rec.get("processInstanceId") or ""
        if iid:
            out[str(iid)] = rec
    return out


def collect_jobs(src: Path, inst_map: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    jobs = []
    unmatched = []
    if not src.is_dir():
        raise FileNotFoundError(src)
    for inst_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        iid = inst_dir.name
        rec = inst_map.get(iid)
        files = [p for p in inst_dir.iterdir() if p.is_file() and p.suffix.lower() in USEFUL_SUFFIX]
        if rec is None:
            unmatched.append(
                {
                    "processInstanceId": iid,
                    "files": [p.name for p in files],
                    "reason": "OA manifest 没有这条数据id；先 fetch_attachments 或核对导出表",
                }
            )
            continue
        person = rec.get("originator") or ""
        for fpath in files:
            fake_att = {"fileName": fpath.name, "kind": "账期明细"}
            if not keep_attachment(fake_att) and fpath.suffix.lower() != ".txt":
                continue
            bucket = dest_bucket(rec, fpath.name)
            jobs.append(
                {
                    "审批编号": rec.get("businessId"),
                    "processInstanceId": iid,
                    "发起人": person,
                    "发起时间": rec.get("createTime"),
                    "账期月": ",".join(rec.get("period_months") or []),
                    "核算桶": bucket,
                    "原始文件名": fpath.name,
                    "本地缓存": str(fpath),
                    "bytes": fpath.stat().st_size,
                    "跳过上传_无核算桶": not bucket,
                }
            )
    return jobs, unmatched


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="", help="aflow_attachments 根目录；默认 DINGTALK_OA_WORK 下约定路径")
    ap.add_argument("--apply", action="store_true", help="真正上传；默认只出计划")
    ap.add_argument("--confirm-scope", default="", help="写 NAS 必填，例如 july-2026-it-se-gaps")
    args = ap.parse_args()
    if args.apply and not args.confirm_scope.strip():
        raise SystemExit("写 NAS 必须带 --confirm-scope（例如 july-2026-it-se-gaps）")

    src = Path(args.src) if args.src else default_aflow_root()
    inst_map = manifest_by_instance()
    jobs, unmatched = collect_jobs(src, inst_map)
    print(f"src={src} jobs={len(jobs)} unmatched_dirs={len(unmatched)}")
    for u in unmatched:
        print("UNMATCHED", u["processInstanceId"], u["reason"], u["files"])

    nas = None
    jul_people: list[str] = []
    aug_people: list[str] = []
    if args.apply:
        nas = nas_admin()
        if not nas.available or not nas._fl:
            raise SystemExit("NAS 未连接")
        jul_people = nas_people(nas, JUL)
        aug_people = nas_people(nas, AUG)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for job in jobs:
        bucket = job["核算桶"]
        name = job["原始文件名"]
        person = job["发起人"]
        action = []
        if job.get("跳过上传_无核算桶"):
            action.append("无核算桶_跳过（木已成舟或 9 月账期）")
            log_rows.append({**job, "时间": ts, "动作": " | ".join(action), "dry_run": not args.apply})
            print(action[-1], person, name)
            continue
        people = jul_people if bucket == JUL else aug_people
        dest_person = resolve_person(people, person) if args.apply else person
        dest_dir = f"{ROOT}/{bucket}/{dest_person}"
        dest_file = f"{dest_dir}/{name}"
        skip_upload = False
        if args.apply:
            dest_files = list_person_files(nas, bucket, dest_person) if dest_person in people else []
            dest_names = {x.get("name") for x in dest_files}
            dest_stems = {stem_key(x.get("name") or "") for x in dest_files}
            if name in dest_names or stem_key(name) in dest_stems:
                skip_upload = True
                action.append("核算桶已有同名或同茎_跳过")
        rec = {
            **job,
            "时间": ts,
            "NAS人名文件夹": dest_person,
            "NAS目标目录": dest_dir,
            "NAS目标文件": dest_file,
            "dry_run": not args.apply,
        }
        if args.apply and not skip_upload:
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
        elif skip_upload:
            rec["上传结果"] = "skipped_exists"
        else:
            rec["上传结果"] = "dry_run"
            action.append("计划上传")
        rec["动作"] = " | ".join(action)
        log_rows.append(rec)
        print(rec["动作"], dest_person, name, "->", bucket)

    report = DATA / "reports"
    report.mkdir(parents=True, exist_ok=True)
    outp = report / "aflow附件NAS归档计划.json"
    payload = {
        "src": str(src),
        "apply": args.apply,
        "confirm_scope": args.confirm_scope,
        "jobs": log_rows,
        "unmatched": unmatched,
        "in": len(jobs) + len(unmatched),
        "planned_or_uploaded": len(log_rows),
        "unmatched_n": len(unmatched),
    }
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", outp)


if __name__ == "__main__":
    main()
