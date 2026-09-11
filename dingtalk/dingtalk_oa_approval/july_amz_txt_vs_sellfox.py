# -*- coding: utf-8 -*-
"""赛狐 7 月 Amazon 结算组 vs 钉钉 Amazon .txt（不含 csv）。对照 7 天内提交规则。"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from paths import OA_REPORTS
from parse import filename_period_month, keep_approval, keep_attachment, parse_amz_channel, ym  # noqa: E402
from person_folders import nas_person_folder  # noqa: E402
from sellfox_amz_settlements import (  # noqa: E402
    MKT_TO_SITE,
    ding_brand_site,
    shop_brand_site,
)
from audit_vs_drm import load_manifest  # noqa: E402

OUT = OA_REPORTS
SF_XLSX = OUT / "赛狐Amazon结算组_7-8月.xlsx"
SLA_DAYS = 7
JUL = "2026-07"
CLOSED = "2026-07-03"  # 此前发起的已算进 6 月，不拿来对 7 月缺口


def ding_july_txt() -> pd.DataFrame:
    recs = load_manifest()
    rows = []
    for rec in recs:
        if not keep_approval(rec.get("status") or "", rec.get("result") or ""):
            continue
        created = str(rec.get("createTime") or "")[:10]
        person = nas_person_folder(rec.get("originator") or "")
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or ""
            if not str(name).lower().endswith(".txt"):
                continue
            amz = parse_amz_channel(name)
            if not amz:
                continue
            months = rec.get("period_months") or []
            fm = filename_period_month(name) or amz.get("period_month")
            pm = months[0] if len(months) == 1 else fm
            if pm != JUL and fm != JUL:
                continue
            b, s = ding_brand_site(amz.get("channel") or "", name)
            rows.append(
                {
                    "人": person,
                    "附件": name,
                    "brand": b,
                    "site": s,
                    "文件名账期月": fm,
                    "表单账期月": ",".join(months),
                    "审批编号": rec.get("businessId"),
                    "发起时间": rec.get("createTime"),
                    "发起日": created,
                    "木已成舟6月": created <= CLOSED,
                }
            )
    return pd.DataFrame(rows)


def file_date(name: str) -> str:
    amz = parse_amz_channel(name) or {}
    raw = str(amz.get("date_raw") or "")
    m = re.search(r"(20\d{2})[-._]?(\d{1,2})[-._]?(\d{1,2})", raw or name)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(?:^|[-_])(\d{1,2})[.\-](\d{1,2})(?:\(\d+\))?$", Path(name).stem)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def shop_key(shop_name: str, marketplace: str) -> tuple[str, str]:
    n = shop_name or ""
    b, s = shop_brand_site(n, marketplace)
    nu = n.upper()
    if "TOODDLY" in nu:
        b = "TOODDLY"
    # 渠道账号表：赛狐店名 ≠ 账期文件名前缀
    if "RUCENER" in nu or "如森" in n:
        b = "ROSOON"
    if "NOVELLEDO" in nu or "YTHD" in nu or "云途汇德" in n:
        b = "YTHD"
    return b, s


def parse_end(v) -> str:
    s = str(v or "").replace("/", "-")[:10]
    return s if re.match(r"20\d{2}-\d{2}-\d{2}", s) else ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    gdf = pd.read_excel(SF_XLSX)
    gdf["groupEnd"] = gdf["groupEnd"].map(parse_end)
    gdf["账期月"] = gdf["groupEnd"].map(lambda x: x[:7] if x else "")
    jul = gdf[gdf["账期月"] == JUL].copy()
    keys = []
    for _, r in jul.iterrows():
        b, s = shop_key(str(r.get("shopName") or ""), str(r.get("marketplace") or ""))
        keys.append((b, s))
    jul["brand"] = [k[0] for k in keys]
    jul["site"] = [k[1] for k in keys]
    ddf = ding_july_txt()
    ding_open = ddf[~ddf["木已成舟6月"]].copy() if not ddf.empty else ddf

    used = set()
    rows = []
    for _, g in jul.sort_values(["shopName", "groupEnd"]).iterrows():
        end = g["groupEnd"]
        b, s = g["brand"], g["site"]
        cand = ding_open[(ding_open["brand"] == b) & (ding_open["site"] == s)] if not ding_open.empty else ding_open
        best_i, best_dt = None, None
        for i, d in cand.iterrows():
            if i in used:
                continue
            fd = file_date(d["附件"])
            if not fd or not end:
                continue
            dt = abs((pd.to_datetime(fd) - pd.to_datetime(end)).days)
            if best_dt is None or dt < best_dt:
                best_dt, best_i = dt, i
        hit = ding_open.loc[best_i] if best_i is not None and best_dt is not None and best_dt <= 10 else None
        if hit is not None:
            used.add(best_i)
            submit = str(hit["发起日"] or "")[:10]
            delay = (pd.to_datetime(submit) - pd.to_datetime(end)).days if submit and end else None
            if delay is None:
                verd = "对上了但缺提交日"
            elif delay <= SLA_DAYS:
                verd = "7天内已交"
            else:
                verd = f"迟交{delay}天"
            rows.append(
                {
                    "赛狐店": g.get("shopName"),
                    "站点": g.get("marketplace"),
                    "brand": b,
                    "site": s,
                    "结算结束日": end,
                    "settlementId": g.get("settlementId"),
                    "打款金额": g.get("transferAmount"),
                    "钉钉附件": hit["附件"],
                    "提交人": hit["人"],
                    "提交日": submit,
                    "间隔天": delay,
                    "结论": verd,
                    "审批编号": hit["审批编号"],
                }
            )
        else:
            rows.append(
                {
                    "赛狐店": g.get("shopName"),
                    "站点": g.get("marketplace"),
                    "brand": b,
                    "site": s,
                    "结算结束日": end,
                    "settlementId": g.get("settlementId"),
                    "打款金额": g.get("transferAmount"),
                    "钉钉附件": "",
                    "提交人": "",
                    "提交日": "",
                    "间隔天": None,
                    "结论": "赛狐有结算组_钉钉无对应txt_漏交或未匹配",
                    "审批编号": "",
                }
            )
    extra = ding_open.drop(index=list(used), errors="ignore") if not ding_open.empty else ding_open
    cdf = pd.DataFrame(rows)
    outp = OUT / "赛狐7月Amazon结算组_vs_钉钉txt_7天规则.xlsx"
    with pd.ExcelWriter(outp, engine="openpyxl") as xw:
        cdf.to_excel(xw, sheet_name="对照", index=False)
        jul.to_excel(xw, sheet_name="赛狐7月全部结算组", index=False)
        ddf.to_excel(xw, sheet_name="钉钉7月txt含6月已算", index=False)
        if extra is not None and len(extra):
            extra.to_excel(xw, sheet_name="钉钉txt未匹配赛狐", index=False)
    n = len(cdf)
    ok = int((cdf["结论"] == "7天内已交").sum()) if n else 0
    late = int(cdf["结论"].astype(str).str.startswith("迟交").sum()) if n else 0
    miss = int(cdf["结论"].astype(str).str.contains("漏交").sum()) if n else 0
    lines = [
        f"赛狐 7 月 Amazon 结算组 {len(jul)} 条（groupEnd 落在 2026-07）。",
        f"钉钉 Amazon .txt（账期/文件名在 7 月）{len(ddf)} 条，其中发起≤7/3 已算 6 月 {int(ddf['木已成舟6月'].sum()) if not ddf.empty else 0} 条，不拿来补 7 月缺口。",
        f"对照：{n}；7天内已交 {ok}；迟交 {late}；赛狐有、钉钉无对应 txt {miss}。",
        "赛狐 API 给的是结算组（店铺/站点/起止日/结算ID/打款额），不是 Amazon 后台那份 .txt 原件。核「有没有这一期」够用；核金额仍看钉钉 txt + 审批表。",
        f"写出 {outp}",
    ]
    (OUT / "赛狐7月Amazon_vs_钉钉txt.md").write_text("\n".join(lines) + "\n\n" + cdf.groupby("结论").size().to_string(), encoding="utf-8")
    print("\n".join(lines))
    if miss:
        print("\n漏交样例（最多 25）")
        sub = cdf[cdf["结论"].astype(str).str.contains("漏交")][["赛狐店", "站点", "结算结束日", "打款金额"]].head(25)
        print(sub.to_string(index=False))
    if late:
        print("\n迟交")
        print(cdf[cdf["结论"].astype(str).str.startswith("迟交")][["赛狐店", "站点", "结算结束日", "钉钉附件", "提交日", "间隔天", "提交人"]].to_string(index=False))


if __name__ == "__main__":
    main()
