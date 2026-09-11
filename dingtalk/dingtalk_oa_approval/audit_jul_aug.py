# -*- coding: utf-8 -*-
"""7/8 月账期附件彻底对照：NAS 归类 + 钉钉提交 + Amazon 渠道次数。

不改 D:\\NAS与我共享\\。默认只出报告；--apply 才在 NAS 上挪错月文件、补上传缺失附件。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from audit_vs_drm import DATA, orig_name_from_cache, norm_person, load_manifest
from combine_jul_aug import skip_for_now
from nas_admin import ROOT, nas_admin
from nas_finance_buckets import wait_task, walk_files
from nas_upload_api21 import KEEP_IN_AUG, dest_bucket, list_person_files, nas_people, resolve_person, stem_key
from parse import (
    filename_period_month,
    keep_approval,
    keep_attachment,
    parse_amz_channel,
    period_month_bucket,
    safe_filename,
)
from person_folders import folder_for_initials, nas_person_folder

JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
REPORT = DATA / "reports"


def is_useful(att: dict) -> bool:
    return keep_attachment(att)


def ding_jobs(recs: list[dict]) -> list[dict]:
    jobs = []
    for rec in recs:
        rec["keep"] = keep_approval(rec.get("status") or "", rec.get("result") or "")
        if not rec["keep"]:
            continue
        person = rec.get("originator") or "unknown"
        st = rec.get("status") or ""
        months = rec.get("period_months") or []
        for att in rec.get("attachments") or []:
            if not is_useful(att):
                continue
            name = att.get("fileName") or orig_name_from_cache(att.get("path") or "")
            why_skip = skip_for_now(person, st, name)
            bucket = dest_bucket(rec, name)
            src = DATA / str(att.get("path") or "")
            amz = parse_amz_channel(name)
            jobs.append(
                {
                    "审批编号": rec.get("businessId"),
                    "发起人": person,
                    "NAS人": nas_person_folder(norm_person(person)),
                    "发起时间": rec.get("createTime"),
                    "状态": rec.get("status"),
                    "账期日期": ",".join(rec.get("period_dates") or []),
                    "账期月": ",".join(months),
                    "平台": ",".join(rec.get("platforms") or []),
                    "提交桶": rec.get("submit_bucket"),
                    "核算桶": bucket,
                    "原始文件名": name,
                    "fileId": att.get("fileId"),
                    "本地缓存": str(src) if src.is_file() else "",
                    "有缓存": src.is_file(),
                    "跳过": why_skip,
                    "Amazon渠道": (amz or {}).get("channel") or "",
                    "文件名账期月": filename_period_month(name) or (amz or {}).get("period_month") or "",
                    "亚马逊文件": bool(amz),
                }
            )
    return jobs


def nas_index(nas) -> list[dict]:
    rows = []
    for b in (JUL, AUG):
        for f in walk_files(nas, f"{ROOT}/{b}", depth=2):
            name = f.get("name") or ""
            amz = parse_amz_channel(name)
            fm = filename_period_month(name)
            rows.append(
                {
                    "桶": b,
                    "人": f.get("person") or "",
                    "文件": name,
                    "path": f.get("path"),
                    "size": f.get("size"),
                    "文件名账期月": fm,
                    "Amazon渠道": (amz or {}).get("channel") or "",
                    "亚马逊文件": bool(amz),
                    "跨月保留8月": name.upper() in KEEP_IN_AUG,
                }
            )
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    recs = load_manifest()
    jobs = ding_jobs(recs)
    nas = nas_admin()
    if not nas.available:
        raise SystemExit("NAS 未连接")
    nas_rows = nas_index(nas)
    nas_keys = {(r["桶"], r["人"], r["文件"].upper()) for r in nas_rows}
    nas_name_keys = {(r["人"], r["文件"].upper()) for r in nas_rows}

    lines = []
    A = lines.append
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    A(f"# 7/8 月账期附件彻底检查 {ts}")

    A("\n## CLB AMZ-Johnear-FR-20260708.txt")
    target = "AMZ-Johnear-FR-20260708.txt"
    nas_hits = [r for r in nas_rows if r["文件"].upper() == target.upper()]
    ding_hits = [j for j in jobs if j["原始文件名"].upper() == target.upper()]
    A(f"- NAS: {json.dumps(nas_hits, ensure_ascii=False)}")
    A(f"- 钉钉: {json.dumps(ding_hits, ensure_ascii=False)}")

    lxj = folder_for_initials("LXJ")
    A("\n## LXJ")
    lxj_jobs = [j for j in jobs if lxj and j["NAS人"] == lxj]
    for ym in ("2026-07", "2026-08"):
        sub = [j for j in lxj_jobs if ym in (j["账期月"] or "")]
        A(f"- 钉钉账期月 {ym}：{len(sub)} 个附件 / {len({j['审批编号'] for j in sub})} 张单")
        for j in sub:
            A(f"  {j['审批编号']} {j['发起时间']} 平台={j['平台']} {j['原始文件名']} → {j['核算桶']}")
    for b in (JUL, AUG):
        files = [r for r in nas_rows if r["桶"] == b and lxj and r["人"] == lxj]
        A(f"- NAS {b}/LXJ：{[r['文件'] for r in files] or '空或不存在'}")

    # 文件名月 vs 桶：以钉钉账期日期为准；无钉钉匹配才看文件名。
    # PKO 文件名 20260803 但账期日期 7/22 → 留 7 月。9 月账期文件暂留 8 月桶（9 月桶 10/4 后再归）。
    ding_by_file = {(j["NAS人"], j["原始文件名"].upper()): j for j in jobs}
    wrong = []
    for r in nas_rows:
        if r["跨月保留8月"]:
            continue
        ding = ding_by_file.get((r["人"], r["文件"].upper()))
        ding_months = []
        if ding:
            ding_months = [m for m in (ding["账期月"] or "").split(",") if m]
        if ding_months == ["2026-07"] and r["桶"] != JUL:
            wrong.append({**r, "问题": "钉钉账期7月但文件不在7月桶"})
            continue
        if ding_months == ["2026-08"] and r["桶"] != AUG:
            wrong.append({**r, "问题": "钉钉账期8月但文件不在8月桶"})
            continue
        if "2026-09" in ding_months and "2026-08" not in ding_months and "2026-07" not in ding_months:
            if r["桶"] in {JUL, AUG}:
                wrong.append({**r, "问题": "钉钉账期9月暂留7/8月桶_10月4日后归9月", "只提醒": True})
            continue
        if ding_months:
            continue
        fm = r["文件名账期月"]
        if fm == "2026-07" and r["桶"] == AUG:
            wrong.append({**r, "问题": "7月文件在8月桶"})
        elif fm == "2026-08" and r["桶"] == JUL:
            wrong.append({**r, "问题": "8月文件在7月桶"})
    A(f"\n## 文件名账期月与桶不一致：{len(wrong)}")
    for r in wrong:
        A(f"- {r['问题']} {r['桶']}/{r['人']}/{r['文件']}")

    # 钉钉有、核算桶缺
    missing_nas = []
    for j in jobs:
        if j["跳过"] or not j["核算桶"] or not j["有缓存"]:
            continue
        key = (j["核算桶"], j["NAS人"], j["原始文件名"].upper())
        if key not in nas_keys:
            missing_nas.append(j)
    A(f"\n## 钉钉已交且有缓存、但核算桶没有：{len(missing_nas)}")
    for j in missing_nas:
        A(f"- {j['NAS人']} {j['原始文件名']} 账期月={j['账期月']} 应放 {j['核算桶']} 审批 {j['审批编号']} 发起 {j['发起时间']}")

    no_cache = [j for j in jobs if j["核算桶"] and not j["有缓存"] and not j["跳过"]]
    A(f"\n## 应进 7/8 桶但缓存下载失败：{len(no_cache)}")
    for j in no_cache[:40]:
        A(f"- {j['NAS人']} {j['原始文件名']} {j['审批编号']}")

    # Amazon 渠道次数
    A("\n## Amazon 渠道 × 自然月（钉钉附件，完成/审批中）")
    by_ch = defaultdict(lambda: {"2026-07": [], "2026-08": []})
    for j in jobs:
        months = [m for m in (j["账期月"] or "").split(",") if m in {"2026-07", "2026-08"}]
        if len(months) == 1:
            pm = months[0]
        else:
            pm = j["文件名账期月"]
            if pm not in {"2026-07", "2026-08"}:
                continue
        ch = j["Amazon渠道"] or "(文件名解析不出渠道)"
        if not j["亚马逊文件"] and "亚马逊" not in (j["平台"] or ""):
            continue
        by_ch[(j["NAS人"], ch)][pm].append(j)
    gap_rows = []
    for (person, ch), mm in sorted(by_ch.items()):
        n7, n8 = len(mm["2026-07"]), len(mm["2026-08"])
        flag = ""
        if n7 >= 2 and n8 == 0:
            flag = "8月0次_需补提交"
        elif n7 >= 2 and n8 == 1:
            flag = "8月仅1次_可能缺一期"
        elif n8 >= 2 and n7 == 0:
            flag = "7月0次_需核对该店是否7月才开"
        elif n8 == 1 and n7 == 1:
            flag = "两月各1次_可能都缺一期"
        elif n7 == 0 and n8 == 0:
            continue
        elif max(n7, n8) >= 4:
            flag = "次数偏多_核对是否重复交"
        A(f"- {person} / {ch}: 7月{n7} 8月{n8} {flag}")
        if flag:
            gap_rows.append(
                {
                    "人": person,
                    "渠道": ch,
                    "7月次数": n7,
                    "8月次数": n8,
                    "提醒": flag,
                    "7月文件": "; ".join(x["原始文件名"] for x in mm["2026-07"]),
                    "8月文件": "; ".join(x["原始文件名"] for x in mm["2026-08"]),
                }
            )

    apply_log = []
    if args.apply:
        # 1) 挪错月
        for r in wrong:
            if r.get("只提醒"):
                continue
            src = r["path"]
            prob = r.get("问题") or ""
            if "不在7月桶" in prob or prob.startswith("7月文件"):
                want_m = "2026-07"
            elif "不在8月桶" in prob or "8月文件在7月" in prob:
                want_m = "2026-08"
            else:
                continue
            dest_b = period_month_bucket(want_m)
            person = r["人"]
            people = nas_people(nas, dest_b)
            if person not in people:
                nas.create_folder(f"{ROOT}/{dest_b}", person)
            dest_names = {x.get("name") for x in list_person_files(nas, dest_b, person)}
            dest_dir = f"{ROOT}/{dest_b}/{person}"
            if r["文件"] in dest_names or r["文件"].upper() in {str(x).upper() for x in dest_names}:
                nas._fl.delete_blocking_function(src)
                apply_log.append({"动作": "删重复", "src": src, "dest": dest_dir})
            else:
                tid = nas._fl.start_copy_move(path=src, dest_folder_path=dest_dir, remove_src=True, overwrite=False)
                if isinstance(tid, str) and tid:
                    wait_task(nas._fl, tid)
                apply_log.append({"动作": "移动", "src": src, "dest": dest_dir})
            print(apply_log[-1])

        # 2) 补上传
        for j in missing_nas:
            person = j["NAS人"]
            bucket = j["核算桶"]
            name = j["原始文件名"]
            people = nas_people(nas, bucket)
            dest_person = resolve_person(people, person)
            nas.create_folder(f"{ROOT}/{bucket}", dest_person)
            dest_dir = f"{ROOT}/{bucket}/{dest_person}"
            dest_files = list_person_files(nas, bucket, dest_person)
            dest_names = {x.get("name") for x in dest_files}
            dest_stems = {stem_key(x.get("name") or "") for x in dest_files}
            if name.lower().endswith(".zip") and stem_key(name) in dest_stems:
                apply_log.append({"动作": "zip已有同茎csv_跳过", "file": name, "dir": dest_dir})
                continue
            if name in dest_names or stem_key(name) in dest_stems:
                apply_log.append({"动作": "已存在跳过", "file": name, "dir": dest_dir})
                continue
            with tempfile.TemporaryDirectory() as td:
                local = Path(td) / safe_filename(name)
                shutil.copy2(j["本地缓存"], local)
                up = nas._fl.upload_file(
                    dest_path=dest_dir,
                    file_path=str(local),
                    create_parents=True,
                    overwrite=False,
                    progress_bar=False,
                )
            apply_log.append({"动作": "上传", "file": name, "dir": dest_dir, "result": str(up)[:300]})
            print("UP", dest_person, name, "->", bucket)

        # 空文件夹：8 月 LXJ 若仍空则保留（可能稍后补交），不删以免误会

    REPORT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jobs).to_excel(REPORT / "JulAug_钉钉附件核算.xlsx", index=False)
    pd.DataFrame(nas_rows).to_excel(REPORT / "JulAug_NAS文件.xlsx", index=False)
    pd.DataFrame(wrong).to_excel(REPORT / "JulAug_桶内错月.xlsx", index=False)
    pd.DataFrame(missing_nas).to_excel(REPORT / "JulAug_核算桶缺失.xlsx", index=False)
    pd.DataFrame(gap_rows).to_excel(REPORT / "JulAug_Amazon渠道次数异常.xlsx", index=False)
    if apply_log:
        pd.DataFrame(apply_log).to_excel(REPORT / "JulAug_NAS对齐操作.xlsx", index=False)
        (REPORT / "JulAug_NAS对齐操作.json").write_text(json.dumps(apply_log, ensure_ascii=False, indent=2), encoding="utf-8")
    md = REPORT / "JulAug_彻底检查.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(md.read_text(encoding="utf-8")[:12000])
    print("wrote", md, "missing", len(missing_nas), "wrong", len(wrong), "amazon_gaps", len(gap_rows), "apply", len(apply_log))


if __name__ == "__main__":
    main()
