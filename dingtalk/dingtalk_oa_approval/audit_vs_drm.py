# -*- coding: utf-8 -*-
"""对照钉钉缓存 vs DRM 本地两月账期桶，并整理一份本地副本（不写 NAS 同步盘）。"""
from __future__ import annotations

from paths import OA_DATA, local_nas_period

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from parse import (
    IMAGE_SUFFIXES,
    PARSE_SUFFIXES,
    keep_approval,
    keep_attachment,
    result_cn,
    safe_filename,
    status_cn,
)
from person_folders import mentions

DATA = OA_DATA
MANIFEST = DATA / "manifest.jsonl"
JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
SEP = "账期20260904-20261003"
REPORT = DATA / "reports"
ORGANIZED = DATA / "organized_jul_aug"
SKIP_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def load_manifest() -> list[dict]:
    by: dict[str, dict] = {}
    if not MANIFEST.is_file():
        return []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        pid = rec.get("processInstanceId")
        if pid:
            by[pid] = rec
    return list(by.values())


def norm_person(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s*\(已离职\)\s*", "", s)
    return s.strip()


def orig_name_from_cache(path_or_name: str) -> str:
    n = Path(str(path_or_name).replace("\\", "/")).name
    if n.startswith("photo__"):
        return n[len("photo__") :]
    if "__" in n:
        return n.split("__", 1)[1]
    return n


def classify_suffix(name: str) -> str:
    suf = Path(name).suffix.lower()
    if suf in PARSE_SUFFIXES:
        if suf == ".pdf":
            return "pdf"
        if suf in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
            return "excel"
        return "txt_csv"
    if suf in IMAGE_SUFFIXES:
        return "image"
    if not suf:
        return "no_ext"
    return f"other{suf}"


def index_drm(bucket: str) -> list[dict]:
    root = local_nas_period() / bucket
    out = []
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or p.name.lower() in SKIP_NAMES:
            continue
        rel = p.relative_to(root)
        person = rel.parts[0] if rel.parts else ""
        out.append(
            {
                "bucket": bucket,
                "person": person,
                "person_n": norm_person(person),
                "name": p.name,
                "name_u": p.name.upper(),
                "rel": str(rel),
                "size": p.stat().st_size,
                "suffix": p.suffix.lower(),
                "kind": classify_suffix(p.name),
                "abs": str(p),
            }
        )
    return out


def err_bucket(reason: str) -> str:
    r = reason or ""
    if "userNotExist" in r or "用户不存在" in r:
        return "userNotExist(发起人账号已失效/离职)"
    if "无附件" in r or r.startswith("无附件"):
        return "无账期明细附件"
    if "download 授权失败" in r or "http=400" in r:
        return "下载授权400"
    if "http error" in r.lower() or "HTTP Error" in r:
        return "直链下载失败"
    return (r[:80] or "未知").replace("\n", " ")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    REPORT.mkdir(parents=True, exist_ok=True)
    recs = load_manifest()
    for rec in recs:
        rec["status_cn"] = status_cn(rec.get("status") or "")
        rec["result_cn"] = result_cn(rec.get("result") or "")
        rec["keep"] = keep_approval(rec.get("status") or "", rec.get("result") or "")

    drm_jul = index_drm(JUL)
    drm_aug = index_drm(AUG)
    drm_sep = index_drm(SEP)
    drm = drm_jul + drm_aug

    inst_rows = []
    fail_rows = []
    att_rows = []
    lina_rows = []
    for rec in recs:
        atts = rec.get("attachments") or []
        errs = rec.get("errors") or []
        parse_atts = [a for a in atts if keep_attachment(a)]
        photo_atts = [a for a in atts if (a.get("kind") or "") == "图片"]
        inst_rows.append(
            {
                "审批编号": rec.get("businessId"),
                "processInstanceId": rec.get("processInstanceId"),
                "发起人": rec.get("originator"),
                "发起时间": rec.get("createTime"),
                "status": rec.get("status"),
                "result": rec.get("result"),
                "审批状态": rec.get("status_cn"),
                "审批结果": rec.get("result_cn"),
                "保留下载": "是" if rec.get("keep") else "否",
                "提交桶": rec.get("submit_bucket"),
                "应放桶": ",".join(rec.get("should_buckets") or []),
                "账期月": ",".join(rec.get("period_months") or []),
                "平台": ",".join(rec.get("platforms") or []),
                "manifest_ok": rec.get("ok"),
                "saved_n": len(atts),
                "parse_n": len(parse_atts),
                "photo_n": len(photo_atts),
                "error_n": len(errs),
                "errors": " | ".join(err_bucket(e.get("reason") or "") for e in errs),
            }
        )
        if mentions("LN", str(rec.get("originator") or "")):
            lina_rows.append({**inst_rows[-1], "error_raw": json.dumps(errs, ensure_ascii=False)[:500]})
        for e in errs:
            fail_rows.append(
                {
                    "审批编号": rec.get("businessId"),
                    "发起人": rec.get("originator"),
                    "审批状态": rec.get("status_cn"),
                    "审批结果": rec.get("result_cn"),
                    "保留下载": "是" if rec.get("keep") else "否",
                    "提交桶": rec.get("submit_bucket"),
                    "fileName": e.get("fileName"),
                    "fileId": e.get("fileId"),
                    "失败类": err_bucket(e.get("reason") or ""),
                    "reason": (e.get("reason") or "")[:400],
                }
            )
        for att in atts:
            name = att.get("fileName") or orig_name_from_cache(att.get("path") or "")
            att_rows.append(
                {
                    "审批编号": rec.get("businessId"),
                    "processInstanceId": rec.get("processInstanceId"),
                    "发起人": rec.get("originator"),
                    "发起人规范化": norm_person(rec.get("originator") or ""),
                    "发起时间": rec.get("createTime"),
                    "审批状态": rec.get("status_cn"),
                    "审批结果": rec.get("result_cn"),
                    "保留下载": "是" if rec.get("keep") else "否",
                    "提交桶": rec.get("submit_bucket"),
                    "应放桶": ",".join(rec.get("should_buckets") or []),
                    "控件": att.get("kind"),
                    "解析用": "是" if keep_attachment(att) else "否",
                    "原始文件名": name,
                    "类型": classify_suffix(name),
                    "fileId": att.get("fileId"),
                    "缓存路径": att.get("path"),
                    "bytes": att.get("bytes") or att.get("fileSize"),
                }
            )

    df_inst = pd.DataFrame(inst_rows)
    df_fail = pd.DataFrame(fail_rows)
    df_att = pd.DataFrame(att_rows)
    df_drm = pd.DataFrame(drm)
    df_lina = pd.DataFrame(lina_rows)

    # DRM vs 钉钉：只比 7/8 提交桶 + 保留审批 + 解析用文件
    drm_useful = df_drm[df_drm["kind"].isin(["txt_csv", "excel", "pdf"])].copy() if not df_drm.empty else pd.DataFrame()
    ding_keep = (
        df_att[
            (df_att["保留下载"] == "是")
            & (df_att["解析用"] == "是")
            & (df_att["提交桶"].isin([JUL, AUG]))
        ].copy()
        if not df_att.empty
        else pd.DataFrame()
    )

    drm_by_key = defaultdict(list)
    drm_by_name = defaultdict(list)
    for _, r in drm_useful.iterrows():
        drm_by_key[(r["person_n"], r["name_u"])].append(r)
        drm_by_name[r["name_u"]].append(r)

    we_vs_drm = []
    matched_drm_rels = set()
    for _, r in ding_keep.iterrows():
        nu = str(r["原始文件名"]).upper()
        hits = drm_by_key.get((r["发起人规范化"], nu)) or drm_by_name.get(nu) or []
        hit_rels = [h["rel"] for h in hits]
        hit_buckets = sorted({h["bucket"] for h in hits})
        for h in hits:
            matched_drm_rels.add((h["bucket"], h["rel"]))
        we_vs_drm.append(
            {
                **r.to_dict(),
                "DRM命中": "是" if hits else "否",
                "DRM桶": ",".join(hit_buckets),
                "DRM路径": ";".join(f"{h['bucket']}/{h['rel']}" for h in hits[:6]),
            }
        )
    df_we = pd.DataFrame(we_vs_drm)
    drm_missed_by_her = df_we[df_we["DRM命中"] == "否"] if not df_we.empty else pd.DataFrame()

    drm_not_in_us = []
    ding_names = set(ding_keep["原始文件名"].str.upper()) if not ding_keep.empty else set()
    ding_person_name = set(zip(ding_keep["发起人规范化"], ding_keep["原始文件名"].str.upper())) if not ding_keep.empty else set()
    # all keep parse files any bucket for "did we download what she has"
    all_keep_parse = df_att[(df_att["保留下载"] == "是") & (df_att["解析用"] == "是")] if not df_att.empty else pd.DataFrame()
    all_names = set(all_keep_parse["原始文件名"].str.upper()) if not all_keep_parse.empty else set()
    all_person_name = (
        set(zip(all_keep_parse["发起人规范化"], all_keep_parse["原始文件名"].str.upper()))
        if not all_keep_parse.empty
        else set()
    )
    for _, r in drm_useful.iterrows():
        in_us = (r["person_n"], r["name_u"]) in all_person_name or r["name_u"] in all_names
        drm_not_in_us.append({**r.to_dict(), "我方已下载同名": "是" if in_us else "否"})
    df_drm_gap = pd.DataFrame(drm_not_in_us)
    her_we_missed = df_drm_gap[df_drm_gap["我方已下载同名"] == "否"] if not df_drm_gap.empty else pd.DataFrame()

    # 整理本地副本：7/8 提交桶 + keep + 解析用
    copied = 0
    copy_rows = []
    if ORGANIZED.exists():
        shutil.rmtree(ORGANIZED)
    for _, r in ding_keep.iterrows():
        src = DATA / str(r["缓存路径"])
        if not src.is_file():
            copy_rows.append({**r.to_dict(), "整理": "缓存文件缺失"})
            continue
        dest_dir = ORGANIZED / r["提交桶"] / safe_filename(r["发起人"] or "unknown")
        dest_dir.mkdir(parents=True, exist_ok=True)
        fid = r.get("fileId") or "nofileid"
        dest = dest_dir / f"{fid}__{safe_filename(r['原始文件名'])}"
        shutil.copy2(src, dest)
        copied += 1
        copy_rows.append({**r.to_dict(), "整理": str(dest.relative_to(DATA))})

    drm_copied = 0
    if not her_we_missed.empty:
        for _, r in her_we_missed.iterrows():
            name = str(r.get("name") or "")
            if name.startswith("合并Amazon"):
                continue
            src = Path(str(r.get("abs") or ""))
            if not src.is_file():
                continue
            dest_dir = ORGANIZED / "_from_drm_api下不了" / str(r["bucket"]) / safe_filename(str(r["person"]))
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / safe_filename(name)
            shutil.copy2(src, dest)
            drm_copied += 1

    xlsx = REPORT / "JulAug_DRM对照审计.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        df_inst.to_excel(xw, sheet_name="实例", index=False)
        if not df_fail.empty:
            df_fail.to_excel(xw, sheet_name="失败明细", index=False)
        if not df_lina.empty:
            df_lina.to_excel(xw, sheet_name="LN", index=False)
        if not df_drm.empty:
            df_drm.to_excel(xw, sheet_name="DRM两月全部文件", index=False)
        if not df_we.empty:
            df_we.to_excel(xw, sheet_name="我方7_8解析文件", index=False)
        if not drm_missed_by_her.empty:
            drm_missed_by_her.to_excel(xw, sheet_name="她漏下_我方有", index=False)
        if not her_we_missed.empty:
            her_we_missed.to_excel(xw, sheet_name="她有_我方未下", index=False)
        pd.DataFrame(copy_rows).to_excel(xw, sheet_name="本地整理清单", index=False)

    lines = []
    A = lines.append
    A("# 钉钉附件 vs DRM 两月桶\n")
    A("## 耗时与限流")
    A("- 上次全量 441 单约 **3.1–6.5 分钟**（串行，实例间隔 0.12s + 每附件 0.05s）。")
    A("- 钉钉标准版：**每应用每接口约 20 QPS**；超限 `Forbidden.AccessDenied.QpsLimitForAppkeyAndApi`。组织月调用约 1 万次量级。")
    A("- **不建议盲目多 worker**：同一 Client ID 共享 QPS。2 个 worker 若合计压在 ~10–12 QPS 可能略快，10 个会限流。当前串行已够用。")
    A("\n## 审批过滤")
    A("- 口径：`审批状态 in {完成, 审批中}` 且 `审批结果 != 拒绝`（API：COMPLETED/RUNNING + 非 refuse）。已撤销/拒绝从现在起不再下附件。")
    if not df_inst.empty:
        A(f"- 实例 {len(df_inst)}：保留 {int((df_inst['保留下载']=='是').sum())} / 不保留 {int((df_inst['保留下载']=='否').sum())}")
        A(f"- 审批状态 {df_inst['审批状态'].value_counts().to_dict()}")
        A(f"- 审批结果 {df_inst['审批结果'].fillna('').value_counts().to_dict()}")
        A(f"- 提交桶 {df_inst['提交桶'].value_counts().to_dict()}")
    A("\n## 失败记录（manifest.jsonl 每单 errors[]）")
    if not df_fail.empty:
        A(f"- 失败行 {len(df_fail)}，按类 {df_fail['失败类'].value_counts().to_dict()}")
        keep_fail = df_fail[df_fail["保留下载"] == "是"]
        A(f"- 其中仍应保留的审批失败 {len(keep_fail)}")
    else:
        A("- 无失败行")
    A("\n## LN")
    if not df_lina.empty:
        A(f"- {len(df_lina)} 张。无解析附件={int((df_lina['parse_n']==0).sum())} 有失败={int((df_lina['error_n']>0).sum())}")
        for _, r in df_lina.iterrows():
            A(
                f"- `{r['审批编号']}` {r['审批状态']}/{r['审批结果'] or '-'} 提交桶={r['提交桶']} "
                f"parse={r['parse_n']} photo={r['photo_n']} err={r['error_n']} {r['errors']}"
            )
    A("\n## DRM 同事两月桶文件类型")
    if not df_drm.empty:
        A(f"- `{JUL}` {len(drm_jul)} 文件；`{AUG}` {len(drm_aug)}；`{SEP}` {len(drm_sep)}（9/4 后提交本地无记录，正常）")
        A(f"- 类型 {df_drm['kind'].value_counts().to_dict()}")
        A(f"- 后缀 {df_drm['suffix'].value_counts().to_dict()}")
    A("\n## 覆盖")
    A(f"- 我方 7/8 提交窗、保留、解析用文件 {len(ding_keep)}；DRM 同类型 {len(drm_useful)}")
    A(f"- 她有、我方同名已下 {int((df_drm_gap['我方已下载同名']=='是').sum()) if not df_drm_gap.empty else 0}；她有我未下 {len(her_we_missed)}")
    A(f"- 我方有、她 7/8 桶没有 {len(drm_missed_by_her)}")
    A(f"- 本地整理副本 {copied} 个文件 → `{ORGANIZED}`（不写 NAS 同步盘）")
    A(f"- 另从 DRM 只读拷了 API 下不了的 {drm_copied} 个到 `organized_jul_aug/_from_drm_api下不了`")
    A("\n## 结论（核算口径 txt/csv/xlsx + 少量 pdf）")
    A("- DRM 两月桶**没有图片**；几乎全是 txt/csv/xlsx，pdf 极少。YTQ 大量 invoice/summary PDF 她不下，我们下了，解析 Amazon 账期用不上。")
    A("- 「LN 无账期明细」不成立：单里有 AMZ txt，下载接口对离职账号返回 `userNotExist`。她 Jul 桶里已有这些 txt。")
    A("- 她有我未下的主体：LYX/LN/WHR/WZ（同一错误）+ 她自己的合并 Amazon 表 + 个别解压后的 csv。")
    A("- 我有她没有：主要是 YTQ PDF（她有意不下）和 ZKY 9/1 审批中 csv。")
    A(f"\n明细：`{xlsx}`")

    md = REPORT / "JulAug_DRM对照审计.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
