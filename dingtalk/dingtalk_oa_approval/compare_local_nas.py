# -*- coding: utf-8 -*-
"""对照：钉钉已拉附件 vs 本地两个月账期桶 vs NAS FileStation（只读）。

不改 D:\\NAS与我共享\\ 本地同步副本；不在 NAS 上移动。
"""
from __future__ import annotations

from paths import LOCAL_NAS_PERIOD, OA_DATA, finance_period_roots

import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from NAS_API.synology import get_nas

MODULE = Path(__file__).resolve().parent
DATA = OA_DATA
MANIFEST = DATA / "manifest.jsonl"
LOCAL_ROOT = LOCAL_NAS_PERIOD
JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"
SEP = "账期20260904-20261003"  # DRM 未下
REPORT = DATA / "reports"
NAS_CANDIDATES = finance_period_roots()


def load_manifest() -> list[dict]:
    if not MANIFEST.is_file():
        return []
    by = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        pid = rec.get("processInstanceId")
        if pid:
            by[pid] = rec
    return list(by.values())


def index_local(bucket: str) -> list[dict]:
    root = LOCAL_ROOT / bucket
    out = []
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        person = rel.parts[0] if rel.parts else ""
        out.append(
            {
                "bucket": bucket,
                "person": person,
                "name": p.name,
                "name_u": p.name.upper(),
                "rel": str(rel),
                "size": p.stat().st_size,
                "suffix": p.suffix.lower(),
            }
        )
    return out


