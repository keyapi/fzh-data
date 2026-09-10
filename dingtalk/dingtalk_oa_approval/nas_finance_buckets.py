# -*- coding: utf-8 -*-
"""只读探测财务账期资料；9 月桶里迟交的 7/8 月附件可按 DRM 惯例移到对应桶/人名文件夹。

默认 dry-run。加 --apply-move 才真正 FileStation move。不改 D:\\NAS与我共享\\。
"""
from __future__ import annotations

from paths import OA_DATA

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from nas_admin import FINANCE_CANDIDATES, list_shares, nas_admin
from parse import period_month_bucket, ym

JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
SEP = "账期20260904-20261003"
DATA = OA_DATA
REPORT = DATA / "reports"


def walk_files(nas, root: str, depth: int = 3) -> list[dict]:
    out = []
    stack = [(root, 0)]
    while stack:
        folder, d = stack.pop()
        items = nas.get_file_list(folder, limit=1000)
        for it in items:
            p = it.get("path") or ""
            if it.get("is_dir"):
                if d < depth:
                    stack.append((p, d + 1))
            else:
                rel = p[len(root) :].lstrip("/") if p.startswith(root) else p
                parts = [x for x in rel.split("/") if x]
                out.append(
                    {
                        "path": p,
                        "name": it.get("name"),
                        "person": parts[0] if parts else "",
                        "size": it.get("size"),
                    }
                )
    return out


def wait_task(fl, taskid: str, timeout_s: int = 120) -> dict:
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout_s:
        try:
            last = fl.get_copy_move_status(taskid)
        except Exception as e:
            msg = str(e)
            if "No such task" in msg or "no such task" in msg.lower():
                return {"success": True, "finished_missing_task": True, "error": msg}
            raise
        if isinstance(last, dict):
            data = last.get("data") or {}
            if data.get("finished") or last.get("success") and data.get("progress") == 1:
                return last
            err = last.get("error") or {}
            if err.get("code") in {1002, 408}:  # no such task / timeout
                return last
        time.sleep(0.4)
    return last


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-move", action="store_true")
    args = ap.parse_args()
    nas = nas_admin()
    info = {
        "available": bool(nas.available),
        "user": nas.username,
        "shares": list_shares(nas),
        "root": None,
        "buckets": {},
        "sep_late_moves": [],
    }
    print(f"login={nas.username} available={nas.available} shares={len(info['shares'])}")
    for s in info["shares"]:
        print(" share", s.get("path") or s.get("name"))

    root = None
    for cand in FINANCE_CANDIDATES:
        items = nas.get_file_list(cand, limit=50)
        if items:
            root = cand
            break
        # 空目录也算命中
        if nas.available and nas._fl:
            # try parent
            pass
    if not root:
        for s in info["shares"]:
            name = s.get("name") or ""
            if "财务" in name:
                probe = s.get("path") or f"/{name}"
                print("try finance share", probe)
                print("  children", [x.get("name") for x in nas.get_file_list(probe, limit=40)])

    if root:
        info["root"] = root
        print("root", root, [x.get("name") for x in nas.get_file_list(root, limit=80)])
        for b in (JUL, AUG, SEP):
            p = f"{root}/{b}"
            people = nas.get_file_list(p, limit=500)
            files = walk_files(nas, p, depth=2) if people else []
            info["buckets"][b] = {
                "people": [x.get("name") for x in people if x.get("is_dir")],
                "file_n": len(files),
                "sample": [x["name"] for x in files[:12]],
            }
            print(f"{b} people={len(info['buckets'][b]['people'])} files={len(files)}")

        sep_files = walk_files(nas, f"{root}/{SEP}", depth=2) if SEP in info["buckets"] else []
        for f in sep_files:
            # 文件名里 2026-07 / 2026-08 / 202607 / 202608
            n = f.get("name") or ""
            period = ""
            if "2026-07" in n or "202607" in n or "2026-7" in n or "2026.07" in n:
                period = "2026-07"
            elif "2026-08" in n or "202608" in n or "2026-8" in n or "2026.08" in n:
                period = "2026-08"
            if not period:
                continue
            dest_bucket = period_month_bucket(period)
            person = f.get("person") or "unknown"
            dest_dir = f"{root}/{dest_bucket}/{person}"
            rec = {
                "src": f["path"],
                "name": n,
                "person": person,
                "period": period,
                "dest_dir": dest_dir,
            }
            info["sep_late_moves"].append(rec)
            print("LATE", n, "->", dest_dir)
            if args.apply_move:
                if not any(x.get("name") == person for x in nas.get_file_list(f"{root}/{dest_bucket}", limit=500)):
                    nas.create_folder(f"{root}/{dest_bucket}", person)
                existing = {x.get("name") for x in nas.get_file_list(dest_dir, limit=500)}
                if n in existing:
                    rec["result"] = "dest_exists_skip"
                    continue
                tid = nas._fl.start_copy_move(path=f["path"], dest_folder_path=dest_dir, remove_src=True, overwrite=False)
                rec["taskid"] = tid if isinstance(tid, str) else str(tid)
                rec["status"] = wait_task(nas._fl, rec["taskid"] if isinstance(tid, str) else (tid.get("taskid") if isinstance(tid, dict) else ""))

    REPORT.mkdir(parents=True, exist_ok=True)
    outp = REPORT / "nas_finance_probe.json"
    outp.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", outp, "apply", args.apply_move, "late", len(info["sep_late_moves"]))


if __name__ == "__main__":
    main()
