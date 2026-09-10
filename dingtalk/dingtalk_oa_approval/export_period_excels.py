# -*- coding: utf-8 -*-
"""按钉钉「账期日期」自然月出 7/8 月核算表，并对照附件。不改本地 NAS 同步盘。"""
from __future__ import annotations

from paths import OA_REPORTS, OA_TOOLS, OA_WORK

import json
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TOOLS := OA_TOOLS))
sys.path.insert(0, str(_REPO))

from audit_vs_drm import load_manifest  # noqa: E402
from nas_upload_api21 import dest_bucket  # noqa: E402
from parse import keep_approval, keep_attachment  # noqa: E402
from person_folders import folder_for_initials, nas_person_folder  # noqa: E402
from patch_july_2026 import (  # noqa: E402
    F2,
    OUT_JULY,
    enrich,
    flatten_sale_account,
    read_dingtalk_xlsx,
)

BASE = OA_WORK
AUG_EXPORT = BASE / "Amazon&新平台成本 20260804-20260903 销售收款确认单-20260907092400_合并汇率&账号_2026-09-07_09-36-15.xlsx"
OUT_DIR = OA_REPORTS
JOHNEAR_ID = "202608071142000210210"
JUL_YM = "2026-07"
AUG_YM = "2026-08"


def id_text(v) -> str:
    """21 位审批编号必须当文本。已经变成 float 的无法还原，原样转成最短十进制。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s.lower() in {"", "nan", "none"}:
        return ""
    if "e+" in s.lower() or "e-" in s.lower():
        try:
            return f"{int(float(s))}"
        except ValueError:
            return s
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def locate_id(df: pd.DataFrame, bid: str) -> pd.DataFrame:
    if df.empty or "审批编号" not in df.columns:
        return pd.DataFrame()
    s = df["审批编号"].map(id_text)
    return df[s == bid].copy()


def locate_johnear_row(df: pd.DataFrame) -> pd.DataFrame:
    hit = locate_id(df, JOHNEAR_ID)
    if len(hit):
        return hit
    if df.empty:
        return pd.DataFrame()
    d = pd.to_datetime(df.get("账期日期"), errors="coerce")
    mask = d.dt.strftime("%Y-%m-%d") == "2026-07-08"
    name_col = next((c for c in ("发起人姓名", "发起人", "originator") if c in df.columns), None)
    clb = folder_for_initials("CLB")
    if name_col and clb:
        mask = mask & df[name_col].astype(str).str.contains(clb, na=False)
    acct = df.get("销售账户_展开", pd.Series("", index=df.index)).astype(str)
    plat = df.get("选择平台", pd.Series("", index=df.index)).astype(str)
    mask = mask & (acct.str.contains("Johna|Johnear", case=False, na=False) | plat.eq("亚马逊"))
    return df[mask].copy()


def drop_helper(df: pd.DataFrame) -> pd.DataFrame:
    drop = {"_sheet", "_key", "账期月", "发起", "完成", "销售账户_展开", "销售账户来源列", "收款账户_展开", "提交桶", "提交分类", "迟交天数"}
    keep = [c for c in df.columns if c not in drop]
    out = df[keep].copy()
    if "审批编号" in out.columns:
        out["审批编号"] = out["审批编号"].map(id_text)
    return out


def write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            out = df.copy()
            if "审批编号" in out.columns:
                out["审批编号"] = out["审批编号"].map(id_text)
            out.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            if "审批编号" not in out.columns:
                continue
            col = list(out.columns).index("审批编号") + 1
            for row in range(2, len(out) + 2):
                cell = ws.cell(row=row, column=col)
                if cell.value is None:
                    continue
                cell.value = id_text(cell.value)
                cell.number_format = "@"


def att_rows(recs) -> pd.DataFrame:
    rows = []
    for rec in recs:
        if not keep_approval(rec.get("status") or "", rec.get("result") or ""):
            continue
        person = rec.get("originator") or ""
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or ""
            bucket = dest_bucket(rec, name)
            months = rec.get("period_months") or []
            if JUL_YM not in months and AUG_YM not in months and bucket not in {
                "账期20260704-20260803",
                "账期20260804-20260903",
            }:
                continue
            rows.append(
                {
                    "审批编号": rec.get("businessId"),
                    "发起人": person,
                    "NAS人": nas_person_folder(person),
                    "发起时间": rec.get("createTime"),
                    "账期日期": ",".join(rec.get("period_dates") or []),
                    "账期月": ",".join(months),
                    "平台": ",".join(rec.get("platforms") or []),
                    "附件": name,
                    "核算桶": bucket,
                    "提交桶": rec.get("submit_bucket"),
                    "状态": rec.get("status"),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    m2 = enrich(read_dingtalk_xlsx(OUT_JULY)) if OUT_JULY.is_file() else pd.DataFrame()
    f2 = enrich(read_dingtalk_xlsx(F2)) if F2.is_file() else pd.DataFrame()
    aug_exp = enrich(read_dingtalk_xlsx(AUG_EXPORT)) if AUG_EXPORT.is_file() else pd.DataFrame()

    lines = []
    A = lines.append
    A("# 钉钉表 vs 附件归类")
    A(f"- 7月方法2: `{OUT_JULY.name}` exists={OUT_JULY.is_file()} rows={len(m2)}")
    A(f"- F2(7/4-9/8发起): `{F2.name}` exists={F2.is_file()} rows={len(f2)}")
    A(f"- 8月提交窗导出: `{AUG_EXPORT.name}` exists={AUG_EXPORT.is_file()} rows={len(aug_exp)}")

    for tag, df in (("方法2-7月", m2), ("F2", f2), ("8月提交窗导出", aug_exp)):
        hit = locate_id(df, JOHNEAR_ID)
        loose = locate_johnear_row(df)
        A(f"- Johnear 审批 {JOHNEAR_ID} 在「{tag}」: 编号命中 {len(hit)} 行；按账期日期+CLB {len(loose)} 行")
        if len(hit):
            A(f"  账期日期={list(hit['账期日期'].astype(str))} 账期月={list(hit['账期月'])} 发起={list(hit['发起'].astype(str))}")
        elif len(loose):
            A(f"  编号对不上（多半Excel把21位审批编号收成数字）。账期日期={list(loose['账期日期'].astype(str))} 账期月={list(loose['账期月'])} 发起={list(loose['发起'].astype(str))}")
            A(f"  该方法2/导出里的审批编号样例={list(loose['审批编号'].map(id_text).head(3))}")

    # 核算口径：以 F2 的「账期日期自然月」为准，不再用方法2的 _key 去重（方法2审批编号可能已损坏）。
    jul_out = f2[f2["账期月"] == JUL_YM].copy() if not f2.empty else pd.DataFrame()
    if not m2.empty:
        june = m2[m2["账期月"] == "2026-06"].copy()
        if not june.empty:
            jul_out = pd.concat([june, jul_out], ignore_index=True)
    aug_out = f2[f2["账期月"] == AUG_YM].copy() if not f2.empty else pd.DataFrame()

    recs = load_manifest()
    atts = att_rows(recs)
    ding_ids_jul = set(jul_out["审批编号"].map(id_text)) if not jul_out.empty else set()
    ding_ids_aug = set(aug_out["审批编号"].map(id_text)) if not aug_out.empty else set()
    att_jul = atts[atts["核算桶"] == "账期20260704-20260803"] if not atts.empty else atts
    att_aug = atts[atts["核算桶"] == "账期20260804-20260903"] if not atts.empty else atts
    miss_jul = sorted({i for i in att_jul["审批编号"].astype(str) if i not in ding_ids_jul}) if not att_jul.empty else []
    miss_aug = sorted({i for i in att_aug["审批编号"].astype(str) if i not in ding_ids_aug}) if not att_aug.empty else []
    A(f"- 7月附件审批不在7月核算表: {miss_jul}")
    A(f"- 8月附件审批不在8月核算表: {miss_aug}")

    # 8月提交窗导出里不该出现的7月账期
    if not aug_exp.empty:
        wrong_in_aug_export = aug_exp[aug_exp["账期月"] == JUL_YM]
        A(f"- 8月提交窗导出里账期月=7月的行数（含Johnear这类迟交）: {len(wrong_in_aug_export)}")
        A(f"  其中是否含Johnear编号: {JOHNEAR_ID in set(wrong_in_aug_export['审批编号'].map(id_text))}")

    ts = pd.Timestamp.now().strftime("%Y%m%d")
    jul_path = OUT_DIR / f"核算_账期日期2026-07_销售收款确认单_{ts}.xlsx"
    aug_path = OUT_DIR / f"核算_账期日期2026-08_销售收款确认单_{ts}.xlsx"
    write_xlsx(
        jul_path,
        {
            "核算行": drop_helper(jul_out),
            "附件对照": att_jul,
            "表缺附件有": pd.DataFrame({"审批编号": miss_jul, "说明": "钉钉附件在7月桶，导出表尚未覆盖（多半9/8后迟交）"}),
        },
    )
    write_xlsx(
        aug_path,
        {
            "核算行": drop_helper(aug_out),
            "附件对照": att_aug,
            "表缺附件有": pd.DataFrame({"审批编号": miss_aug, "说明": "钉钉附件在8月桶，导出表尚未覆盖（多半9/8后迟交）"}),
        },
    )
    johnear_check = pd.concat(
        [
            locate_johnear_row(m2).assign(来源="方法2"),
            locate_johnear_row(f2).assign(来源="F2_7/4-9/8发起"),
            locate_johnear_row(aug_exp).assign(来源="8月提交窗导出"),
            locate_johnear_row(jul_out).assign(来源="本7月核算表"),
            locate_johnear_row(aug_out).assign(来源="本8月核算表"),
        ],
        ignore_index=True,
    )
    if not johnear_check.empty:
        write_xlsx(OUT_DIR / f"Johnear_FR_20260708_三表核对_{ts}.xlsx", {"核对": drop_helper(johnear_check)})
    note = OUT_DIR / "核算_7月8月钉钉表说明.md"
    note.write_text("\n".join(lines + ["", f"- 7月表 `{jul_path}`", f"- 8月表 `{aug_path}`"]), encoding="utf-8")
    print("\n".join(lines))
    print("wrote", jul_path)
    print("wrote", aug_path)


if __name__ == "__main__":
    main()
