# -*- coding: utf-8 -*-
"""7 月 Amazon：按渠道账号综合 NAS(全员文件夹) + 钉钉核算表 + 赛狐结算组 + 渠道账号负责人。

人名文件夹 = 提交人，不是负责人。不写本地 NAS 同步盘。
口径与 7 月结论见 docs/research/2026-09-10-july-amazon-period-reconcile.md。
"""
from __future__ import annotations

from paths import LOCAL_NAS_PERIOD, OA_REPORTS, OA_TOOLS

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
_TOOLS = OA_TOOLS
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_REPO))

from audit_vs_drm import load_manifest  # noqa: E402
from channel_account_sync.fetch_sources import fetch_sheet  # noqa: E402
from channel_account_sync.plan import sheet_records  # noqa: E402
from export_period_excels import id_text  # noqa: E402
from july_amz_txt_vs_sellfox import file_date, parse_end, shop_key  # noqa: E402
from parse import parse_amz_channel, ym  # noqa: E402
from patch_july_2026 import flatten_sale_account, read_dingtalk_xlsx  # noqa: E402
from person_folders import folder_for_initials, nas_person_folder  # noqa: E402
from sellfox_amz_settlements import ding_brand_site  # noqa: E402

OUT = OA_REPORTS
NAS_JUL = LOCAL_NAS_PERIOD / "账期20260704-20260803"
NAS_JUN = LOCAL_NAS_PERIOD / "账期20260604-20260703"
NAS_AUG = LOCAL_NAS_PERIOD / "账期20260804-20260903"
JUL_XLSX = OUT / "核算_账期日期2026-07_销售收款确认单_20260910.xlsx"
SF_XLSX = OUT / "赛狐Amazon结算组_7-8月.xlsx"
SITES = "US|UK|DE|FR|IT|ES|CA|MX|BE|NL|SE|PL|AU|JP|IN|IE|AT"


def brand_site_from_code(code: str) -> tuple[str, str]:
    raw = (code or "").strip()
    amz = parse_amz_channel(raw + "-2026-07-01.txt")
    if amz and amz.get("site"):
        b, s = ding_brand_site(amz.get("channel") or "", raw + "-2026-07-01.txt")
        if "YTHD" in raw.upper() or "NOVELLEDO" in raw.upper():
            b = "YTHD"
        if "ROSOON" in raw.upper() or "RUCENER" in raw.upper():
            b = "ROSOON"
        return b, s
    u = re.sub(r"[^A-Za-z0-9]", "", raw.upper())
    if u.startswith("AMZ"):
        u = u[3:]
    m = re.search(rf"({SITES})$", u, re.I)
    if not m:
        return ding_brand_site(u, ""), ""
    site = m.group(1).upper()
    brand = u[: m.start()]
    fake = f"AMZ{brand}{site}-2026-07-01.txt"
    b, s = ding_brand_site("", fake)
    if brand in {"YTHD", "NOVELLEDO"}:
        b = "YTHD"
    if brand in {"ROSOON", "RUCENER"}:
        b = "ROSOON"
    return b, s or site


def walk_nas_amz(root: Path, bucket: str) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for p in root.rglob("*.txt"):
        name = p.name
        amz = parse_amz_channel(name)
        if not amz:
            continue
        person = p.parent.name
        b, s = ding_brand_site(amz.get("channel") or "", name)
        rows.append(
            {
                "来源": "NAS",
                "桶": bucket,
                "提交人文件夹": person,
                "附件": name,
                "brand": b,
                "site": s,
                "文件日期": file_date(name),
                "文件名账期月": (file_date(name) or "")[:7],
                "path": str(p),
            }
        )
    return rows


def excel_amz_rows() -> pd.DataFrame:
    df = read_dingtalk_xlsx(JUL_XLSX) if JUL_XLSX.is_file() else pd.DataFrame()
    if df.empty and JUL_XLSX.is_file():
        df = pd.read_excel(JUL_XLSX, sheet_name="核算行")
    if df.empty:
        return df
    df = df.copy()
    df["账期月"] = df["账期日期"].map(ym)
    df = df[df["账期月"] == "2026-07"].copy()
    acct = df.apply(flatten_sale_account, axis=1)
    df["销售账户"] = [a for a, _ in acct]
    df["销售账户来源列"] = [s for _, s in acct]
    plat = df.get("选择平台", pd.Series("", index=df.index)).astype(str)
    amz = df[plat.str.contains("亚马逊") | df["销售账户"].astype(str).str.upper().str.startswith("AMZ")].copy()
    keys = [brand_site_from_code(str(x)) for x in amz["销售账户"]]
    amz["brand"] = [k[0] for k in keys]
    amz["site"] = [k[1] for k in keys]
    amz["提交人"] = amz.get("发起人姓名", pd.Series("", index=amz.index)).map(lambda x: nas_person_folder(str(x).replace("(已离职)", "")))
    amz["审批编号"] = amz["审批编号"].map(id_text) if "审批编号" in amz.columns else ""
    return amz