def nas_try_list() -> dict:
    nas = get_nas()
    info = {"available": bool(nas.available), "shares": [], "hits": []}
    if not nas.available:
        info["error"] = "NAS client init failed"
        return info
    try:
        if nas._fl:
            sh = nas._fl.get_list_share()
            files = []
            if isinstance(sh, dict) and sh.get("success"):
                files = (sh.get("data") or {}).get("shares") or (sh.get("data") or {}).get("files") or []
            for f in files[:80]:
                info["shares"].append(
                    {
                        "name": f.get("name") or f.get("path"),
                        "path": f.get("path"),
                        "isdir": f.get("isdir"),
                    }
                )
    except Exception as e:
        info["share_error"] = str(e)[:300]
    for path in NAS_CANDIDATES:
        try:
            items = nas.get_file_list(path, limit=200)
        except Exception as e:
            info["hits"].append({"path": path, "ok": False, "error": str(e)[:200]})
            continue
        info["hits"].append(
            {
                "path": path,
                "ok": bool(items) or items == [],
                "count": len(items),
                "names": [x.get("name") for x in items[:30]],
            }
        )
    # 在已命中目录下列两个月桶
    for hit in info["hits"]:
        if not hit.get("ok") or not hit.get("count"):
            continue
        parent = hit["path"]
        for b in (JUL, AUG, SEP):
            sub = nas.get_file_list(f"{parent}/{b}", limit=200)
            hit.setdefault("buckets", []).append(
                {"bucket": b, "count": len(sub), "sample": [x.get("name") for x in sub[:15]]}
            )
    return info


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    REPORT.mkdir(parents=True, exist_ok=True)
    recs = load_manifest()
    local_jul = index_local(JUL)
    local_aug = index_local(AUG)
    local_sep = index_local(SEP)
    local_all = local_jul + local_aug + local_sep
    by_name = defaultdict(list)
    for f in local_all:
        by_name[f["name_u"]].append(f)

    att_rows = []
    name_to_atts = defaultdict(list)
    for rec in recs:
        if not rec.get("ok") and not rec.get("attachments"):
            continue
        for att in rec.get("attachments") or []:
            name = att.get("fileName") or Path(str(att.get("path") or "")).name
            name_u = name.upper()
            hits = by_name.get(name_u, [])
            submit_b = rec.get("submit_bucket") or ""
            should = rec.get("should_buckets") or []
            current_buckets = sorted({h["bucket"] for h in hits})
            person_hits = [h for h in hits if h["person"] == rec.get("originator")]
            att_rows.append(
                {
                    "审批编号": rec.get("businessId"),
                    "processInstanceId": rec.get("processInstanceId"),
                    "发起人": rec.get("originator"),
                    "发起时间": rec.get("createTime"),
                    "状态": rec.get("status"),
                    "审批结果": rec.get("result"),
                    "平台": ",".join(rec.get("platforms") or []),
                    "账期日期": ",".join(rec.get("period_dates") or []),
                    "账期月": ",".join(rec.get("period_months") or []),
                    "提交桶_现在DRM口径": submit_b,
                    "应放桶_账期月口径": ",".join(should),
                    "是否错位": "是" if should and submit_b and submit_b not in should else "否",
                    "附件控件": att.get("kind") or att.get("component"),
                    "原始文件名": name,
                    "fileId": att.get("fileId"),
                    "钉钉缓存路径": att.get("path"),
                    "本地命中桶": ",".join(current_buckets) or "未在本地7/8月桶找到",
                    "本地人名命中": ";".join(h["rel"] for h in person_hits[:5]) if person_hits else "",
                    "本地同名全部": ";".join(f"{h['bucket']}/{h['rel']}" for h in hits[:8]),
                    "同名出现次数_本地": len(hits),
                    "同名不同人": ",".join(sorted({h["person"] for h in hits})) if hits else "",
                }
            )
            name_to_atts[name_u].append(rec.get("businessId"))

    # 钉钉侧重名：同一原始文件名，多个 fileId 或多张单
    ding_collisions = []
    by_fn = defaultdict(list)
    for r in att_rows:
        if r["附件控件"] == "图片":
            continue
        by_fn[r["原始文件名"].upper()].append(r)
    for fn, rs in by_fn.items():
        fids = {x["fileId"] for x in rs if x["fileId"]}
        insts = {x["processInstanceId"] for x in rs}
        if len(rs) > 1 or len(fids) > 1:
            ding_collisions.append(
                {
                    "原始文件名": rs[0]["原始文件名"],
                    "出现次数": len(rs),
                    "不同fileId数": len(fids),
                    "不同审批单数": len(insts),
                    "发起人": ",".join(sorted({x["发起人"] for x in rs})),
                    "审批编号": ",".join(x["审批编号"] or "" for x in rs),
                }
            )

    import pandas as pd

    df = pd.DataFrame(att_rows)
    xlsx = REPORT / "附件对照_本地两月账期桶.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        if not df.empty:
            df.to_excel(xw, sheet_name="逐附件", index=False)
            df[df["是否错位"] == "是"].to_excel(xw, sheet_name="错位应挪", index=False)
            detail = df[df["附件控件"] == "账期明细"]
            detail.to_excel(xw, sheet_name="仅账期明细", index=False)
            miss = detail[detail["本地命中桶"] == "未在本地7/8月桶找到"]
            miss.to_excel(xw, sheet_name="明细本地未找到", index=False)
        pd.DataFrame(ding_collisions).to_excel(xw, sheet_name="钉钉侧文件名重名", index=False)
        pd.DataFrame(
            [
                {"桶": JUL, "本地文件数": len(local_jul), "存在": (LOCAL_ROOT / JUL).exists()},
                {"桶": AUG, "本地文件数": len(local_aug), "存在": (LOCAL_ROOT / AUG).exists()},
                {"桶": SEP, "本地文件数": len(local_sep), "存在": (LOCAL_ROOT / SEP).exists(), "备注": "DRM按提交窗10月4日后才下"},
            ]
        ).to_excel(xw, sheet_name="本地桶汇总", index=False)

    nas_info = nas_try_list()
    (REPORT / "nas_readonly_probe.json").write_text(
        json.dumps(nas_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = []
    A = md.append
    A("# 账期附件对照（钉钉 API vs 本地两个月桶 vs NAS 只读）\n")
    A("## 钉钉拉取")
    A(f"- 实例记录 {len(recs)} ；附件行 {len(att_rows)}")
    if not df.empty:
        detail = df[df["附件控件"] == "账期明细"]
        A(f"- 账期明细 {len(detail)} ；其中错位 {int((detail['是否错位']=='是').sum())} ；本地7/8月桶未找到 {int(detail['本地命中桶'].eq('未在本地7/8月桶找到').sum())}")
        A(f"- 控件 {df['附件控件'].value_counts().to_dict()}")
        A(f"- 含图片在内本地未找到 {int(df['本地命中桶'].eq('未在本地7/8月桶找到').sum())} 行")
    A(f"- 钉钉侧原始文件名碰撞组 {len(ding_collisions)}（同一文件名多 fileId 或多张单；落盘用 `fileId__原名` 不会覆盖）")
    A("\n## 本地 DRM 桶（按提交人文件夹）")
    A(f"- `{JUL}` {len(local_jul)} 文件")
    A(f"- `{AUG}` {len(local_aug)} 文件")
    A(f"- `{SEP}` {len(local_sep)} 文件（预期 0：DRM 未下 9 月）")
    A("\n归类口径：")
    A("- **现在**：NAS/本地 = 发起时间落入的 4号~下月3号桶 / 发起人姓名 / 原始文件名")
    A("- **核算/Tax 应该**：账期日期自然月对应的那个桶（7月账期即使 8/4 后才交，txt 应在 7 月桶）")
    A("- **钉钉缓存**：`dingtalk/dingtalk_oa_approval/data/files/{processInstanceId}/{fileId}__原名`")
    A("\n## NAS API 只读")
    A(f"- available={nas_info.get('available')} shares={len(nas_info.get('shares') or [])}")
    for h in nas_info.get("hits") or []:
        A(f"- `{h.get('path')}` ok={h.get('ok')} count={h.get('count')} err={h.get('error','')}")
        for b in h.get("buckets") or []:
            A(f"  - {b['bucket']}: {b['count']} {b.get('sample')}")
    A("\n未改本地同步目录，未在 NAS 上移动。")
    A(f"\n明细表：`{xlsx}`")
    out_md = REPORT / "附件对照.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
