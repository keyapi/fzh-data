# -*- coding: utf-8 -*-
"""把钉钉 API 里 F2 截止后的审批，按现有导出表列写成核算行。先用于 9/9 CLB 6 张。

不改 D:\\NAS与我共享\\。审批编号按文本写出。
"""
from __future__ import annotations

from paths import OA_DATA, OA_REPORTS, OA_TOOLS

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
_TOOLS = OA_TOOLS
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_REPO))

from client import get_access_token, get_instance  # noqa: E402
from ding_xlsx import F2, id_text, read_dingtalk_xlsx  # noqa: E402
from export_period_excels import write_xlsx  # noqa: E402
from parse import collect_dd_attachments, keep_attachment, parse_table_rows, result_cn, status_cn, ym  # noqa: E402

OUT_DIR = OA_REPORTS
AUG_PATH = OUT_DIR / "核算_账期日期2026-08_销售收款确认单_20260910.xlsx"
LATE_IDS = [
    "202609090931000287248",
    "202609090946000572037",
    "202609090957000314358",
    "202609091009000148884",
    "202609091025000583294",
    "202609091028000271289",
]
MANIFEST = OA_DATA / "manifest.jsonl"


def local_ts(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    t = pd.to_datetime(v, errors="coerce", utc=True)
    if pd.isna(t):
        t = pd.to_datetime(v, errors="coerce")
        if pd.isna(t):
            return str(v)
        return t.strftime("%Y-%m-%d %H:%M:%S")
    return t.tz_convert("Asia/Shanghai").tz_localize(None).strftime("%Y-%m-%d %H:%M:%S")


def load_manifest() -> list[dict]:
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def inst_id_by_business(bid: str) -> str:
    for rec in load_manifest():
        if rec.get("businessId") == bid:
            return rec.get("processInstanceId") or ""
    return ""


def approval_log(inst: dict) -> str:
    parts = []
    for op in inst.get("operationRecords") or []:
        who = op.get("userName") or op.get("userId") or ""
        uid = op.get("userId") or ""
        typ = op.get("type") or op.get("operationType") or ""
        t = op.get("date") or op.get("operateTime") or ""
        remark = op.get("remark") or ""
        parts.append(f"{who}|{uid}|{typ}|{t}|{remark}")
    return ";\n\n".join(parts)


def attach_names(inst: dict) -> str:
    form = inst.get("formComponentValues") or []
    names = []
    for att in collect_dd_attachments(form):
        if keep_attachment(att) and (att.get("fileName") or "").lower().endswith(".txt"):
            names.append(att.get("fileName") or "")
        elif keep_attachment(att):
            names.append(att.get("fileName") or "")
    return ";".join(names)


def header_row(inst: dict, f2_cols: list[str]) -> dict:
    created = inst.get("createTime") or ""
    finish = inst.get("finishTime") or inst.get("finish_time") or ""
    row = {
        "数据id": inst.get("processInstanceId") or "",
        "审批编号": inst.get("businessId") or "",
        "审批单名称": inst.get("title") or inst.get("processInstanceName") or "销售收款确认单",
        "标题": inst.get("title") or "",
        "审批状态": status_cn(inst.get("status") or ""),
        "审批结果": result_cn(inst.get("result") or ""),
        "发起时间": local_ts(created),
        "完成时间": local_ts(finish),
        "发起人姓名": (inst.get("title") or "").replace("的销售收款确认单", ""),
        "发起人UserID": inst.get("originatorUserId") or "",
        "发起人部门": "",
        "历史审批人姓名": "",
        "审批记录": approval_log(inst),
        "当前审批节点": "",
        "账期明细": attach_names(inst),
        "图片": "",
    }
    # 只保留导出表里有的列名
    return {k: v for k, v in row.items() if k in f2_cols}


def table_to_excel_rows(inst: dict, f2_cols: list[str]) -> list[dict]:
    form = inst.get("formComponentValues") or []
    tables = parse_table_rows(form)
    head = header_row(inst, f2_cols)
    out = []
    for rec in tables:
        row = {c: None for c in f2_cols}
        row.update(head)
        for lab, val in rec.items():
            if lab in f2_cols:
                row[lab] = val
            elif lab == "账期日期" and "账期日期" in f2_cols:
                row["账期日期"] = str(val)[:10] if val else val
        out.append(row)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    f2 = read_dingtalk_xlsx(F2)
    f2_cols = list(f2.columns)
    f2_cols = [c for c in f2_cols if not str(c).startswith("Unnamed") and str(c) != "_sheet"]
    token = get_access_token()
    new_rows = []
    dump = []
    for bid in LATE_IDS:
        iid = inst_id_by_business(bid)
        if not iid:
            print("missing instance", bid)
            continue
        inst = get_instance(token, iid)
        form = inst.get("formComponentValues") or []
        tables = parse_table_rows(form)
        dump.append(
            {
                "审批编号": bid,
                "processInstanceId": iid,
                "status": inst.get("status"),
                "table_keys": sorted({k for r in tables for k in r}),
                "账期日期": [str(r.get("账期日期") or "")[:10] for r in tables],
                "选择平台": [r.get("选择平台") for r in tables],
                "附件txt": [
                    a.get("fileName")
                    for a in collect_dd_attachments(form)
                    if str(a.get("fileName") or "").lower().endswith(".txt")
                ],
            }
        )
        new_rows.extend(table_to_excel_rows(inst, f2_cols))
        print(bid, "rows", len(tables), "dates", [str(r.get("账期日期") or "")[:10] for r in tables])

    nd = pd.DataFrame(new_rows)
    if not nd.empty:
        nd["账期月"] = nd["账期日期"].map(ym)
        nd["审批编号"] = nd["审批编号"].map(id_text)
    aug_only = nd[nd["账期月"] == "2026-08"].copy() if not nd.empty else nd
    sep_only = nd[nd["账期月"] == "2026-09"].copy() if not nd.empty else nd

    old = pd.read_excel(AUG_PATH, sheet_name="核算行", dtype={"审批编号": str})
    old["审批编号"] = old["审批编号"].map(id_text)
    have = set(old["审批编号"])
    add = aug_only[~aug_only["审批编号"].isin(have)].copy() if not aug_only.empty else aug_only
    merged = pd.concat([old, add.drop(columns=["账期月"], errors="ignore")], ignore_index=True)

    att = pd.read_excel(AUG_PATH, sheet_name="附件对照", dtype=str) if "附件对照" in pd.ExcelFile(AUG_PATH).sheet_names else pd.DataFrame()
    ts = datetime.now().strftime("%Y%m%d")
    outp = OUT_DIR / f"核算_账期日期2026-08_销售收款确认单_{ts}_含9月9日API补行.xlsx"
    extra_sheets = {
        "核算行": merged,
        "API补的8月行": add.drop(columns=["账期月"], errors="ignore") if not add.empty else pd.DataFrame(),
        "同单9月账期暂不进8月表": sep_only.drop(columns=["账期月"], errors="ignore") if not sep_only.empty else pd.DataFrame(),
        "附件对照": att,
    }
    write_xlsx(outp, extra_sheets)
    (OUT_DIR / "CLB9月9日_API表单字段.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print("old", len(old), "add", len(add), "merged", len(merged), "sep_hold", len(sep_only))
    print("wrote", outp)


if __name__ == "__main__":
    main()