def manifest_amz() -> pd.DataFrame:
    rows = []
    for rec in load_manifest():
        person = nas_person_folder((rec.get("originator") or "").replace("(已离职)", ""))
        names = []
        for att in rec.get("attachments") or []:
            names.append(att.get("fileName") or "")
        for err in rec.get("errors") or []:
            names.append(err.get("fileName") or "")
        for name in names:
            if not str(name).lower().endswith(".txt"):
                continue
            amz = parse_amz_channel(name)
            if not amz:
                continue
            b, s = ding_brand_site(amz.get("channel") or "", name)
            rows.append(
                {
                    "提交人": person,
                    "附件": name,
                    "brand": b,
                    "site": s,
                    "文件日期": file_date(name),
                    "审批编号": rec.get("businessId"),
                    "发起时间": rec.get("createTime"),
                    "状态": rec.get("status"),
                    "下载失败": bool(rec.get("errors")),
                }
            )
    return pd.DataFrame(rows)


def gsheet_amz_owners() -> pd.DataFrame:
    sheet = fetch_sheet()
    recs, _ = sheet_records(sheet["header"], sheet.get("rows") or [])
    rows = []
    for rec in recs:
        ch = str(rec.get("渠道") or "")
        code = str(rec.get("渠道账号") or "").strip()
        if "亚马逊" not in ch and not code.upper().startswith("AMZ"):
            continue
        b, s = brand_site_from_code(code)
        rows.append(
            {
                "渠道账号": code,
                "别名": rec.get("渠道账号别名") or "",
                "赛狐店铺": rec.get("赛狐店铺") or "",
                "运营分组": rec.get("运营分组") or "",
                "运营人员202607": rec.get("运营人员202607") or "",
                "运营人员202608": rec.get("运营人员202608") or "",
                "brand": b,
                "site": s,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    owners = gsheet_amz_owners()
    nas = pd.DataFrame(
        walk_nas_amz(NAS_JUL, "账期20260704-20260803")
        + walk_nas_amz(NAS_JUN, "账期20260604-20260703")
        + walk_nas_amz(NAS_AUG, "账期20260804-20260903")
    )
    nas7 = nas[nas["文件名账期月"] == "2026-07"].copy() if not nas.empty else nas
    excel = excel_amz_rows()
    mani = manifest_amz()
    gdf = pd.read_excel(SF_XLSX)
    gdf["groupEnd"] = gdf["groupEnd"].map(parse_end)
    jul_sf = gdf[gdf["groupEnd"].astype(str).str.startswith("2026-07")].copy()
    keys = [shop_key(str(r.get("shopName") or ""), str(r.get("marketplace") or "")) for _, r in jul_sf.iterrows()]
    jul_sf["brand"] = [k[0] for k in keys]
    jul_sf["site"] = [k[1] for k in keys]

    owner_map = {}
    for _, r in owners.iterrows():
        if r["brand"] and r["site"]:
            owner_map[(r["brand"], r["site"])] = r["运营人员202607"]

    rows = []
    for _, g in jul_sf.sort_values(["shopName", "groupEnd"]).iterrows():
        b, s, end = g["brand"], g["site"], g["groupEnd"]
        owner = owner_map.get((b, s), "")
        nas_hits = nas7[(nas7["brand"] == b) & (nas7["site"] == s)] if not nas7.empty else nas7
        # 日期近的优先
        nas_txt, nas_people = [], set()
        for _, n in nas_hits.iterrows():
            fd = n.get("文件日期") or ""
            if fd and abs((pd.to_datetime(fd) - pd.to_datetime(end)).days) <= 10:
                nas_txt.append(n["附件"])
                nas_people.add(n["提交人文件夹"])
        if not nas_txt and len(nas_hits):
            nas_txt = list(nas_hits["附件"].astype(str))
            nas_people = set(nas_hits["提交人文件夹"].astype(str))
        ex_hits = excel[(excel["brand"] == b) & (excel["site"] == s)] if not excel.empty else excel
        ex_people, ex_ids = [], []
        if ex_hits is not None and len(ex_hits):
            dlt = pd.to_datetime(ex_hits["账期日期"], errors="coerce")
            close = ex_hits[(dlt - pd.to_datetime(end)).abs().dt.days <= 10] if len(ex_hits) else ex_hits
            use = close if len(close) else ex_hits
            ex_people = sorted({str(x) for x in use["提交人"] if str(x) not in {"", "nan"}})
            ex_ids = [id_text(x) for x in use["审批编号"]]
        amt = pd.to_numeric(g.get("transferAmount"), errors="coerce")
        has_nas = bool(nas_txt)
        has_excel = bool(ex_ids)
        if has_nas or has_excel:
            verd = "有附件或核算行"
            if has_nas and not has_excel:
                verd = "NAS有txt_核算表未对上"
            elif has_excel and not has_nas:
                verd = "核算表有行_NAS无对应txt"
        else:
            verd = "赛狐有组_NAS和核算表都没有" if (pd.isna(amt) or amt != 0) else "赛狐有组打款0_无txt无表行"
        rows.append(
            {
                "赛狐店": g.get("shopName"),
                "站点": g.get("marketplace"),
                "brand": b,
                "site": s,
                "结算结束日": end,
                "打款金额": g.get("transferAmount"),
                "表负责人202607": owner,
                "NAS提交人": "、".join(sorted(nas_people)),
                "NAS文件": "; ".join(nas_txt[:6]),
                "核算提交人": "、".join(ex_people),
                "核算审批编号": ";".join(ex_ids[:6]),
                "结论": verd,
                "提交人是否等于负责人": (
                    "无从比"
                    if not owner
                    else ("是" if owner in nas_people or owner in ex_people else "否_助手或换人")
                ),
            }
        )

    cdf = pd.DataFrame(rows)
    ln_folder = folder_for_initials("LN")
    lina = (
        nas7[nas7["提交人文件夹"].str.contains(ln_folder, na=False)]
        if ln_folder and not nas7.empty
        else pd.DataFrame()
    )
    split = nas7.groupby(["brand", "site"])["提交人文件夹"].nunique().reset_index(name="提交人文件夹数") if not nas7.empty else pd.DataFrame()
    split = split[split["提交人文件夹数"] > 1] if not split.empty else split

    outp = OUT / "7月Amazon_按账号综合_NAS核算表赛狐负责人.xlsx"
    with pd.ExcelWriter(outp, engine="openpyxl") as xw:
        cdf.to_excel(xw, sheet_name="按结算组对照", index=False)
        nas7.to_excel(xw, sheet_name="NAS全员7月txt", index=False)
        if not excel.empty:
            excel[
                [c for c in ["审批编号", "发起人姓名", "发起时间", "账期日期", "销售账户", "brand", "site", "应收账款", "销售额"] if c in excel.columns]
            ].to_excel(xw, sheet_name="核算表亚马逊7月", index=False)
        owners.to_excel(xw, sheet_name="渠道账号202607负责人", index=False)
        if not lina.empty:
            lina.to_excel(xw, sheet_name="LN文件夹7月txt", index=False)
        if not split.empty:
            split.to_excel(xw, sheet_name="同一账号多人文件夹", index=False)
        if not mani.empty:
            mani.to_excel(xw, sheet_name="钉钉API含离职下载失败", index=False)

    n = len(cdf)
    lines = [
        f"赛狐 7 月结算组 {n}",
        f"NAS 三桶里文件名属 7 月的 Amazon txt：{len(nas7)}（按提交人文件夹，不是负责人）",
        f"7 月核算表亚马逊行：{len(excel)}",
        f"渠道账号表 Amazon 行：{len(owners)}，有 202607 负责人：{int((owners['运营人员202607'].astype(str).str.strip() != '').sum()) if not owners.empty else 0}",
        f"结论：{cdf['结论'].value_counts().to_dict() if n else {}}",
        f"提交人≠负责人：{int((cdf['提交人是否等于负责人']=='否_助手或换人').sum())}",
        f"同一账号 7 月 txt 出现在多个 NAS 人名文件夹：{len(split)}",
        f"LN 文件夹 7 月 Amazon txt：{len(lina)}",
        f"写出 {outp}",
    ]
    (OUT / "7月Amazon_按账号综合说明.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    if len(lina):
        print("\nLN 文件夹（提交人≠负责人的例子）")
        print(lina[["附件", "brand", "site", "文件日期"]].to_string(index=False))
    print("\n有打款且 NAS+核算都没有（才像真漏交）")
    miss = cdf[cdf["结论"] == "赛狐有组_NAS和核算表都没有"]
    print(miss[["赛狐店", "站点", "结算结束日", "打款金额", "表负责人202607"]].to_string(index=False) if len(miss) else "(无)")


if __name__ == "__main__":
    main()
