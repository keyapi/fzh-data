# -*- coding: utf-8 -*-
"""把 API 有、DRM 7/8 月桶没有的附件补到财务 NAS；按账期月落桶。

若 7 月账期文件目前还在 8 月桶，补入 7 月桶后从 8 月桶删除同名/同 stem（zip↔csv），避免两月各算一遍。
不改 D:\\NAS与我共享\\。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit_vs_drm import (
    AUG,
    JUL,
    DATA,
    classify_suffix,
    index_drm,
    load_manifest,
    orig_name_from_cache,
    norm_person,
)
from combine_jul_aug import skip_for_now
from nas_admin import ROOT, nas_admin
from nas_finance_buckets import wait_task, walk_files
from parse import keep_approval, keep_attachment, period_month_bucket, safe_filename

REPORT = DATA / "reports"
USEFUL = {"txt_csv", "excel", "pdf"}


def dest_bucket(rec: dict) -> str:
    months = [m for m in (rec.get("period_months") or []) if m]
    buckets = sorted({period_month_bucket(m) for m in months if period_month_bucket(m)})
    if JUL in buckets and AUG not in buckets:
        return JUL
    if AUG in buckets and JUL not in buckets:
        return AUG
    if len(buckets) == 1:
        return buckets[0]
    should = rec.get("should_buckets") or []
    if len(should) == 1:
        return should[0]
    return rec.get("submit_bucket") or AUG


def stem_key(name: str) -> str:
    return Path(name).stem.upper().replace(" ", "")


def api_missing() -> list[dict]:
    recs = load_manifest()
    have = set()
    for bucket, files in ((JUL, index_drm(JUL)), (AUG, index_drm(AUG))):
        for f in files:
            if f["kind"] not in USEFUL:
                continue
            have.add((bucket, f["person_n"], f["name_u"]))
            have.add((bucket, f["person_n"], stem_key(f["name"])))
    out = []
    for rec in recs:
        if not keep_approval(rec.get("status") or "", rec.get("result") or ""):
            continue
        submit = rec.get("submit_bucket") or ""
        if submit not in {JUL, AUG}:
            continue
        person = rec.get("originator") or ""
        person_n = norm_person(person)
        st = rec.get("status") or ""
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or orig_name_from_cache(att.get("path") or "")
            if skip_for_now(person, st, name):
                continue
            if (submit, person_n, name.upper()) in have or (submit, person_n, stem_key(name)) in have:
                continue
            src = DATA / str(att.get("path") or "")
            if not src.is_file():
                continue
            out.append(
                {
                    "审批编号": rec.get("businessId"),
                    "processInstanceId": rec.get("processInstanceId"),
                    "发起人": person,
                    "发起人规范化": person_n,
                    "审批状态": rec.get("status"),
                    "提交桶": submit,
                    "账期月": ",".join(rec.get("period_months") or []),
                    "应放桶_账期月": dest_bucket(rec),
                    "原始文件名": name,
                    "fileId": att.get("fileId"),
                    "本地缓存": str(src),
                    "bytes": src.stat().st_size,
                }
            )
    return out


def resolve_person_folder(people: list[str], originator: str) -> str:
    n = norm_person(originator)
    for p in people:
        if norm_person(p) == n:
            return p
    return originator


def hits_for(files: list[dict], person_n: str, name: str) -> list[dict]:
    want = name.upper()
    stem = stem_key(name)
    out = []
    for f in files:
        if norm_person(f.get("person") or "") != person_n:
            continue
        if (f.get("name") or "").upper() == want or stem_key(f.get("name") or "") == stem:
            out.append(f)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = api_missing()
    nas = nas_admin()
    if not nas.available:
        raise SystemExit("NAS 管理员登录失败")
    jul_files = walk_files(nas, f"{ROOT}/{JUL}", depth=2)
    aug_files = walk_files(nas, f"{ROOT}/{AUG}", depth=2)
    jul_people = [x.get("name") for x in nas.get_file_list(f"{ROOT}/{JUL}", limit=500) if x.get("is_dir")]
    aug_people = [x.get("name") for x in nas.get_file_list(f"{ROOT}/{AUG}", limit=500) if x.get("is_dir")]

    log = []
    for r in rows:
        dest_b = r["应放桶_账期月"]
        people = jul_people if dest_b == JUL else aug_people
        person_folder = resolve_person_folder(people, r["发起人"])
        dest_dir = f"{ROOT}/{dest_b}/{person_folder}"
        dest_path = f"{dest_dir}/{r['原始文件名']}"
        other_b = AUG if dest_b == JUL else JUL
        other_files = aug_files if dest_b == JUL else jul_files
        dest_files = jul_files if dest_b == JUL else aug_files
        dest_hits = hits_for(dest_files, r["发起人规范化"], r["原始文件名"])
        other_hits = hits_for(other_files, r["发起人规范化"], r["原始文件名"])
        rec = {
            **r,
            "NAS人名文件夹": person_folder,
            "NAS目标目录": dest_dir,
            "NAS目标文件": dest_path,
            "目标桶已有": ";".join(h["path"] for h in dest_hits),
            "另一桶同名或同stem": ";".join(h["path"] for h in other_hits),
            "动作": "",
            "删除8月或错桶": "",
            "结果": "",
        }
        actions = []
        if dest_hits:
            actions.append("目标已有_跳过上传")
        else:
            if person_folder not in people:
                cr = nas.create_folder(f"{ROOT}/{dest_b}", person_folder)
                actions.append(f"建文件夹={cr.get('success')}")
                people.append(person_folder)
                if dest_b == JUL:
                    jul_people.append(person_folder)
                else:
                    aug_people.append(person_folder)
            tmp_dir = Path(tempfile.mkdtemp(prefix="nas_oa_"))
            tmp_file = tmp_dir / safe_filename(r["原始文件名"])
            shutil.copy2(r["本地缓存"], tmp_file)
            up = nas._fl.upload_file(
                dest_path=dest_dir,
                file_path=str(tmp_file),
                create_parents=True,
                overwrite=False,
                progress_bar=False,
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            rec["上传返回"] = str(up)[:400]
            ok = isinstance(up, dict) and up.get("success")
            actions.append("上传成功" if ok else f"上传失败")
            if ok:
                dest_files.append(
                    {"path": dest_path, "name": r["原始文件名"], "person": person_folder, "size": r["bytes"]}
                )
        removed = []
        # 账期在 7 月却放在 8 月（或反过来）→ 删错桶，防双计
        for h in other_hits:
            if other_b != AUG and dest_b != JUL:
                # 仍删除「非目标桶」的同名，避免双月重复
                pass
            try:
                nas._fl.delete_blocking_function(h["path"])
                removed.append(h["path"])
                actions.append(f"删除错桶 {h['path']}")
            except Exception as e:
                actions.append(f"删除失败 {h['path']} {e}"[:200])
        rec["动作"] = " | ".join(actions)
        rec["删除8月或错桶"] = ";".join(removed)
        rec["结果"] = "ok" if "上传失败" not in rec["动作"] else "fail"
        log.append(rec)
        print(rec["原始文件名"], rec["应放桶_账期月"], rec["动作"])

    REPORT.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    extra_moves = []
    for h in aug_files:
        n = h.get("name") or ""
        person = h.get("person") or ""
        julyish = (
            "2026-07" in n
            or "2026-7-" in n
            or "2026-7." in n
            or "-7-25" in n
            or bool(__import__("re").search(r"(?:^|[-_])7\.\d", n))
        )
        if not julyish:
            continue
        person_folder = resolve_person_folder(jul_people, person)
        dest_dir = f"{ROOT}/{JUL}/{person_folder}"
        dest_path = f"{dest_dir}/{n}"
        if any((x.get("name") or "").upper() == n.upper() and norm_person(x.get("person") or "") == norm_person(person) for x in jul_files):
            # 7 月已有 → 只删 8 月
            try:
                nas._fl.delete_blocking_function(h["path"])
                extra_moves.append({"src": h["path"], "动作": "7月已有_删除8月重复", "结果": "ok"})
            except Exception as e:
                extra_moves.append({"src": h["path"], "动作": "删除8月失败", "结果": str(e)[:200]})
            continue
        if person_folder not in jul_people:
            nas.create_folder(f"{ROOT}/{JUL}", person_folder)
            jul_people.append(person_folder)
        tid = nas._fl.start_copy_move(path=h["path"], dest_folder_path=dest_dir, remove_src=True, overwrite=False)
        task_id = tid if isinstance(tid, str) else (tid.get("taskid") if isinstance(tid, dict) else str(tid))
        st = wait_task(nas._fl, task_id) if task_id else {}
        extra_moves.append({"src": h["path"], "dest": dest_path, "taskid": str(task_id)[:120], "动作": "8月→7月移动", "status": str(st)[:200]})
        print("MOVE", h["path"], "->", dest_dir)

    df = pd.DataFrame(log)
    xlsx = REPORT / "NAS补入21_操作记录.xlsx"
    df.to_excel(xlsx, index=False)
    if extra_moves:
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="补入", index=False)
            pd.DataFrame(extra_moves).to_excel(xw, sheet_name="8月迟交挪到7月", index=False)
    body = df.fillna("").to_string(index=False)
    md = REPORT / "NAS补入21_操作记录.md"
    md.write_text(
        "\n".join(
            [
                "# NAS 补入 API 有而 DRM 桶没有的附件\n",
                f"- 根目录 `{ROOT}`",
                f"- 按账期月放入 `{JUL}` / `{AUG}` / 发起人 / 原名",
                "- 目标桶已有则跳过上传；另一桶同名或 zip↔csv 同 stem 则删除，避免 7/8 月双计",
                "- 8 月桶里文件名属于 7 月账期的，移动到 7 月桶后从 8 月移除",
                "- 未改 `D:\\NAS与我共享\\`",
                f"- 补入行数 {len(df)} ；挪移 {len(extra_moves)}\n",
                body,
                "\n## 8月→7月\n",
                json.dumps(extra_moves, ensure_ascii=False, indent=2),
                f"\nExcel：`{xlsx}`",
            ]
        ),
        encoding="utf-8",
    )
    (REPORT / "NAS补入21_操作记录.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote", xlsx)


if __name__ == "__main__":
    main()
