# -*- coding: utf-8 -*-
"""按钉钉账期日期归附件，人名用财务惯用文件夹。不改 D:\\NAS与我共享\\。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from nas_admin import ROOT, nas_admin
from nas_finance_buckets import wait_task, walk_files
from person_folders import DINGTALK_TO_FOLDER, folder_for_initials, mapped_folder_names
from paths import OA_REPORTS

JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
REPORT = OA_REPORTS

JUL_NAME_HINTS = (
    "2026-07",
    "2026-7-",
    "2026-7.",
    "7.13",
    "7.22",
    "7.29",
)

YIN_MOVE = ["WFUS-2026-08-03.csv", "WFUS-2026-08-04(1).csv"]
YUBIN_MOVE = "Daneey独立站账期.csv"


def names_in(nas, bucket: str, person: str) -> dict[str, dict]:
    folder = f"{ROOT}/{bucket}/{person}"
    people = [x["name"] for x in nas.get_file_list(f"{ROOT}/{bucket}", limit=500) if x.get("is_dir")]
    if person not in people:
        return {}
    return {x["name"]: x for x in nas.get_file_list(folder, limit=1000) if not x.get("is_dir")}


def ensure_person(nas, bucket: str, person: str, log: list) -> None:
    people = [x["name"] for x in nas.get_file_list(f"{ROOT}/{bucket}", limit=500) if x.get("is_dir")]
    if person not in people:
        cr = nas.create_folder(f"{ROOT}/{bucket}", person)
        log.append({"动作": "建文件夹", "桶": bucket, "人": person, "结果": cr})


def move_or_drop(nas, src_path: str, dest_dir: str, dest_has: bool, log: list, why: str) -> None:
    if dest_has:
        nas._fl.delete_blocking_function(src_path)
        log.append({"动作": "删重复", "src": src_path, "dest_dir": dest_dir, "原因": why})
        print("DEL", src_path, "keep", dest_dir)
        return
    tid = nas._fl.start_copy_move(path=src_path, dest_folder_path=dest_dir, remove_src=True, overwrite=False)
    if not isinstance(tid, str) or not tid:
        if isinstance(tid, dict):
            taskid = tid.get("data") or tid.get("taskid")
            if isinstance(taskid, str) and taskid:
                wait_task(nas._fl, taskid)
        log.append({"动作": "移动", "src": src_path, "dest_dir": dest_dir, "原因": why, "task": str(tid)[:200]})
        print("MOVE", src_path, "->", dest_dir)
        return
    wait_task(nas._fl, tid)
    log.append({"动作": "移动", "src": src_path, "dest_dir": dest_dir, "原因": why, "task": str(tid)[:200]})
    print("MOVE", src_path, "->", dest_dir)


def maybe_delete_empty(nas, bucket: str, person: str, log: list) -> None:
    folder = f"{ROOT}/{bucket}/{person}"
    people = [x["name"] for x in nas.get_file_list(f"{ROOT}/{bucket}", limit=500) if x.get("is_dir")]
    if person not in people:
        return
    left = [x for x in nas.get_file_list(folder, limit=1000) if not x.get("is_dir")]
    if left:
        return
    nas.delete_folder(folder)
    log.append({"动作": "删空文件夹", "path": folder})
    print("RMDIR", folder)


def is_july_filename(name: str) -> bool:
    n = name or ""
    if "2026-08" in n or "2026-8-" in n or "2026-8." in n:
        return False
    return any(h in n for h in JUL_NAME_HINTS)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    nas = nas_admin()
    if not nas.available or not nas._fl:
        raise SystemExit("NAS 未连接")
    log = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1) 钉钉标题名 → 财务惯用文件夹（映射只在本地 json）
    for alias, canonical in DINGTALK_TO_FOLDER.items():
        for b in (JUL, AUG):
            files = walk_files(nas, f"{ROOT}/{b}", depth=2)
            alias_files = [f for f in files if f.get("person") == alias]
            if not alias_files:
                maybe_delete_empty(nas, b, alias, log)
                continue
            ensure_person(nas, b, canonical, log)
            dest_names = names_in(nas, b, canonical)
            for f in alias_files:
                name = f.get("name") or ""
                # 8 月桶里误放的 7 月文件：7 月真名夹已有则删，否则挪到 7 月真名夹
                if b == AUG and is_july_filename(name):
                    ensure_person(nas, JUL, canonical, log)
                    jul_names = names_in(nas, JUL, canonical)
                    dest_dir = f"{ROOT}/{JUL}/{canonical}"
                    move_or_drop(nas, f["path"], dest_dir, name in jul_names, log, f"{alias} 8月桶7月文件→{canonical} 7月")
                    continue
                dest_dir = f"{ROOT}/{b}/{canonical}"
                move_or_drop(nas, f["path"], dest_dir, name in dest_names, log, f"{alias}→{canonical}")
                dest_names = names_in(nas, b, canonical)
            maybe_delete_empty(nas, b, alias, log)

    # 2) YB Daneey独立站账期.csv：8月提交且表单含 8 月账期 → 回 8 月
    yb = folder_for_initials("YB")
    yb_jul = names_in(nas, JUL, yb) if yb else {}
    yb_aug = names_in(nas, AUG, yb) if yb else {}
    if yb and YUBIN_MOVE in yb_jul:
        ensure_person(nas, AUG, yb, log)
        move_or_drop(
            nas,
            yb_jul[YUBIN_MOVE]["path"],
            f"{ROOT}/{AUG}/{yb}",
            YUBIN_MOVE in yb_aug,
            log,
            "YB Daneey csv 8月提交且账期含2026-08 → 8月桶",
        )

    # 3) YTQ 两笔：账期日期 8 月、8/3 及之前提交 → 附件从 7 月挪到 8 月
    ytq = folder_for_initials("YTQ")
    yin_jul = names_in(nas, JUL, ytq) if ytq else {}
    yin_aug = names_in(nas, AUG, ytq) if ytq else {}
    if ytq:
        ensure_person(nas, AUG, ytq, log)
    for name in YIN_MOVE:
        if name not in yin_jul:
            log.append({"动作": "未找到", "人": "YTQ", "桶": JUL, "name": name})
            continue
        move_or_drop(
            nas,
            yin_jul[name]["path"],
            f"{ROOT}/{AUG}/{ytq}",
            name in yin_aug,
            log,
            "YTQ 账期日期8月 早交附件 7月→8月",
        )

    REPORT.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    js = REPORT / "NAS_账期人名对齐.json"
    xlsx = REPORT / "NAS_账期人名对齐.xlsx"
    md = REPORT / "NAS_账期人名对齐.md"
    js.write_text(json.dumps({"时间": ts, "log": log}, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(log).to_excel(xlsx, index=False)

    # 回读
    verify = {}
    for b in (JUL, AUG):
        people = [x["name"] for x in nas.get_file_list(f"{ROOT}/{b}", limit=500) if x.get("is_dir")]
        verify[b] = {}
        for person in mapped_folder_names() + ["Cici"]:
            if person not in people:
                verify[b][person] = []
                continue
            verify[b][person] = sorted(
                x["name"] for x in nas.get_file_list(f"{ROOT}/{b}/{person}", limit=1000) if not x.get("is_dir")
            )
    (REPORT / "NAS_账期人名对齐_回读.json").write_text(json.dumps(verify, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# NAS 账期/人名对齐 {ts}",
        f"- 人名：钉钉标题名→财务文件夹（见 person_folders.local.json）",
        f"- YB `{YUBIN_MOVE}` 回 8 月桶",
        f"- YTQ `{', '.join(YIN_MOVE)}` 7月→8月",
        f"- SWY PKO 账期日期 2026-07-22，留 7 月桶",
        f"- 操作 {len(log)} 步",
        "",
        json.dumps(log, ensure_ascii=False, indent=2)[:8000],
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    print("n", len(log), md)


if __name__ == "__main__":
    main()
